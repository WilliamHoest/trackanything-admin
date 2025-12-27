#!/usr/bin/env python3
"""
Scheduled Scraping Script for TrackAnything

This script is designed to be run by a cron job (e.g., hourly).
It fetches all active brands, determines which ones are due for scraping
based on their scrape_frequency_hours, and processes them.

Cron example (run every hour):
0 * * * * cd /path/to/trackanything-admin && /path/to/venv/bin/python scripts/run_scheduled_scrapes.py >> logs/scraper.log 2>&1
"""

import sys
import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set

# Add parent directory to path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase_admin
from app.services.scraping.orchestrator import fetch_all_mentions

async def get_platform_id(supabase, platform_name: str) -> int:
    """Get or create platform ID from platforms table."""
    try:
        # Try to get existing platform
        result = supabase.table("platforms").select("id").eq("name", platform_name).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]["id"]

        # Create new platform if it doesn't exist
        insert_result = supabase.table("platforms").insert({"name": platform_name}).execute()
        return insert_result.data[0]["id"]

    except Exception as e:
        print(f"⚠️  Error getting platform ID for '{platform_name}': {e}")
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

    print(f"\n{'='*60}")
    print(f"🔍 Processing Brand: {brand_name} (ID: {brand_id})")
    print(f"{'='*60}")

    try:
        # 1. Fetch all active topics for this brand
        topics_result = supabase.table("topics").select("id, name").eq("brand_id", brand_id).eq("is_active", True).execute()

        if not topics_result.data:
            print(f"⚠️  No active topics found for brand '{brand_name}'. Skipping.")
            return {
                "brand_id": brand_id,
                "brand_name": brand_name,
                "success": True,
                "mentions_found": 0,
                "mentions_saved": 0,
                "error": "No active topics"
            }

        topics = topics_result.data
        print(f"📋 Found {len(topics)} active topic(s)")

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
                print(f"  📌 Topic '{topic_name}': {len(topic_keywords)} keyword(s)")

        if not all_keywords:
            print(f"⚠️  No keywords found for brand '{brand_name}'. Skipping.")
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
        print(f"🔑 Total unique keywords: {len(unique_keywords)}")

        # 3. Fetch mentions from all sources
        print(f"🚀 Starting scraping with {len(unique_keywords)} keyword(s)...")
        mentions = await fetch_all_mentions(unique_keywords)

        if not mentions:
            print(f"✅ Scraping complete. No new mentions found for brand '{brand_name}'.")
            return {
                "brand_id": brand_id,
                "brand_name": brand_name,
                "success": True,
                "mentions_found": 0,
                "mentions_saved": 0,
                "error": None
            }

        print(f"✅ Found {len(mentions)} potential mention(s)")

        # 4. Save mentions to database with deduplication
        saved_count = 0
        skipped_count = 0

        for mention in mentions:
            try:
                # Get platform ID
                platform_name = mention.get("platform", "Unknown")
                platform_id = await get_platform_id(supabase, platform_name)

                # Determine which topic(s) to assign this mention to
                # For simplicity, assign to the first topic that matches any keyword in the mention
                # (In a more sophisticated system, you'd do keyword matching per mention)
                assigned_topic_id = topics[0]["id"]  # Default to first topic

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
                print(f"  ✅ Saved: {mention.get('title', 'Uden titel')[:60]}")

            except Exception as mention_error:
                print(f"  ❌ Failed to save mention: {mention_error}")
                continue

        # CRITICAL: Update last_scraped_at timestamp to prevent constant scraping
        now_iso = datetime.now(timezone.utc).isoformat()
        supabase.table("brands").update({"last_scraped_at": now_iso}).eq("id", brand_id).execute()
        print(f"✅ Updated last_scraped_at for brand '{brand_name}'")

        print(f"\n📊 Summary for '{brand_name}':")
        print(f"  • Total mentions found: {len(mentions)}")
        print(f"  • New mentions saved: {saved_count}")
        print(f"  • Duplicates skipped: {skipped_count}")

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
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()

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
    print(f"\n{'#'*60}")
    print(f"# TrackAnything - Scheduled Scraper")
    print(f"# Started at: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'#'*60}\n")

    try:
        # Initialize Supabase admin client (bypasses RLS)
        supabase = get_supabase_admin()
        print("✅ Connected to Supabase")

        # Fetch all active brands with their scrape frequency and last scrape time
        brands_result = supabase.table("brands")\
            .select("id, name, profile_id, scrape_frequency_hours, last_scraped_at")\
            .eq("is_active", True)\
            .execute()

        if not brands_result.data:
            print("⚠️  No active brands found. Exiting.")
            return

        brands = brands_result.data
        print(f"📊 Found {len(brands)} active brand(s)\n")

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
                print(f"✅ '{brand_name}': Aldrig scrapet før. Kører nu.")
                should_scrape = True
            else:
                # Calculate time since last scrape
                last_scraped_time = datetime.fromisoformat(last_scraped_at.replace("Z", "+00:00"))
                hours_since = (current_time - last_scraped_time).total_seconds() / 3600

                if hours_since >= scrape_frequency_hours:
                    print(f"✅ '{brand_name}': Tid til update ({hours_since:.1f}t siden, frekvens: {scrape_frequency_hours}t)")
                    should_scrape = True
                else:
                    print(f"⏭️  '{brand_name}': Venter ({hours_since:.1f}t / {scrape_frequency_hours}t)")

            if should_scrape:
                brands_to_scrape.append(brand)

        if not brands_to_scrape:
            print("\n✅ No brands are due for scraping at this time.")
            return

        print(f"\n🚀 Scraping {len(brands_to_scrape)} brand(s)...\n")

        # Process each brand
        results = []
        for brand in brands_to_scrape:
            result = await scrape_brand(supabase, brand)
            results.append(result)

        # Print final summary
        print(f"\n{'='*60}")
        print(f"📊 FINAL SUMMARY")
        print(f"{'='*60}")

        successful = sum(1 for r in results if r["success"])
        failed = sum(1 for r in results if not r["success"])
        total_mentions = sum(r["mentions_saved"] for r in results)

        print(f"✅ Successful: {successful}/{len(results)}")
        print(f"❌ Failed: {failed}/{len(results)}")
        print(f"📝 Total new mentions saved: {total_mentions}")

        if failed > 0:
            print(f"\n⚠️  Failed brands:")
            for r in results:
                if not r["success"]:
                    print(f"  • {r['brand_name']}: {r['error']}")

        print(f"\n{'='*60}")
        print(f"✅ Scraping complete at {datetime.now(timezone.utc).isoformat()}")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
