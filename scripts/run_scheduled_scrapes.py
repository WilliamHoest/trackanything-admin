#!/usr/bin/env python3
"""
Scheduled Scraping Script for TrackAnything

This script is designed to be run by a cron job (e.g., Railway Cron Jobs).
It fetches all active brands, determines which ones are due for scraping
based on their scrape_frequency_hours, and processes them.

Railway Cron Job example (run every hour):
0 * * * * python scripts/run_scheduled_scrapes.py
"""

import sys
import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set
from pathlib import Path

# Add parent directory to path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure environment variables are loaded
from dotenv import load_dotenv
load_dotenv()

from app.core.supabase_client import get_supabase_admin
from app.services.scraping.orchestrator import fetch_all_mentions

# Configure logging for Railway (stdout/stderr only, no file handlers)
def setup_cron_logging():
    """
    Configure logging optimized for Railway Cron Jobs.
    Logs to stdout only (no files) for Railway's log aggregation.
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Set levels for noisy libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    return logging.getLogger(__name__)

# Initialize logger
logger = setup_cron_logging()


# Global platform cache to avoid repeated DB lookups
_platform_cache: Dict[str, int] = {}

async def load_platform_cache(supabase) -> None:
    """Pre-load all platforms into cache for fast lookup."""
    global _platform_cache
    try:
        result = supabase.table("platforms").select("id, name").execute()
        _platform_cache = {p["name"]: p["id"] for p in result.data}
        logger.info(f"📦 Loaded {len(_platform_cache)} platforms into cache")
    except Exception as e:
        logger.error(f"Error loading platform cache: {e}")
        _platform_cache = {}

async def get_platform_id(supabase, platform_name: str) -> int:
    """Get or create platform ID from platforms table (with caching)."""
    global _platform_cache

    # Check cache first
    if platform_name in _platform_cache:
        return _platform_cache[platform_name]

    try:
        # Create new platform if it doesn't exist
        insert_result = supabase.table("platforms").insert({"name": platform_name}).execute()
        platform_id = insert_result.data[0]["id"]
        _platform_cache[platform_name] = platform_id
        logger.info(f"Created new platform: {platform_name}")
        return platform_id

    except Exception as e:
        logger.error(f"Error getting platform ID for '{platform_name}': {e}")
        return 1


async def try_acquire_brand_scrape_lock(supabase, brand_id: int, stale_after_minutes: int = 180) -> bool:
    """Try to acquire cross-process scrape lock for a brand."""
    try:
        now = datetime.now(timezone.utc)
        stale_cutoff = (now - timedelta(minutes=stale_after_minutes)).isoformat()

        # Clear stale lock (best effort)
        supabase.table("brands").update({
            "scrape_in_progress": False,
            "scrape_started_at": None
        }).eq("id", brand_id).eq("scrape_in_progress", True).lt("scrape_started_at", stale_cutoff).execute()

        # Acquire lock if brand is free
        result = supabase.table("brands").update({
            "scrape_in_progress": True,
            "scrape_started_at": now.isoformat()
        }).eq("id", brand_id).eq("scrape_in_progress", False).execute()

        return len(result.data or []) > 0
    except Exception as e:
        message = str(e).lower()
        if "scrape_in_progress" in message or "scrape_started_at" in message:
            logger.warning("Scrape lock columns missing; continuing without DB lock (run migration 009).")
            return True
        logger.error(f"Error acquiring lock for brand {brand_id}: {e}")
        return False


async def release_brand_scrape_lock(supabase, brand_id: int) -> bool:
    """Release scrape lock for a brand."""
    try:
        result = supabase.table("brands").update({
            "scrape_in_progress": False,
            "scrape_started_at": None
        }).eq("id", brand_id).execute()
        return len(result.data or []) > 0
    except Exception as e:
        message = str(e).lower()
        if "scrape_in_progress" in message or "scrape_started_at" in message:
            return True
        logger.error(f"Error releasing lock for brand {brand_id}: {e}")
        return False


async def scrape_brand(supabase, brand: Dict) -> Dict:
    """
    Scrape mentions for a single brand.

    Returns a dict with status info:
    {
        "brand_id": int,
        "brand_name": str,
        "success": bool,
        "mentions_found": int,
        "mentions_saved": int,
        "error": str or None
    }
    """
    brand_id = brand["id"]
    brand_name = brand["name"]

    logger.info("="*60)
    logger.info(f"🔍 Processing Brand: {brand_name} (ID: {brand_id})")
    logger.info("="*60)

    lock_acquired = False
    run_started_at = datetime.now(timezone.utc)

    try:
        lock_acquired = await try_acquire_brand_scrape_lock(supabase, brand_id)
        if not lock_acquired:
            logger.warning(f"⏭️  Skipping '{brand_name}' because another scrape is already running")
            return {
                "brand_id": brand_id,
                "brand_name": brand_name,
                "success": True,
                "mentions_found": 0,
                "mentions_saved": 0,
                "error": "Scrape already in progress"
            }

        # 1. Fetch all active topics for this brand
        topics_result = supabase.table("topics").select("id, name").eq("brand_id", brand_id).eq("is_active", True).execute()

        if not topics_result.data:
            logger.warning(f"No active topics found for brand '{brand_name}'. Skipping.")
            return {
                "brand_id": brand_id,
                "brand_name": brand_name,
                "success": True,
                "mentions_found": 0,
                "mentions_saved": 0,
                "error": "No active topics"
            }

        topics = topics_result.data
        logger.info(f"📋 Found {len(topics)} active topic(s)")

        # 2. Collect all keywords across all topics
        all_keywords = []
        topic_keyword_map = {}  # Map keyword -> list of topic_ids that use it

        for topic in topics:
            topic_id = topic["id"]
            topic_name = topic["name"]

            # Get keywords for this topic via junction table
            keywords_result = supabase.table("topic_keywords")\
                .select("keyword_id, keywords(text)")\
                .eq("topic_id", topic_id)\
                .execute()

            topic_keywords = []
            for row in keywords_result.data:
                if row.get("keywords") and row["keywords"].get("text"):
                    keyword_text = row["keywords"]["text"]
                    topic_keywords.append(keyword_text)

                    # Track which topics use this keyword
                    if keyword_text not in topic_keyword_map:
                        topic_keyword_map[keyword_text] = []
                    topic_keyword_map[keyword_text].append(topic_id)

            if topic_keywords:
                all_keywords.extend(topic_keywords)
                logger.info(f"  📌 Topic '{topic_name}': {len(topic_keywords)} keyword(s)")

        if not all_keywords:
            logger.warning(f"No keywords found for brand '{brand_name}'. Skipping.")
            return {
                "brand_id": brand_id,
                "brand_name": brand_name,
                "success": True,
                "mentions_found": 0,
                "mentions_saved": 0,
                "error": "No keywords"
            }

        # Remove duplicates while preserving order
        unique_keywords = list(dict.fromkeys(all_keywords))
        logger.info(f"🔑 Total unique keywords: {len(unique_keywords)}")

        # 3. Fetch mentions from all sources
        logger.info(f"🚀 Starting scraping with {len(unique_keywords)} keyword(s)...")
        mentions = await fetch_all_mentions(unique_keywords)

        if not mentions:
            logger.info(f"✅ Scraping complete. No new mentions found for brand '{brand_name}'.")
            return {
                "brand_id": brand_id,
                "brand_name": brand_name,
                "success": True,
                "mentions_found": 0,
                "mentions_saved": 0,
                "error": None
            }

        logger.info(f"✅ Found {len(mentions)} potential mention(s)")

        # 4. Save mentions to database with OPTIMIZED batch operations
        saved_count = 0
        skipped_count = 0
        topic_counts = {t["id"]: 0 for t in topics}  # Track mentions per topic
        keyword_counts = {kw: 0 for kw in topic_keyword_map.keys()}  # Track mentions per keyword

        def find_matching_topic_and_keyword(mention_text: str, keyword_map: Dict, default_topic_id: int) -> tuple:
            """
            Find the best matching topic for a mention based on keyword matching.
            Returns (topic_id, matched_keyword) - keyword is None if no match found.
            """
            mention_lower = mention_text.lower()

            # Check each keyword - prioritize longer keywords first (more specific matches)
            sorted_keywords = sorted(keyword_map.keys(), key=len, reverse=True)

            for keyword in sorted_keywords:
                if keyword.lower() in mention_lower:
                    # Return the topic and the matched keyword
                    return keyword_map[keyword][0], keyword

            # No match found - return default with no keyword
            return default_topic_id, None

        # OPTIMIZATION 1: Batch fetch all existing URLs for this brand (1 query instead of N)
        existing_result = supabase.table("mentions")\
            .select("post_link")\
            .eq("brand_id", brand_id)\
            .execute()
        existing_urls = {row["post_link"] for row in existing_result.data} if existing_result.data else set()
        logger.info(f"📦 Loaded {len(existing_urls)} existing URLs for deduplication")

        # OPTIMIZATION 2: Prepare all mentions in memory first
        mentions_to_insert = []
        import time as time_module  # Import once, not per mention

        for mention in mentions:
            try:
                link = mention.get("link")

                # In-memory duplicate check (instant, no DB query)
                if link in existing_urls:
                    skipped_count += 1
                    continue

                # Get platform ID (from cache - no DB query if cached)
                platform_name = mention.get("platform", "Unknown")
                platform_id = await get_platform_id(supabase, platform_name)

                # Determine which topic to assign this mention to based on keyword matching
                mention_text = f"{mention.get('title', '')} {mention.get('content_teaser', '')}"
                assigned_topic_id, matched_keyword = find_matching_topic_and_keyword(
                    mention_text,
                    topic_keyword_map,
                    topics[0]["id"]  # Fallback to first topic if no match
                )

                # Prepare mention data
                published_at = None
                if "published_parsed" in mention and mention["published_parsed"]:
                    published_at = datetime.fromtimestamp(
                        time_module.mktime(mention["published_parsed"]),
                        tz=timezone.utc
                    ).isoformat()

                mention_data = {
                    "caption": mention.get("title", "Ingen titel"),
                    "post_link": link,
                    "published_at": published_at,
                    "platform_id": platform_id,
                    "brand_id": brand_id,
                    "topic_id": assigned_topic_id,
                    "read_status": False,
                    "notified_status": False,
                    "content_teaser": mention.get("content_teaser", "")
                }

                mentions_to_insert.append((mention_data, assigned_topic_id, matched_keyword))

                # Add to existing_urls to prevent duplicates within same batch
                existing_urls.add(link)

            except Exception as mention_error:
                logger.error(f"  ❌ Failed to prepare mention: {mention_error}")
                continue

        # OPTIMIZATION 3: Batch insert all new mentions (1 query instead of N)
        if mentions_to_insert:
            try:
                batch_data = [m[0] for m in mentions_to_insert]
                supabase.table("mentions").insert(batch_data).execute()
                saved_count = len(mentions_to_insert)

                # Update counts for logging
                for _, assigned_topic_id, matched_keyword in mentions_to_insert:
                    topic_counts[assigned_topic_id] = topic_counts.get(assigned_topic_id, 0) + 1
                    if matched_keyword:
                        keyword_counts[matched_keyword] = keyword_counts.get(matched_keyword, 0) + 1

                logger.info(f"✅ Batch inserted {saved_count} mentions in single query")

            except Exception as batch_error:
                logger.error(f"❌ Batch insert failed: {batch_error}")
                # Fallback to individual inserts if batch fails
                logger.info("⚠️ Falling back to individual inserts...")
                for mention_data, assigned_topic_id, matched_keyword in mentions_to_insert:
                    try:
                        supabase.table("mentions").insert(mention_data).execute()
                        saved_count += 1
                        topic_counts[assigned_topic_id] = topic_counts.get(assigned_topic_id, 0) + 1
                        if matched_keyword:
                            keyword_counts[matched_keyword] = keyword_counts.get(matched_keyword, 0) + 1
                    except Exception as e:
                        logger.error(f"  ❌ Individual insert failed: {e}")

        # CRITICAL: Update last_scraped_at timestamp to prevent constant scraping
        supabase.table("brands").update({"last_scraped_at": run_started_at.isoformat()}).eq("id", brand_id).execute()
        logger.info(f"✅ Updated last_scraped_at for brand '{brand_name}'")

        logger.info(f"📊 Summary for '{brand_name}':")
        logger.info(f"  • Total mentions found: {len(mentions)}")
        logger.info(f"  • New mentions saved: {saved_count}")
        logger.info(f"  • Duplicates skipped: {skipped_count}")
        logger.info(f"  • Distribution per topic:")
        for topic in topics:
            count = topic_counts.get(topic["id"], 0)
            logger.info(f"    - {topic['name']}: {count}")

        # Log keyword performance - sort by count descending
        logger.info(f"  • Keyword performance:")
        sorted_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)
        for keyword, count in sorted_keywords:
            if count > 0:
                logger.info(f"    ✅ '{keyword}': {count} mention(s)")
            else:
                logger.info(f"    ❌ '{keyword}': 0 mentions")

        return {
            "brand_id": brand_id,
            "brand_name": brand_name,
            "success": True,
            "mentions_found": len(mentions),
            "mentions_saved": saved_count,
            "error": None
        }

    except Exception as e:
        error_msg = f"Error scraping brand '{brand_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)

        return {
            "brand_id": brand_id,
            "brand_name": brand_name,
            "success": False,
            "mentions_found": 0,
            "mentions_saved": 0,
            "error": str(e)
        }
    finally:
        if lock_acquired:
            await release_brand_scrape_lock(supabase, brand_id)


async def main():
    """
    Main execution function.

    Logic:
    1. Fetch all active brands
    2. For each brand, check if it's due for scraping based on scrape_frequency_hours
    3. Scrape and save mentions
    """
    logger.info("#"*60)
    logger.info("# TrackAnything - Scheduled Scraper")
    logger.info(f"# Started at: {datetime.now(timezone.utc).isoformat()}")
    logger.info("#"*60)

    try:
        # Initialize Supabase admin client (bypasses RLS)
        supabase = get_supabase_admin()
        logger.info("✅ Connected to Supabase")

        # OPTIMIZATION: Pre-load platform cache for fast lookups
        await load_platform_cache(supabase)

        # Fetch all active brands with their scrape frequency and last scrape time
        brands_result = supabase.table("brands")\
            .select("id, name, profile_id, scrape_frequency_hours, last_scraped_at")\
            .eq("is_active", True)\
            .execute()

        if not brands_result.data:
            logger.warning("⚠️  No active brands found. Exiting.")
            return

        brands = brands_result.data
        logger.info(f"📊 Found {len(brands)} active brand(s)")

        # Determine which brands are due for scraping
        brands_to_scrape = []
        current_time = datetime.now(timezone.utc)

        for brand in brands:
            brand_id = brand["id"]
            brand_name = brand["name"]
            scrape_frequency_hours = brand.get("scrape_frequency_hours", 24)
            last_scraped_at = brand.get("last_scraped_at")

            should_scrape = False

            if not last_scraped_at:
                # Never scraped before - scrape immediately
                logger.info(f"✅ '{brand_name}': Aldrig scrapet før. Kører nu.")
                should_scrape = True
            else:
                # Calculate time since last scrape
                last_scraped_time = datetime.fromisoformat(last_scraped_at.replace("Z", "+00:00"))
                hours_since = (current_time - last_scraped_time).total_seconds() / 3600

                if hours_since >= scrape_frequency_hours:
                    logger.info(f"✅ '{brand_name}': Tid til update ({hours_since:.1f}t siden, frekvens: {scrape_frequency_hours}t)")
                    should_scrape = True
                else:
                    logger.info(f"⏭️  '{brand_name}': Venter ({hours_since:.1f}t / {scrape_frequency_hours}t)")

            if should_scrape:
                brands_to_scrape.append(brand)

        if not brands_to_scrape:
            logger.info("✅ No brands are due for scraping at this time.")
            return

        logger.info(f"🚀 Scraping {len(brands_to_scrape)} brand(s)...")

        # Process each brand
        results = []
        for brand in brands_to_scrape:
            result = await scrape_brand(supabase, brand)
            results.append(result)

        # Print final summary
        logger.info("="*60)
        logger.info("📊 FINAL SUMMARY")
        logger.info("="*60)

        successful = sum(1 for r in results if r["success"])
        failed = sum(1 for r in results if not r["success"])
        total_mentions = sum(r["mentions_saved"] for r in results)

        logger.info(f"✅ Successful: {successful}/{len(results)}")
        logger.info(f"❌ Failed: {failed}/{len(results)}")
        logger.info(f"📝 Total new mentions saved: {total_mentions}")

        if failed > 0:
            logger.warning("⚠️  Failed brands:")
            for r in results:
                if not r["success"]:
                    logger.error(f"  • {r['brand_name']}: {r['error']}")

        logger.info("="*60)
        logger.info(f"✅ Scraping complete at {datetime.now(timezone.utc).isoformat()}")
        logger.info("="*60)

        # Exit with error code if any brands failed
        if failed > 0:
            logger.warning(f"Exiting with code 1 due to {failed} failed brand(s)")
            sys.exit(1)

    except Exception as e:
        logger.critical(f"FATAL ERROR: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
