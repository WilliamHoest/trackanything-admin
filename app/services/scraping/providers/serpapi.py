from typing import List, Dict, Optional
from datetime import datetime, timezone
import asyncio
import logging
from time import perf_counter
from dateutil import parser as dateparser
from serpapi import GoogleSearch

from app.core.config import settings
from app.services.scraping.core.text_processing import clean_keywords
from app.services.scraping.core.domain_utils import get_etld_plus_one
from app.services.scraping.core.metrics import observe_http_error, observe_http_request
from app.services.scraping.core.rate_limit import get_domain_limiter

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


def _detect_limit_signal(error_message: str) -> Optional[str]:
    message = (error_message or "").lower()
    if not message:
        return None

    if "rate limit" in message or "too many requests" in message:
        return "rate_limit"
    if "quota" in message or "searches left" in message:
        return "quota"
    if "monthly" in message and "search" in message:
        return "quota"
    if "insufficient" in message and "balance" in message:
        return "quota"
    if "limit reached" in message:
        return "limit_reached"
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

        # Apply per-domain API rate control before outbound SerpAPI request.
        etld1 = get_etld_plus_one("https://serpapi.com")
        limiter = get_domain_limiter(etld1, profile="api")
        request_started_at = perf_counter()
        async with limiter:
            results = await asyncio.to_thread(run_search)
        status_code = "200" if "error" not in results else "api_error"
        request_duration = perf_counter() - request_started_at
        observe_http_request(
            provider="serpapi",
            domain=etld1,
            status_code=status_code,
            duration_seconds=request_duration,
        )

        metadata = results.get("search_metadata", {})
        meta_status = metadata.get("status", "unknown")
        news_results = results.get("news_results", [])
        _log(
            scrape_run_id,
            (
                f"Response: status={meta_status}, http_metric={status_code}, "
                f"duration={request_duration:.2f}s, news_results={len(news_results)}"
            ),
        )

        if "error" in results:
            error_message = str(results.get("error", "Unknown SerpAPI error"))
            limit_signal = _detect_limit_signal(error_message)
            if limit_signal:
                _log(
                    scrape_run_id,
                    f"Possible SerpAPI {limit_signal} detected: {error_message}",
                    logging.WARNING,
                )
            else:
                _log(scrape_run_id, f"SerpAPI error: {error_message}", logging.ERROR)
            observe_http_error(
                provider="serpapi",
                domain=etld1,
                error_type=f"api_{limit_signal or 'error'}",
            )
            return []

        _log(scrape_run_id, f"Found {len(news_results)} raw results")
        if not news_results:
            _log(
                scrape_run_id,
                "No news_results returned by SerpAPI (empty result set).",
                logging.WARNING,
            )

        mentions = []
        skipped_before_cutoff = 0
        skipped_missing_date = 0
        skipped_unparseable_date = 0
        for item in news_results:
            raw_date = item.get("date")
            parsed_dt: Optional[datetime] = None

            if raw_date:
                try:
                    # SerpAPI returns relative dates like "2 hours ago" or absolute dates.
                    parsed_dt = dateparser.parse(raw_date)
                except Exception:
                    parsed_dt = None

                if parsed_dt is not None:
                    if parsed_dt.tzinfo is None:
                        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                    else:
                        parsed_dt = parsed_dt.astimezone(timezone.utc)

            # Strict mode when cutoff is active:
            # require a parseable date and enforce exact cutoff.
            if from_date_utc is not None:
                if not raw_date:
                    skipped_missing_date += 1
                    continue
                if parsed_dt is None:
                    skipped_unparseable_date += 1
                    continue
                if parsed_dt < from_date_utc:
                    skipped_before_cutoff += 1
                    continue

            if parsed_dt is None:
                parsed_dt = datetime.now(timezone.utc)

            mention = {
                "title": item.get("title", "No title"),
                "link": item.get("link", ""),
                "content_teaser": item.get("snippet", ""),
                "published_parsed": parsed_dt.timetuple(),
                "platform": item.get("source", {}).get("title", "Google News"),
            }
            mentions.append(mention)

        _log(
            scrape_run_id,
            (
                f"Returning {len(mentions)} valid mentions "
                f"(skipped_before_cutoff={skipped_before_cutoff}, "
                f"skipped_missing_date={skipped_missing_date}, "
                f"skipped_unparseable_date={skipped_unparseable_date})"
            ),
        )
        return mentions

    except Exception as e:
        observe_http_error(
            provider="serpapi",
            domain=get_etld_plus_one("https://serpapi.com"),
            error_type=type(e).__name__,
        )
        _log(scrape_run_id, f"Scraping failed: {type(e).__name__}: {e}", logging.ERROR)
        return []
