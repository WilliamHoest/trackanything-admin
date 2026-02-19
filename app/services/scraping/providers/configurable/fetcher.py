from typing import Dict, List, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse
import logging
import asyncio

from bs4 import BeautifulSoup
import httpx

from app.services.scraping.core.http_client import fetch_with_retry
from app.services.scraping.core.metrics import observe_extraction, observe_playwright_fallback
from app.services.scraping.core.text_processing import (
    compile_keyword_patterns,
    get_platform_from_url,
    keyword_match_score,
    normalize_url,
)
from .config import _get_config_for_domain, _log, _normalize_domain
from .extractor import (
    _has_meaningful_content,
    _extract_content,
    _parse_date_value,
)
from .config import PLAYWRIGHT_CONCURRENCY_LIMIT

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None
    PlaywrightTimeoutError = Exception


PLAYWRIGHT_NAVIGATION_TIMEOUT_MS = 15000
PLAYWRIGHT_RENDER_WAIT_MS = 800
_playwright_semaphore = asyncio.Semaphore(PLAYWRIGHT_CONCURRENCY_LIMIT)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _fetch_with_playwright(
    url: str,
    scrape_run_id: Optional[str] = None,
) -> Optional[tuple[str, str]]:
    """
    Fetch rendered HTML with Playwright for JS-heavy pages.
    Returns tuple of (html, final_url) or None on failure.
    """
    if async_playwright is None:
        _log(
            scrape_run_id,
            f"Playwright fallback unavailable (not installed) for {url}",
            logging.DEBUG,
        )
        return None

    async with _playwright_semaphore:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT_MS,
                    )
                    await page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)
                    html = await page.content()
                    final_url = normalize_url(page.url) if page.url else normalize_url(url)
                    await context.close()
                    return html, final_url
                finally:
                    await browser.close()
        except PlaywrightTimeoutError as e:
            _log(scrape_run_id, f"Playwright timeout for {url}: {e}", logging.WARNING)
            return None
        except Exception as e:
            _log(scrape_run_id, f"Playwright fallback failed for {url}: {type(e).__name__}: {e}", logging.WARNING)
            return None


