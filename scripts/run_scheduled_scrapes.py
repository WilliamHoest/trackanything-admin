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


async def get_platform_id(supabase, platform_name: str) -> int:
    """Get or create platform ID from platforms table."""
    try:
        # Try to get existing platform
        result = supabase.table("platforms").select("id").eq("name", platform_name).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]["id"]

        # Create new platform if it doesn't exist
        insert_result = supabase.table("platforms").insert({"name": platform_name}).execute()
        logger.info(f"Created new platform: {platform_name}")
        return insert_result.data[0]["id"]

    except Exception as e:
        logger.error(f"Error getting platform ID for '{platform_name}': {e}")
        # Default to a safe fallback (you may want to adjust this)
        return 1


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

    try:
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

        # 4. Save mentions to database with deduplication
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

        for mention in mentions:
            try:
                # Get platform ID
                platform_name = mention.get("platform", "Unknown")
                platform_id = await get_platform_id(supabase, platform_name)

                # Determine which topic to assign this mention to based on keyword matching
                mention_text = f"{mention.get('title', '')} {mention.get('content_teaser', '')}"
                assigned_topic_id, matched_keyword = find_matching_topic_and_keyword(
                    mention_text,
                    topic_keyword_map,
                    topics[0]["id"]  # Fallback to first topic if no match
                )

                # Check if this mention already exists for this brand
                link = mention.get("link")
                existing = supabase.table("mentions")\
                    .select("id")\
                    .eq("post_link", link)\
                    .eq("brand_id", brand_id)\
                    .execute()

                if existing.data and len(existing.data) > 0:
                    skipped_count += 1
                    continue  # Skip duplicate

                # Prepare mention data
                published_at = None
                if "published_parsed" in mention and mention["published_parsed"]:
                    # Convert time.struct_time to datetime
                    import time
                    published_at = datetime.fromtimestamp(
                        time.mktime(mention["published_parsed"]),
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

                # Insert mention
                supabase.table("mentions").insert(mention_data).execute()
                saved_count += 1
                topic_counts[assigned_topic_id] = topic_counts.get(assigned_topic_id, 0) + 1
                if matched_keyword:
                    keyword_counts[matched_keyword] = keyword_counts.get(matched_keyword, 0) + 1

                # Find topic name for logging
                topic_name = next((t["name"] for t in topics if t["id"] == assigned_topic_id), "Unknown")
                keyword_info = f" (keyword: '{matched_keyword}')" if matched_keyword else " (no keyword match)"
                logger.debug(f"  ✅ Saved to '{topic_name}'{keyword_info}: {mention.get('title', 'Uden titel')[:40]}")

            except Exception as mention_error:
                logger.error(f"  ❌ Failed to save mention: {mention_error}")
                continue

        # CRITICAL: Update last_scraped_at timestamp to prevent constant scraping
        now_iso = datetime.now(timezone.utc).isoformat()
        supabase.table("brands").update({"last_scraped_at": now_iso}).eq("id", brand_id).execute()
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
