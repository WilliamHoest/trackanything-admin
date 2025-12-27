import asyncio
from typing import List, Dict

from app.services.scraping.providers.gnews import scrape_gnews
from app.services.scraping.providers.serpapi import scrape_serpapi
from app.services.scraping.providers.configurable import scrape_configurable_sources
from app.services.scraping.providers.rss import scrape_rss
from app.services.scraping.core.text_processing import normalize_url, get_platform_from_url

async def fetch_all_mentions(keywords: List[str]) -> List[Dict]:
    """
    Fetch mentions from all sources in parallel using asyncio.gather.

    Benefits:
    - All 4 sources scrape simultaneously (much faster)
    - One failed source doesn't crash the entire batch
    - Returns deduplicated results based on normalized URLs
    """
    if not keywords:
        print("⚠️ No keywords provided for scraping")
        return []

    print(f"🚀 Starting parallel scraping with {len(keywords)} keywords")
    print(f"📝 Keywords: {keywords}")

    # Run all scrapers in parallel
    # return_exceptions=True ensures one failure doesn't crash others
    results = await asyncio.gather(
        scrape_gnews(keywords),
        scrape_serpapi(keywords),
        scrape_configurable_sources(keywords),
        scrape_rss(keywords),
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
