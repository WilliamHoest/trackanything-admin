import httpx
from time import perf_counter
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)
from fake_useragent import UserAgent
from app.services.scraping.core.domain_utils import get_etld_plus_one
from app.services.scraping.core.rate_limit import get_domain_limiter
from app.services.scraping.core.metrics import observe_http_error, observe_http_request

# === Configuration ===
TIMEOUT_SECONDS = 6
MAX_RETRIES = 2
RETRY_WAIT_MIN = 2  # seconds
RETRY_WAIT_MAX = 8  # seconds

# Initialize User-Agent rotator
ua = UserAgent()

# Modern browser headers to avoid "Soft 404" and improve compatibility with social media platforms
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,da;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

def get_random_user_agent() -> str:
    """Get a random User-Agent string"""
    try:
        return ua.random
    except Exception:
        # Fallback if fake-useragent fails - modern Chrome on macOS
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_default_headers() -> dict:
    """
    Get default HTTP headers with a random User-Agent.
    Returns a new dict to avoid mutation issues.
    """
    headers = DEFAULT_HEADERS.copy()
    headers["User-Agent"] = get_random_user_agent()
    return headers


def _is_retryable_error(exception: Exception) -> bool:
    """
    Retry ONLY on:
    - httpx.RequestError (network/transport issues)
    - HTTP 429 (rate limiting)
    - HTTP 5xx (server errors)

    Fail fast on client errors such as 400/401/403/404 (and other non-429 4xx).
    """
    if isinstance(exception, httpx.RequestError):
        return True

    if isinstance(exception, httpx.HTTPStatusError):
        status = exception.response.status_code if exception.response is not None else None
        if status == 429:
            return True
        if status is not None and 500 <= status <= 599:
            return True
        return False

    return False


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
    retry=retry_if_exception(_is_retryable_error),
    reraise=True
)
async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    rate_profile: str = "html",
    metrics_provider: str = "unknown",
    **kwargs
) -> httpx.Response:
    """
    Fetch URL with automatic retry on network errors or 5xx status codes.
    Uses exponential backoff: 2s, 4s, 8s.
    Automatically follows redirects (up to 20 by default).
    """
    # Ensure follow_redirects is enabled (default in httpx, but explicit for clarity)
    if 'follow_redirects' not in kwargs:
        kwargs['follow_redirects'] = True

    etld1 = get_etld_plus_one(url)
    limiter = get_domain_limiter(etld1, rate_profile)

    started_at = perf_counter()
    try:
        async with limiter:
            response = await client.get(url, **kwargs)
        response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
        observe_http_request(
            provider=metrics_provider,
            domain=etld1,
            status_code=str(response.status_code),
            duration_seconds=perf_counter() - started_at,
        )
        return response
    except httpx.HTTPStatusError as exc:
        status_code = str(exc.response.status_code) if exc.response is not None else "http_status_error"
        observe_http_request(
            provider=metrics_provider,
            domain=etld1,
            status_code=status_code,
            duration_seconds=perf_counter() - started_at,
        )
        observe_http_error(
            provider=metrics_provider,
            domain=etld1,
            error_type=f"http_{status_code}",
        )
        raise
    except httpx.RequestError as exc:
        observe_http_error(
            provider=metrics_provider,
            domain=etld1,
            error_type=type(exc).__name__,
        )
        raise
