import feedparser
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from time import perf_counter
import logging

from app.services.scraping.core.domain_utils import get_etld_plus_one
from app.services.scraping.core.metrics import observe_http_error, observe_http_request
from app.services.scraping.core.rate_limit import get_domain_limiter

logger = logging.getLogger("scraping")


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[RSS] %s", prefix, message)


async def scrape_rss(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None
) -> List[Dict]:
    """
    Scraper RSS feeds via Google News RSS endpoint.

    NOTE: Da vi søger på keywords, er RSS lidt tricky.
    Normalt abonnerer man på et feed URL.
    Her laver vi en Google News RSS søgning som fallback/gratis alternativ.
    Dette giver os data uden API key limits (dog med rate limits).
    
    Args:
        keywords: List of keywords to search for
        from_date: Optional datetime to filter articles from. Defaults to 24 hours ago.
    """
    if not keywords:
        _log(scrape_run_id, "No keywords provided for RSS scraping", logging.WARNING)
        return []

    mentions = []

    # Vi bruger Google News RSS endpoint som en gratis "hack"
    # Det giver os data uden API key limits (dog med rate limits)
    base_url = "https://news.google.com/rss/search?q={}&hl=da&gl=DK&ceid=DK:da"

    # Use provided from_date or default to 24 hours ago
    since = from_date if from_date else datetime.now(timezone.utc) - timedelta(hours=24)

    _log(scrape_run_id, f"Scraping {len(keywords)} keyword(s) via Google News RSS...")

    for keyword in keywords:
        try:
            url = base_url.format(keyword.replace(" ", "+"))

            # Apply per-domain RSS rate control before outbound request.
            etld1 = get_etld_plus_one(url)
            limiter = get_domain_limiter(etld1, profile="rss")
            request_started_at = perf_counter()
            async with limiter:
                # feedparser is blocking, so we run it in a thread.
                feed = await asyncio.to_thread(feedparser.parse, url)
            status_code = str(getattr(feed, "status", 200))
            observe_http_request(
                provider="rss",
                domain=etld1,
                status_code=status_code,
                duration_seconds=perf_counter() - request_started_at,
            )

            if not hasattr(feed, 'entries'):
                continue

            for entry in feed.entries:
                try:
                    # Parse published date - skip articles without parsable date
                    published_parsed = entry.get("published_parsed")
                    if not published_parsed:
                        continue
                    published_dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)

                    # Skip old articles
                    if published_dt < since:
                        continue

                    # Extract link (Google News RSS wraps the real link)
                    link = entry.get("link", "")

                    mentions.append({
                        "title": entry.get("title", "Ingen titel"),
                        "link": link,
                        "content_teaser": entry.get("summary", "")[:200],
                        "platform": "Google RSS",
                        "published_parsed": published_parsed,
                    })
                    _log(scrape_run_id, f"Match: {entry.get('title', 'Ingen titel')[:60]}", logging.DEBUG)

                except Exception as entry_error:
                    _log(scrape_run_id, f"Entry parse error: {entry_error}", logging.WARNING)
                    continue

        except Exception as e:
            observe_http_error(
                provider="rss",
                domain=get_etld_plus_one(url),
                error_type=type(e).__name__,
            )
            _log(scrape_run_id, f"Error for '{keyword}': {e}", logging.WARNING)
            continue

    _log(scrape_run_id, f"Found {len(mentions)} articles")
    return mentions
