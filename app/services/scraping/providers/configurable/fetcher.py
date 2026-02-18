from typing import Dict, List, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse
import logging

from bs4 import BeautifulSoup
import httpx

from app.services.scraping.core.http_client import fetch_with_retry
from app.services.scraping.core.text_processing import (
    compile_keyword_patterns,
    get_platform_from_url,
    keyword_matches_text,
    normalize_url,
)
from .config import _get_config_for_domain, _log, _normalize_domain
from .extractor import (
    _extract_content,
    _is_confident_date_for_filtering,
    _parse_date_value,
)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _scrape_article_content(
    client: httpx.AsyncClient,
    url: str,
    keywords: List[str],
    from_date: Optional[datetime] = None,
    config_cache: Optional[Dict[str, Optional[Dict]]] = None,
    blind_domain_counts: Optional[Dict[str, int]] = None,
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
        response = await fetch_with_retry(client, url, headers=headers)
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 402:
            _log(scrape_run_id, f"Paywall blocked (402) for {url}")
            return None
        raise

    final_url = normalize_url(str(response.url)) if response.url else normalize_url(url)
    if final_url != normalize_url(url):
        _log(scrape_run_id, f"Redirected article URL: {url} -> {final_url}", level=logging.DEBUG)

    soup = BeautifulSoup(response.text, "lxml")
    title, content, date_str, date_confident, extracted_via = await _extract_content(
        soup,
        response.text,
        config,
        scrape_run_id=scrape_run_id,
    )

    text_to_search = f"{title} {content}"
    if keyword_matches_text(patterns, text_to_search):
        if config and config.get("domain"):
            platform = config["domain"]
        else:
            platform = get_platform_from_url(final_url)

        published_parsed = None
        if date_str:
            parsed_date = _parse_date_value(date_str, scrape_run_id=scrape_run_id)
            if parsed_date:
                if from_date_utc and parsed_date < from_date_utc:
                    if _is_confident_date_for_filtering(date_str, date_confident):
                        _log(
                            scrape_run_id,
                            f"Date too old for {final_url}: {parsed_date} < {from_date_utc}",
                            level=logging.DEBUG,
                        )
                        return None
                    _log(
                        scrape_run_id,
                        f"Date looked old but extraction was low confidence for {final_url}. Keeping article.",
                        level=logging.DEBUG,
                    )
                published_parsed = parsed_date.timetuple()
            else:
                _log(
                    scrape_run_id,
                    f"Date missing or unparseable for {final_url}. Keeping published_parsed=None.",
                    level=logging.DEBUG,
                )

        article = {
            "title": title or "Uden titel",
            "link": final_url,
            "published_parsed": published_parsed,
            "platform": platform,
            "content_teaser": content[:500] if content else "",
        }

        config_status = "config" if config else "generic"
        _log(
            scrape_run_id,
            f"Match ({platform}, {config_status}, extracted_via={extracted_via}): {title}",
            level=logging.DEBUG,
        )
        return article

    if not title and not content:
        blind_domain = _normalize_domain(urlparse(final_url).netloc)
        if blind_domain and blind_domain_counts is not None:
            blind_domain_counts[blind_domain] = blind_domain_counts.get(blind_domain, 0) + 1

    _log(scrape_run_id, f"Keyword match failed for {final_url}", level=logging.DEBUG)
    _log(
        scrape_run_id,
        f"  Title: {len(title)} chars, Content: {len(content)} chars",
        level=logging.DEBUG,
    )
    return None
