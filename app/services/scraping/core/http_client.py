import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from fake_useragent import UserAgent

# === Configuration ===
TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
RETRY_WAIT_MIN = 2  # seconds
RETRY_WAIT_MAX = 8  # seconds

# Initialize User-Agent rotator
ua = UserAgent()

def get_random_user_agent() -> str:
    """Get a random User-Agent string"""
    try:
        return ua.random
    except Exception:
        # Fallback if fake-useragent fails
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    reraise=True
)
async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
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

    response = await client.get(url, **kwargs)
    response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
    return response
