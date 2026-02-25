import asyncio
import logging
import uuid
from time import perf_counter
from typing import Any, Awaitable, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

from app.services.scraping.providers.gnews import scrape_gnews
from app.services.scraping.providers.serpapi import scrape_serpapi
from app.services.scraping.providers.configurable import scrape_configurable_sources
from app.services.scraping.providers.rss import scrape_rss
from app.services.scraping.core.date_utils import parse_mention_date, is_within_interval
from app.services.scraping.core.text_processing import (
    normalize_url,
    get_platform_from_url,
    clean_keywords,
)
from app.services.scraping.core.deduplication import near_deduplicate_mentions
from app.services.scraping.core.language_filter import filter_by_language
from app.services.scraping.analyzers.relevance_filter import relevance_filter
from app.services.scraping.core.metrics import (
    observe_duplicates_removed,
    observe_guardrail_event,
    observe_provider_run,
)
from app.services.scraping.core.run_artifacts import (
    write_mentions_snapshot,
    write_run_metadata,
)
from app.core.config import settings

AI_RELEVANCE_FILTER_ENABLED = True
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
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
    artifact_label: Optional[str] = None,
) -> List[Dict]:
    """
    Fetch mentions from all sources in parallel using asyncio.gather.

    Benefits:
    - All enabled sources scrape simultaneously (much faster)
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

    max_keywords = max(1, int(settings.scraping_max_keywords_per_run))
    if len(sanitized_keywords) > max_keywords:
        dropped = len(sanitized_keywords) - max_keywords
        sanitized_keywords = sanitized_keywords[:max_keywords]
        _run_log(
            scrape_run_id,
            (
                f"Keyword guardrail triggered: truncating keyword set to {max_keywords} "
                f"(dropped {dropped})"
            ),
            logging.WARNING,
        )
        observe_guardrail_event(
            "max_keywords_per_run",
            "orchestrator",
            "truncate",
            count=dropped,
        )

    scrape_run_id = scrape_run_id or uuid.uuid4().hex[:10]
    from_date = _normalize_from_date(from_date, lookback_days, scrape_run_id=scrape_run_id)

    _run_log(scrape_run_id, f"Starting parallel scraping with {len(sanitized_keywords)} keywords")
    _run_log(scrape_run_id, f"Keywords: {sanitized_keywords}", logging.DEBUG)
    _run_log(scrape_run_id, f"Fetching articles from {from_date.isoformat()}")
    provider_toggles = {
        "gnews": settings.scraping_provider_gnews_enabled,
        "serpapi": settings.scraping_provider_serpapi_enabled,
        "configurable": settings.scraping_provider_configurable_enabled,
        "rss": settings.scraping_provider_rss_enabled,
    }
    _run_log(
        scrape_run_id,
        (
            "Provider toggles: "
            f"gnews={provider_toggles['gnews']}, "
            f"serpapi={provider_toggles['serpapi']}, "
            f"configurable={provider_toggles['configurable']}, "
            f"rss={provider_toggles['rss']}"
        ),
    )
    write_run_metadata(
        scrape_run_id,
        {
            "run_id": scrape_run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "keywords": sanitized_keywords,
            "keyword_count": len(sanitized_keywords),
            "from_date": from_date.isoformat(),
            "lookback_days": lookback_days,
            "provider_toggles": provider_toggles,
        },
        artifact_label=artifact_label,
    )

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

    enabled_providers: List[Tuple[str, str, Awaitable[Any]]] = []

    if settings.scraping_provider_gnews_enabled:
        enabled_providers.append(
            (
                "gnews",
                "GNews",
                scrape_gnews(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id, allowed_languages=allowed_languages),
            )
        )
    else:
        observe_guardrail_event("provider_toggle", "gnews", "disabled")
        _run_log(scrape_run_id, "GNews provider disabled by config", logging.INFO)

    if settings.scraping_provider_serpapi_enabled:
        enabled_providers.append(
            (
                "serpapi",
                "SerpAPI",
                scrape_serpapi(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id, allowed_languages=allowed_languages),
            )
        )
    else:
        observe_guardrail_event("provider_toggle", "serpapi", "disabled")
        _run_log(scrape_run_id, "SerpAPI provider disabled by config", logging.INFO)

    if settings.scraping_provider_configurable_enabled:
        enabled_providers.append(
            (
                "configurable",
                "Configurable Sources",
                scrape_configurable_sources(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id, allowed_languages=allowed_languages),
            )
        )
    else:
        observe_guardrail_event("provider_toggle", "configurable", "disabled")
        _run_log(scrape_run_id, "Configurable provider disabled by config", logging.INFO)

    if settings.scraping_provider_rss_enabled:
        enabled_providers.append(
            (
                "rss",
                "RSS Feed",
                scrape_rss(sanitized_keywords, from_date=from_date, scrape_run_id=scrape_run_id, allowed_languages=allowed_languages),
            )
        )
    else:
        observe_guardrail_event("provider_toggle", "rss", "disabled")
        _run_log(scrape_run_id, "RSS provider disabled by config", logging.INFO)

    if not enabled_providers:
        _run_log(scrape_run_id, "All providers are disabled by config; skipping scrape run", logging.WARNING)
        observe_guardrail_event("provider_toggle", "orchestrator", "all_disabled")
        return []

    # Run enabled scrapers in parallel with from_date.
    # return_exceptions=True ensures one failure doesn't crash others.
    results = await asyncio.gather(
        *[_run_provider(provider_name, provider_coro) for provider_name, _, provider_coro in enabled_providers],
        return_exceptions=True
    )

    # Collect all mentions, handling exceptions
    all_mentions: List[Dict[str, Any]] = []
    provider_outcomes: List[Dict[str, Any]] = []
    for idx, result in enumerate(results):
        provider_name, source, _provider_coro = enabled_providers[idx]
        if isinstance(result, Exception):
            _run_log(scrape_run_id, f"{source} scraping failed with exception: {result}", logging.ERROR)
            provider_outcomes.append(
                {
                    "provider": provider_name,
                    "source": source,
                    "status": "exception",
                    "error": str(result),
                    "mentions": 0,
                }
            )
        elif isinstance(result, list):
            _run_log(scrape_run_id, f"{source}: found {len(result)} articles")
            annotated_mentions: List[Dict[str, Any]] = []
            for mention in result:
                if not isinstance(mention, dict):
                    continue
                enriched = dict(mention)
                enriched.setdefault("source_provider", provider_name)
                enriched.setdefault("source_label", source)
                annotated_mentions.append(enriched)
            provider_outcomes.append(
                {
                    "provider": provider_name,
                    "source": source,
                    "status": "success",
                    "mentions": len(annotated_mentions),
                }
            )
            all_mentions.extend(annotated_mentions)
        else:
            _run_log(scrape_run_id, f"{source}: unexpected result type {type(result)}", logging.WARNING)
            provider_outcomes.append(
                {
                    "provider": provider_name,
                    "source": source,
                    "status": "unexpected_result",
                    "mentions": 0,
                    "result_type": str(type(result)),
                }
            )

    write_mentions_snapshot(
        scrape_run_id,
        "01_raw_provider_output",
        all_mentions,
        metadata={"providers": provider_outcomes},
        artifact_label=artifact_label,
    )

    # Apply global date interval filter
    interval_filtered_mentions = []
    date_filter_removed_missing_or_unparseable = 0
    date_filter_removed_before_cutoff = 0
    for mention in all_mentions:
        raw_date = mention.get("published_parsed") or mention.get("date")
        parsed_dt = parse_mention_date(raw_date)
        mention_link = mention.get("link", "no-link")

        if from_date is not None:
            parsed_dt_iso = parsed_dt.isoformat() if parsed_dt else "None"
            within_interval = bool(parsed_dt and is_within_interval(parsed_dt, from_date))
            _run_log(
                scrape_run_id,
                (
                    f"Global date filter evaluation for {mention_link}: "
                    f"raw_date={raw_date!r}, "
                    f"parsed_date={parsed_dt_iso}, "
                    f"cutoff={from_date.isoformat()}, "
                    f"within_interval={within_interval}"
                ),
                logging.DEBUG,
            )
            # Strict guardrail: require a parseable date when interval filtering is active.
            if parsed_dt is None:
                _run_log(scrape_run_id, f"Global date filter skipped {mention_link}: unparseable/missing date", logging.DEBUG)
                date_filter_removed_missing_or_unparseable += 1
                continue
            if not within_interval:
                _run_log(scrape_run_id, f"Global date filter skipped {mention_link}: before cutoff", logging.DEBUG)
                date_filter_removed_before_cutoff += 1
                continue
        interval_filtered_mentions.append(mention)
    
    all_mentions = interval_filtered_mentions
    write_mentions_snapshot(
        scrape_run_id,
        "02_after_global_date_filter",
        all_mentions,
        metadata={
            "removed_missing_or_unparseable_date": date_filter_removed_missing_or_unparseable,
            "removed_before_cutoff": date_filter_removed_before_cutoff,
            "cutoff": from_date.isoformat() if from_date else None,
        },
        artifact_label=artifact_label,
    )

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

    url_duplicates_removed = len(all_mentions) - len(unique_mentions)
    observe_duplicates_removed(stage="url", count=url_duplicates_removed)
    write_mentions_snapshot(
        scrape_run_id,
        "03_after_url_dedup",
        unique_mentions,
        metadata={"url_duplicates_removed": url_duplicates_removed},
        artifact_label=artifact_label,
    )

    dedupe_threshold = settings.scraping_fuzzy_dedup_threshold
    dedupe_day_window = settings.scraping_fuzzy_dedup_day_window
    if settings.scraping_fuzzy_dedup_enabled:
        unique_mentions, fuzzy_duplicates_removed = near_deduplicate_mentions(
            unique_mentions,
            threshold=dedupe_threshold,
            day_window=dedupe_day_window,
        )
    else:
        fuzzy_duplicates_removed = 0

    observe_duplicates_removed(stage="fuzzy", count=fuzzy_duplicates_removed)
    duplicates_removed = url_duplicates_removed + fuzzy_duplicates_removed
    write_mentions_snapshot(
        scrape_run_id,
        "04_after_fuzzy_dedup",
        unique_mentions,
        metadata={
            "fuzzy_duplicates_removed": fuzzy_duplicates_removed,
            "url_duplicates_removed": url_duplicates_removed,
            "total_duplicates_removed": duplicates_removed,
            "fuzzy_threshold": dedupe_threshold,
            "fuzzy_day_window": dedupe_day_window,
        },
        artifact_label=artifact_label,
    )

    # Language filtering (after dedup, before AI relevance filter)
    if settings.scraping_language_filter_enabled and allowed_languages:
        unique_mentions, lang_removed = filter_by_language(
            unique_mentions, allowed_languages, scrape_run_id=scrape_run_id
        )
        observe_duplicates_removed(stage="language_filter", count=lang_removed)
        _run_log(scrape_run_id, f"Language filter removed {lang_removed} mentions (allowed={allowed_languages})")

    _run_log(
        scrape_run_id,
        (
            f"Scraping complete: {len(unique_mentions)} unique mentions "
            f"({duplicates_removed} duplicates removed: "
            f"url={url_duplicates_removed}, fuzzy={fuzzy_duplicates_removed})"
        )
    )

    return unique_mentions


async def fetch_and_filter_mentions(
    keywords: List[str],
    apply_relevance_filter: bool = True,
    lookback_days: int = 1,
    from_date: datetime = None,
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
    artifact_label: Optional[str] = None,
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
        scrape_run_id=scrape_run_id,
        allowed_languages=allowed_languages,
        artifact_label=artifact_label,
    )

    if not mentions:
        return []

    write_mentions_snapshot(
        scrape_run_id,
        "05_before_ai_filter",
        mentions,
        metadata={"apply_relevance_filter": apply_relevance_filter},
        artifact_label=artifact_label,
    )

    # Step 2: Apply AI relevance filter if enabled
    if not AI_RELEVANCE_FILTER_ENABLED:
        if apply_relevance_filter:
            _run_log(
                scrape_run_id,
                "AI relevance filter is temporarily disabled. Returning unfiltered mentions.",
                logging.WARNING
            )
        write_mentions_snapshot(
            scrape_run_id,
            "06_after_ai_filter_skipped",
            mentions,
            metadata={"reason": "ai_filter_disabled"},
            artifact_label=artifact_label,
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
        write_mentions_snapshot(
            scrape_run_id,
            "06_after_ai_filter",
            filtered_mentions,
            metadata={
                "input_mentions": len(mentions),
                "kept_mentions": len(filtered_mentions),
                "filtered_out": filtered_count,
            },
            artifact_label=artifact_label,
        )
        return filtered_mentions

    write_mentions_snapshot(
        scrape_run_id,
        "06_after_ai_filter_skipped",
        mentions,
        metadata={"reason": "apply_relevance_filter_false_or_no_keywords"},
        artifact_label=artifact_label,
    )
    return mentions
