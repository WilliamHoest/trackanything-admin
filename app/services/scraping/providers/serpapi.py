from typing import List, Dict, Optional
from datetime import datetime, timezone
import asyncio
import logging
from dateutil import parser as dateparser
from serpapi import GoogleSearch

from app.core.config import settings
from app.services.scraping.core.text_processing import clean_keywords

logger = logging.getLogger("scraping")


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[SerpAPI] %s", prefix, message)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_tbs_from_date(from_date: Optional[datetime]) -> Optional[str]:
    """
    Map an absolute datetime cutoff to Google News tbs buckets.
    """
    cutoff = _normalize_utc(from_date)
    if cutoff is None:
        return None

    now = datetime.now(timezone.utc)
    if cutoff > now:
        return "qdr:d"

    age_seconds = (now - cutoff).total_seconds()
    if age_seconds <= 24 * 3600:
        return "qdr:d"
    if age_seconds <= 7 * 24 * 3600:
        return "qdr:w"
    if age_seconds <= 31 * 24 * 3600:
        return "qdr:m"
    if age_seconds <= 365 * 24 * 3600:
        return "qdr:y"
    return None


async def scrape_serpapi(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None
) -> List[Dict]:
    """
    Fetch articles from SerpAPI (Google News).
    Uses async httpx with retry logic.

    Args:
        keywords: List of keywords to search for
        from_date: Optional datetime to filter articles from. Defaults to 24 hours ago.
    """
    if not keywords:
        return []

    cleaned = clean_keywords(keywords)
    query = " OR ".join(cleaned)
    from_date_utc = _normalize_utc(from_date)

    try:
        if not settings.serpapi_key:
            _log(scrape_run_id, "SerpAPI key not found, skipping.", logging.WARNING)
            return []

        _log(scrape_run_id, f"Scraping {len(keywords)} keywords ({query})...")

        params = {
            "q": query,
            "engine": "google_news",
            # "hl": "da",  # Removed to allow broader language results
            # "gl": "dk",  # Removed to allow broader geographic results
            "api_key": settings.serpapi_key,
            "num": 20
        }

        tbs = _build_tbs_from_date(from_date_utc)
        if tbs:
            params["tbs"] = tbs
            _log(scrape_run_id, f"Applying Google News time filter tbs={tbs} for cutoff {from_date_utc.isoformat()}")

        # Use asyncio.to_thread to run the blocking GoogleSearch call
        # This prevents blocking the event loop while waiting for SerpAPI
        def run_search():
            search = GoogleSearch(params)
            return search.get_dict()

        results = await asyncio.to_thread(run_search)

        if "error" in results:
            _log(scrape_run_id, f"SerpAPI error: {results['error']}", logging.ERROR)
            return []

        news_results = results.get("news_results", [])
        _log(scrape_run_id, f"Found {len(news_results)} raw results")

        mentions = []
        for item in news_results:
            # Parse date
            published_parsed = None
            if "date" in item:
                try:
                    # SerpAPI returns relative dates like "2 hours ago" or absolute dates
                    # We'll let dateparser handle it
                    dt = dateparser.parse(item["date"])
                    if dt:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            dt = dt.astimezone(timezone.utc)

                        # Filter by from_date if provided
                        if from_date_utc and dt < from_date_utc:
                            continue

                        published_parsed = dt.timetuple()
                except Exception:
                    # If date parsing fails, default to now or skip?
                    # Let's verify if we should skip
                    pass

            # If no date found/parsed, use current time as fallback
            # (unless from_date strict filtering is required, but better to include than miss)
            if not published_parsed:
                published_parsed = datetime.now(timezone.utc).timetuple()

            mention = {
                "title": item.get("title", "No title"),
                "link": item.get("link", ""),
                "content_teaser": item.get("snippet", ""),
                "published_parsed": published_parsed,
                "platform": item.get("source", {}).get("title", "Google News"),
            }
            mentions.append(mention)

        _log(scrape_run_id, f"Returning {len(mentions)} valid mentions")
        return mentions

    except Exception as e:
        _log(scrape_run_id, f"Scraping failed: {e}", logging.ERROR)
        return []