async def _scrape_article_content(
    client: httpx.AsyncClient,
    url: str,
    keywords: List[str],
    from_date: Optional[datetime] = None,
    config_cache: Optional[Dict[str, Optional[Dict]]] = None,
    blind_domain_counts: Optional[Dict[str, int]] = None,
    min_keyword_matches: int = 2,
    allow_partial_matches: bool = False,
    scrape_run_id: Optional[str] = None,
) -> Optional[Dict]:
    """Scrape a single article URL and return a mention payload if keyword-matched."""
    if not keywords:
        return None

    patterns = compile_keyword_patterns(keywords)
    from_date_utc = _normalize_utc(from_date)

    parsed = urlparse(url)
    domain = _normalize_domain(parsed.netloc)

    config = await _get_config_for_domain(
        domain,
        config_cache=config_cache,
        scrape_run_id=scrape_run_id,
    )

    from app.services.scraping.core.http_client import get_default_headers

    headers = get_default_headers()

    try:
        response = await fetch_with_retry(
            client,
            url,
            rate_profile="html",
            metrics_provider="configurable",
            headers=headers,
        )
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 402:
            _log(scrape_run_id, f"Paywall blocked (402) for {url}")
            return None
        raise

    final_url = normalize_url(str(response.url)) if response.url else normalize_url(url)
    metrics_domain = _normalize_domain(urlparse(final_url).netloc) or domain or "unknown"
    if final_url != normalize_url(url):
        _log(scrape_run_id, f"Redirected article URL: {url} -> {final_url}", level=logging.DEBUG)

    soup = BeautifulSoup(response.text, "lxml")
    title, content, date_str, _date_confident, extracted_via = await _extract_content(
        soup,
        response.text,
        config,
        scrape_run_id=scrape_run_id,
    )

    if not _has_meaningful_content(content):
        observe_playwright_fallback(metrics_domain, "triggered")
        _log(
            scrape_run_id,
            f"Standard fetch failed (len={len(content)}). Triggering Playwright fallback for {final_url}...",
            logging.INFO,
        )
        playwright_result = await _fetch_with_playwright(final_url, scrape_run_id=scrape_run_id)
        if playwright_result:
            pw_html, pw_final_url = playwright_result
            pw_soup = BeautifulSoup(pw_html, "lxml")
            pw_title, pw_content, pw_date_str, _pw_date_confident, pw_extracted_via = await _extract_content(
                pw_soup,
                pw_html,
                config,
                scrape_run_id=scrape_run_id,
            )
            if _has_meaningful_content(pw_content):
                if pw_title:
                    title = pw_title
                content = pw_content
                if pw_date_str:
                    date_str = pw_date_str
                extracted_via = f"{pw_extracted_via}+playwright"
                if pw_final_url and normalize_url(pw_final_url) != final_url:
                    _log(
                        scrape_run_id,
                        f"Playwright resolved redirected URL: {final_url} -> {pw_final_url}",
                        logging.DEBUG,
                    )
                    final_url = normalize_url(pw_final_url)
                _log(
                    scrape_run_id,
                    f"Playwright fallback succeeded for {final_url} (len={len(content)})",
                    logging.INFO,
                )
                observe_playwright_fallback(metrics_domain, "success")
            else:
                _log(
                    scrape_run_id,
                    f"Playwright fallback returned low/empty content for {final_url} (len={len(pw_content)})",
                    logging.DEBUG,
                )
                observe_playwright_fallback(metrics_domain, "low_content")
        else:
            _log(scrape_run_id, f"Playwright fallback failed for {final_url}", logging.DEBUG)
            observe_playwright_fallback(metrics_domain, "failed")

    if _has_meaningful_content(content):
        observe_extraction("configurable", metrics_domain, "success", len(content))
    else:
        observe_extraction("configurable", metrics_domain, "empty_content", 0)

    text_to_search = f"{title} {content}"
    term_match_score = keyword_match_score(patterns, text_to_search)
    passed_threshold = term_match_score >= max(1, int(min_keyword_matches))
    keep_partial = allow_partial_matches and term_match_score > 0

    if passed_threshold or keep_partial:
        if config and config.get("domain"):
            platform = config["domain"]
        else:
            platform = get_platform_from_url(final_url)

        published_parsed = None
        parsed_date = _parse_date_value(date_str, scrape_run_id=scrape_run_id) if date_str else None

        # Strict cutoff policy for configurable sources:
        # if from_date is active, article must have a parseable date and satisfy cutoff.
        if from_date_utc is not None:
            if not date_str:
                observe_extraction("configurable", metrics_domain, "date_missing_cutoff_skip", 0)
                _log(
                    scrape_run_id,
                    f"Date missing for {final_url} with active cutoff {from_date_utc.isoformat()}. Skipping.",
                    level=logging.DEBUG,
                )
                return None

            if not parsed_date:
                observe_extraction("configurable", metrics_domain, "date_unparseable_cutoff_skip", 0)
                _log(
                    scrape_run_id,
                    (
                        f"Date unparseable for {final_url} "
                        f"(raw='{date_str}') with active cutoff {from_date_utc.isoformat()}. Skipping."
                    ),
                    level=logging.DEBUG,
                )
                return None

            if parsed_date < from_date_utc:
                observe_extraction("configurable", metrics_domain, "date_before_cutoff_skip", 0)
                _log(
                    scrape_run_id,
                    f"Date too old for {final_url}: {parsed_date} < {from_date_utc}. Skipping.",
                    level=logging.DEBUG,
                )
                return None

        if parsed_date:
            published_parsed = parsed_date.timetuple()

        article = {
            "title": title or "Uden titel",
            "link": final_url,
            "published_parsed": published_parsed,
            "platform": platform,
            "content_teaser": content[:500] if content else "",
            "_term_match_count": term_match_score,
        }

        config_status = "config" if config else "generic"
        if passed_threshold:
            _log(
                scrape_run_id,
                (
                    f"Match ({platform}, {config_status}, extracted_via={extracted_via}, "
                    f"term_matches={term_match_score}): {title}"
                ),
                level=logging.DEBUG,
            )
        else:
            _log(
                scrape_run_id,
                (
                    f"Partial match retained for fallback "
                    f"({platform}, term_matches={term_match_score}): {title}"
                ),
                level=logging.DEBUG,
            )
        return article

    if not title and not content:
        blind_domain = _normalize_domain(urlparse(final_url).netloc)
        if blind_domain and blind_domain_counts is not None:
            blind_domain_counts[blind_domain] = blind_domain_counts.get(blind_domain, 0) + 1

    _log(
        scrape_run_id,
        (
            f"Keyword match failed for {final_url} "
            f"(term_matches={term_match_score}, required={min_keyword_matches})"
        ),
        level=logging.DEBUG,
    )
    _log(
        scrape_run_id,
        f"  Title: {len(title)} chars, Content: {len(content)} chars",
        level=logging.DEBUG,
    )
    return None
