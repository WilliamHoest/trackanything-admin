import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone

from app.services.scraping.providers.gnews import scrape_gnews
from app.services.scraping.providers.serpapi import scrape_serpapi
from app.services.scraping.providers.configurable import scrape_configurable_sources
from app.services.scraping.providers.rss import scrape_rss
from app.services.scraping.core.text_processing import normalize_url, get_platform_from_url
from app.services.scraping.analyzers.relevance_filter import relevance_filter

AI_RELEVANCE_FILTER_TEMP_DISABLED = True


def _normalize_from_date(from_date: Optional[datetime], lookback_days: int) -> datetime:
    now = datetime.now(timezone.utc)
    if from_date is None:
        return now - timedelta(days=lookback_days)

    if from_date.tzinfo is None:
        normalized = from_date.replace(tzinfo=timezone.utc)
    else:
        normalized = from_date.astimezone(timezone.utc)

    if normalized > now:
        print(f"⚠️ Received future from_date ({normalized.isoformat()}). Clamping to now.")
        return now

    return normalized


async def fetch_all_mentions(keywords: List[str], lookback_days: int = 1, from_date: datetime = None) -> List[Dict]:
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
    if not keywords:
        print("⚠️ No keywords provided for scraping")
        return []

    from_date = _normalize_from_date(from_date, lookback_days)

    print(f"🚀 Starting parallel scraping with {len(keywords)} keywords")
    print(f"📝 Keywords: {keywords}")
    print(f"📅 Fetching articles from {from_date.isoformat()}")

    # Run all scrapers in parallel with from_date
    # return_exceptions=True ensures one failure doesn't crash others
    results = await asyncio.gather(
        scrape_gnews(keywords, from_date=from_date),
        scrape_serpapi(keywords, from_date=from_date),
        scrape_configurable_sources(keywords, from_date=from_date),
        scrape_rss(keywords, from_date=from_date),
        return_exceptions=True
    )

    # Collect all mentions, handling exceptions
    all_mentions = []
    source_names = ["GNews", "SerpAPI", "Configurable Sources", "RSS Feed"]

    for idx, result in enumerate(results):
        source = source_names[idx]
        if isinstance(result, Exception):
            print(f"❌ {source} scraping failed with exception: {result}")
        elif isinstance(result, list):
            print(f"✅ {source}: found {len(result)} articles")
            all_mentions.extend(result)
        else:
            print(f"⚠️ {source}: unexpected result type {type(result)}")

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
    print(f"✅ Scraping complete: {len(unique_mentions)} unique mentions ({duplicates_removed} duplicates removed)")

    return unique_mentions


async def fetch_and_filter_mentions(
    keywords: List[str],
    apply_relevance_filter: bool = True,
    lookback_days: int = 1,
    from_date: datetime = None
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
    # Step 1: Fetch all mentions from sources with lookback
    mentions = await fetch_all_mentions(keywords, lookback_days=lookback_days, from_date=from_date)

    if not mentions:
        return []

    # Step 2: Apply AI relevance filter if enabled
    if AI_RELEVANCE_FILTER_TEMP_DISABLED:
        if apply_relevance_filter:
            print("⚠️ AI relevance filter is temporarily disabled. Returning unfiltered mentions.")
        return mentions

    if apply_relevance_filter and keywords:
        print(f"🤖 Running AI relevance filter on {len(mentions)} mentions...")
        filtered_mentions = await relevance_filter.filter_mentions(mentions, keywords)
        filtered_count = len(mentions) - len(filtered_mentions)
        print(f"✅ Relevance filter: kept {len(filtered_mentions)} mentions ({filtered_count} filtered out)")
        return filtered_mentions

    return mentions
