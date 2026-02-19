import asyncio
import logging
import uuid
from time import perf_counter
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone

from app.services.scraping.providers.gnews import scrape_gnews
from app.services.scraping.providers.serpapi import scrape_serpapi
from app.services.scraping.providers.configurable import scrape_configurable_sources
from app.services.scraping.providers.rss import scrape_rss
from app.services.scraping.core.text_processing import (
    normalize_url,
    get_platform_from_url,
    clean_keywords,
)
from app.services.scraping.analyzers.relevance_filter import relevance_filter
from app.services.scraping.core.metrics import (
    observe_duplicates_removed,
    observe_provider_run,
)

AI_RELEVANCE_FILTER_TEMP_DISABLED = True
logger = logging.getLogger("scraping")


def _run_log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s%s", prefix, message)


def _normalize_from_date(
    from_date: Optional[datetime],
    lookback_days: int,
    scrape_run_id: Optional[str] = None
) -> datetime:
    now = datetime.now(timezone.utc)
    if from_date is None:
        return now - timedelta(days=lookback_days)

    if from_date.tzinfo is None:
        normalized = from_date.replace(tzinfo=timezone.utc)
    else:
        normalized = from_date.astimezone(timezone.utc)

    if normalized > now:
        _run_log(
            scrape_run_id,
            f"Received future from_date ({normalized.isoformat()}). Clamping to now.",
            logging.WARNING
        )
        return now

    return normalized


async def fetch_all_mentions(
    keywords: List[str],
    lookback_days: int = 1,
    from_date: datetime = None,
    scrape_run_id: Optional[str] = None
) -> List[Dict]:
    """
    Fetch mentions from all sources in parallel using asyncio.gather.

    Benefits:
    - All 4 sources scrape simultaneously (much faster)
    - One failed source doesn't crash the entire batch
    - Returns deduplicated results based on normalized URLs

    Args:
        keywords: List of keywords to search for
        lookback_days: Number of days to look back for mentions (default: 1). Ignored if from_date is set.
        from_date: Explicit datetime cutoff. If set, lookback_days is ignored.
    """
    sanitized_keywords = clean_keywords(keywords)
    if not sanitized_keywords:
        _run_log(scrape_run_id, "No keywords provided for scraping", logging.WARNING)
        return []

    scrape_run_id = scrape_run_id or uuid.uuid4().hex[:10]
    from_date = _normalize_from_date(from_date, lookback_days, scrape_run_id=scrape_run_id)

    _run_log(scrape_run_id, f"Starting parallel scraping with {len(sanitized_keywords)} keywords")
    _run_log(scrape_run_id, f"Keywords: {sanitized_keywords}", logging.DEBUG)
    _run_log(scrape_run_id, f"Fetching articles from {from_date.isoformat()}")

    async def _run_provider(provider_name: str, provider_coro):
        provider_started_at = perf_counter()
        try:
            result = await provider_coro
            if isinstance(result, list):
                observe_provider_run(
                    provider=provider_name,
                    status="success",
                    duration_seconds=perf_counter() - provider_started_at,
                    articles=len(result),
                )
            else:
                observe_provider_run(
                    provider=provider_name,
                    status="unexpected_result",
                    duration_seconds=perf_counter() - provider_started_at,
                    articles=0,
                )
            return result
        except Exception:
            observe_provider_run(
                provider=provider_name,
                status="error",
                duration_seconds=perf_counter() - provider_started_at,
                articles=0,
            )
            raise

    # Run all scrapers in parallel with from_date
    # return_exceptions=True ensures one failure doesn't crash others
    results = await asyncio.gather(
        _run_provider(
            "gnews",
            scrape_gnews(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id),
        ),
        _run_provider(
            "serpapi",
            scrape_serpapi(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id),
        ),
        _run_provider(
            "configurable",
            scrape_configurable_sources(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id),
        ),
        _run_provider(
            "rss",
            scrape_rss(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id),
        ),
        return_exceptions=True
    )

    # Collect all mentions, handling exceptions
    all_mentions = []
    source_names = ["GNews", "SerpAPI", "Configurable Sources", "RSS Feed"]

    for idx, result in enumerate(results):
        source = source_names[idx]
        if isinstance(result, Exception):
            _run_log(scrape_run_id, f"{source} scraping failed with exception: {result}", logging.ERROR)
        elif isinstance(result, list):
            _run_log(scrape_run_id, f"{source}: found {len(result)} articles")
            all_mentions.extend(result)
        else:
            _run_log(scrape_run_id, f"{source}: unexpected result type {type(result)}", logging.WARNING)

    # Deduplicate based on normalized URLs
    seen_links = set()
    unique_mentions = []

    for mention in all_mentions:
        if "link" not in mention or not mention["link"]:
            continue

        normalized = normalize_url(mention["link"])
        if normalized not in seen_links:
            seen_links.add(normalized)

            # Ensure platform is set
            if "platform" not in mention or not mention["platform"]:
                mention["platform"] = get_platform_from_url(mention["link"])

            unique_mentions.append(mention)

    duplicates_removed = len(all_mentions) - len(unique_mentions)
    observe_duplicates_removed(stage="url", count=duplicates_removed)
    _run_log(
        scrape_run_id,
        f"Scraping complete: {len(unique_mentions)} unique mentions ({duplicates_removed} duplicates removed)"
    )

    return unique_mentions


async def fetch_and_filter_mentions(
    keywords: List[str],
    apply_relevance_filter: bool = True,
    lookback_days: int = 1,
    from_date: datetime = None,
    scrape_run_id: Optional[str] = None
) -> List[Dict]:
    """
    Fetch mentions from all sources and optionally filter by AI relevance.

    This is the recommended entry point for scraping with relevance checking.

    Args:
        keywords: List of keywords to search for
        apply_relevance_filter: Whether to run AI relevance filter (default: True)
        lookback_days: Number of days to look back for mentions (default: 1). Ignored if from_date is set.
        from_date: Explicit datetime cutoff. If set, lookback_days is ignored.

    Returns:
        List of relevant mentions (deduplicated)
    """
    scrape_run_id = scrape_run_id or uuid.uuid4().hex[:10]

    # Step 1: Fetch all mentions from sources with lookback
    sanitized_keywords = clean_keywords(keywords)

    mentions = await fetch_all_mentions(
        sanitized_keywords,
        lookback_days=lookback_days,
        from_date=from_date,
        scrape_run_id=scrape_run_id
    )

    if not mentions:
        return []

    # Step 2: Apply AI relevance filter if enabled
    if AI_RELEVANCE_FILTER_TEMP_DISABLED:
        if apply_relevance_filter:
            _run_log(
                scrape_run_id,
                "AI relevance filter is temporarily disabled. Returning unfiltered mentions.",
                logging.WARNING
            )
        return mentions

    if apply_relevance_filter and sanitized_keywords:
        _run_log(scrape_run_id, f"Running AI relevance filter on {len(mentions)} mentions...")
        filtered_mentions = await relevance_filter.filter_mentions(mentions, sanitized_keywords)
        filtered_count = len(mentions) - len(filtered_mentions)
        _run_log(
            scrape_run_id,
            f"Relevance filter: kept {len(filtered_mentions)} mentions ({filtered_count} filtered out)"
        )
        return filtered_mentions

    return mentions
