from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from dateutil import parser as dateparser
import httpx
import logging

from app.core.config import settings
from app.services.scraping.core.http_client import (
    fetch_with_retry, 
    TIMEOUT_SECONDS
)
from app.services.scraping.core.text_processing import clean_keywords

logger = logging.getLogger("scraping")


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[GNews] %s", prefix, message)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_gnews_iso(dt: datetime) -> str:
    # GNews expects RFC3339/ISO8601, e.g. 2026-02-17T12:30:00Z
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def scrape_gnews(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None
) -> List[Dict]:
    """
    Fetch articles from GNews API.
    Uses async httpx with retry logic.
    
    Args:
        keywords: List of keywords to search for
        from_date: Optional datetime to filter articles from. Defaults to 24 hours ago.
    """
    if not keywords or not settings.gnews_api_key:
        if not settings.gnews_api_key:
            _log(scrape_run_id, "GNEWS_API_KEY is not set.", logging.WARNING)
        return []

    since = _normalize_utc(from_date) or (datetime.now(timezone.utc) - timedelta(hours=24))
    cleaned = clean_keywords(keywords)
    query = quote_plus(" OR ".join(cleaned))
    since_iso = quote_plus(_to_gnews_iso(since))
    url = (
        f"https://gnews.io/api/v4/search?"
        f"q={query}&token={settings.gnews_api_key}&lang=da,en&max=20&sortby=publishedAt&from={since_iso}"
    )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            from app.services.scraping.core.http_client import get_default_headers
            headers = get_default_headers()
            response = await fetch_with_retry(
                client,
                url,
                rate_profile="api",
                metrics_provider="gnews",
                headers=headers,
            )
            data = response.json()

            articles_data = data.get("articles", [])
            entries = []
            _log(scrape_run_id, f"Applying API cutoff from={_to_gnews_iso(since)}")

            for article in articles_data:
                if "url" not in article:
                    continue

                try:
                    published_at = article.get("publishedAt")
                    if not published_at:
                        continue
                    try:
                        parsed = dateparser.parse(published_at)
                    except Exception:
                        continue
                    if parsed is None:
                        continue

                    # Ensure UTC-aware
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    else:
                        parsed = parsed.astimezone(timezone.utc)

                    if parsed < since:
                        continue

                    entries.append({
                        "title": article.get("title", "Uden titel"),
                        "link": article["url"],
                        "published_parsed": parsed.timetuple(),
                        "platform": "GNews",
                        "content_teaser": article.get("description", "")
                    })
                    _log(scrape_run_id, f"Match: {article.get('title', 'Uden titel')}", logging.DEBUG)

                except Exception as e:
                    _log(scrape_run_id, f"Article parse error: {e}", logging.WARNING)
                    continue

            return entries

    except Exception as e:
        _log(scrape_run_id, f"Request failed: {e}", logging.ERROR)
        return []
