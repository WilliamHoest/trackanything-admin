import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.services.scraping.core.date_utils import parse_mention_date
from app.services.scraping.core.http_client import TIMEOUT_SECONDS, fetch_with_retry, get_default_headers
from app.services.scraping.core.text_processing import (
    compile_keyword_patterns,
    keyword_match_score,
    normalize_url,
)

logger = logging.getLogger("scraping")

# Danish foundation-specific RSS feeds
# trusted=True: niche fonde-only sources — keyword matching skipped, all articles saved
FONDE_RSS_FEEDS: List[Tuple[str, str, bool]] = [
    ("Filantropi.dk", "https://filantropi.dk/feed/", True),
    ("Impactinsider.dk", "https://impactinsider.dk/feed/", True),
    ("Fundats.dk", "https://fundats.dk/feed/", True),
    ("Altinget Fonde", "https://www.altinget.dk/fonde/rss", False),
]

RSS_ACCEPT_HEADER = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[FONDE_RSS] %s", prefix, message)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_link(entry: Dict) -> str:
    for key in ("link", "id", "guid"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_url(value.strip())
    return ""


def _strip_html(text: str) -> str:
    if not text or "<" not in text:
        return text
    try:
        return BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    except Exception:
        return text


def _rss_headers() -> dict:
    headers = get_default_headers()
    headers["Accept"] = RSS_ACCEPT_HEADER
    # Remove Accept-Encoding so httpx handles decompression automatically.
    # Manually setting it disables httpx's transparent gzip decompression,
    # causing feedparser to receive raw compressed bytes.
    headers.pop("Accept-Encoding", None)
    return headers


async def _fetch_feed(
    platform: str,
    rss_url: str,
    scrape_run_id: Optional[str] = None,
) -> Optional[feedparser.FeedParserDict]:
    headers = _rss_headers()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await fetch_with_retry(
                client,
                rss_url,
                rate_profile="rss",
                metrics_provider="fonde_rss",
                headers=headers,
            )
        feed = await asyncio.to_thread(feedparser.parse, response.content)
        entry_count = len(getattr(feed, "entries", []))
        _log(scrape_run_id, f"{platform}: fetched {entry_count} entries", logging.DEBUG)
        return feed
    except httpx.RemoteProtocolError:
        # Small hosting servers sometimes disconnect under parallel load — retry solo after pause
        _log(scrape_run_id, f"{platform}: RemoteProtocolError, retrying solo in 2s", logging.DEBUG)
        await asyncio.sleep(2)
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.get(rss_url, headers=_rss_headers(), follow_redirects=True)
            feed = await asyncio.to_thread(feedparser.parse, response.content)
            entry_count = len(getattr(feed, "entries", []))
            _log(scrape_run_id, f"{platform}: retry ok, fetched {entry_count} entries", logging.DEBUG)
            return feed
        except Exception as exc:
            _log(scrape_run_id, f"{platform}: fetch failed after retry ({type(exc).__name__}: {exc})", logging.WARNING)
            return None
    except Exception as exc:
        _log(scrape_run_id, f"{platform}: fetch failed ({type(exc).__name__}: {exc})", logging.WARNING)
        return None


async def scrape_fonde_rss(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
) -> List[Dict]:
    if not keywords:
        return []

    since = _normalize_utc(from_date) or (datetime.now(timezone.utc) - timedelta(hours=24))
    patterns = compile_keyword_patterns(keywords)

    mentions: List[Dict] = []
    seen_links: set[str] = set()

    _log(scrape_run_id, f"Fetching {len(FONDE_RSS_FEEDS)} feeds with {len(keywords)} keywords, since={since.isoformat()}")

    feed_results = await asyncio.gather(
        *[
            _fetch_feed(platform, url, scrape_run_id)
            for platform, url, _ in FONDE_RSS_FEEDS
        ],
        return_exceptions=True,
    )

    for (platform, _, trusted), feed in zip(FONDE_RSS_FEEDS, feed_results):
        if feed is None or isinstance(feed, Exception):
            continue

        entries = list(getattr(feed, "entries", []) or [])
        kept = 0

        for entry in entries:
            try:
                raw_date = (
                    entry.get("published_parsed")
                    or entry.get("updated_parsed")
                    or entry.get("published")
                )
                published_dt = parse_mention_date(raw_date)
                if published_dt is None or published_dt < since:
                    continue

                title = entry.get("title", "").strip()
                summary = _strip_html(entry.get("summary", ""))

                if not trusted and patterns and keyword_match_score(patterns, f"{title}\n{summary}") < 1:
                    continue

                link = _extract_link(entry)
                if not link or link in seen_links:
                    continue
                seen_links.add(link)

                mentions.append({
                    "title": title,
                    "link": link,
                    "content_teaser": summary[:200],
                    "platform": platform,
                    "published_parsed": published_dt.timetuple(),
                    "trusted_source": trusted,
                })
                kept += 1

            except Exception as exc:
                _log(scrape_run_id, f"{platform}: entry error ({exc})", logging.WARNING)

        _log(scrape_run_id, f"{platform}: kept {kept}/{len(entries)}")

    _log(scrape_run_id, f"Total: {len(mentions)} mentions from fonde RSS feeds")
    return mentions
