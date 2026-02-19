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


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    total_entries_seen = 0
    total_kept = 0
    total_before_cutoff = 0
    total_missing_date = 0
    total_unparseable_date = 0
    total_parse_errors = 0

    # Vi bruger Google News RSS endpoint som en gratis "hack"
    # Det giver os data uden API key limits (dog med rate limits)
    base_url = "https://news.google.com/rss/search?q={}&hl=da&gl=DK&ceid=DK:da"

    # Use provided from_date or default to 24 hours ago
    explicit_cutoff = _normalize_utc(from_date)
    since = explicit_cutoff or (datetime.now(timezone.utc) - timedelta(hours=24))

    _log(scrape_run_id, f"Scraping {len(keywords)} keyword(s) via Google News RSS...")
    _log(
        scrape_run_id,
        f"Applying strict cutoff since={since.isoformat()} (explicit_from_date={explicit_cutoff is not None})",
    )

    for keyword in keywords:
        try:
            url = base_url.format(keyword.replace(" ", "+"))
            keyword_entries_seen = 0
            keyword_kept = 0
            keyword_before_cutoff = 0
            keyword_missing_date = 0
            keyword_unparseable_date = 0
            keyword_parse_errors = 0

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
            _log(
                scrape_run_id,
                f"Keyword '{keyword}': feed status={status_code}",
                logging.DEBUG,
            )

            status_numeric = int(status_code) if status_code.isdigit() else 200
            if status_numeric >= 400:
                _log(
                    scrape_run_id,
                    f"Keyword '{keyword}': feed returned HTTP {status_code} (possible throttle/limit)",
                    logging.WARNING,
                )
                observe_http_error(
                    provider="rss",
                    domain=etld1,
                    error_type=f"http_{status_code}",
                )

            if getattr(feed, "bozo", 0):
                bozo_exception = getattr(feed, "bozo_exception", None)
                _log(
                    scrape_run_id,
                    f"Keyword '{keyword}': feed parser bozo=1 ({bozo_exception})",
                    logging.WARNING,
                )

            if not hasattr(feed, 'entries'):
                _log(scrape_run_id, f"Keyword '{keyword}': no entries attribute in feed", logging.WARNING)
                continue

            keyword_entries_seen = len(feed.entries)
            for entry in feed.entries:
                try:
                    # Parse published date - skip articles without parsable date
                    published_parsed = entry.get("published_parsed")
                    if not published_parsed:
                        keyword_missing_date += 1
                        continue
                    try:
                        published_dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        keyword_unparseable_date += 1
                        continue

                    # Skip old articles
                    if published_dt < since:
                        keyword_before_cutoff += 1
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
                    keyword_kept += 1
                    _log(scrape_run_id, f"Match: {entry.get('title', 'Ingen titel')[:60]}", logging.DEBUG)

                except Exception as entry_error:
                    keyword_parse_errors += 1
                    _log(scrape_run_id, f"Entry parse error: {entry_error}", logging.WARNING)
                    continue

            total_entries_seen += keyword_entries_seen
            total_kept += keyword_kept
            total_before_cutoff += keyword_before_cutoff
            total_missing_date += keyword_missing_date
            total_unparseable_date += keyword_unparseable_date
            total_parse_errors += keyword_parse_errors
            _log(
                scrape_run_id,
                (
                    f"Keyword '{keyword}' summary: entries={keyword_entries_seen}, "
                    f"kept={keyword_kept}, before_cutoff={keyword_before_cutoff}, "
                    f"missing_date={keyword_missing_date}, unparseable_date={keyword_unparseable_date}, "
                    f"parse_errors={keyword_parse_errors}"
                ),
            )

        except Exception as e:
            observe_http_error(
                provider="rss",
                domain=get_etld_plus_one(url),
                error_type=type(e).__name__,
            )
            _log(scrape_run_id, f"Error for '{keyword}': {e}", logging.WARNING)
            continue

    _log(
        scrape_run_id,
        (
            f"Found {len(mentions)} articles. Totals: entries={total_entries_seen}, "
            f"kept={total_kept}, before_cutoff={total_before_cutoff}, "
            f"missing_date={total_missing_date}, unparseable_date={total_unparseable_date}, "
            f"parse_errors={total_parse_errors}"
        ),
    )
    return mentions
