import feedparser
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
import logging

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

            # feedparser er blokerende, så vi kører det i en thread
            feed = await asyncio.to_thread(feedparser.parse, url)

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
            _log(scrape_run_id, f"Error for '{keyword}': {e}", logging.WARNING)
            continue

    _log(scrape_run_id, f"Found {len(mentions)} articles")
    return mentions
