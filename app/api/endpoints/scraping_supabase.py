from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timezone
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.scraping.orchestrator import fetch_all_mentions, fetch_and_filter_mentions
import logging

router = APIRouter()
scraping_logger = logging.getLogger("scraping")

class BrandScrapeResponse(BaseModel):
    message: str
    brand_id: int
    brand_name: str
    keywords_used: List[str]
    mentions_found: int
    mentions_saved: int
    errors: List[str] = []

class UserScrapeResponse(BaseModel):
    message: str
    total_brands_processed: int
    total_mentions_found: int
    total_mentions_saved: int
    brand_results: List[BrandScrapeResponse]
    errors: List[str] = []

@router.post("/brand/{brand_id}", response_model=BrandScrapeResponse)
async def scrape_brand(
    brand_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Run scraping process for all keywords in a specific brand scope
    (Can scrape both active and inactive brands for manual scraping)
    """
    # Verify brand belongs to current user
    brand = await crud.get_brand(brand_id)
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )

    try:
        # Get all active topics for this brand
        topics = await crud.get_topics_by_brand(brand_id)
        active_topics = [topic for topic in topics if topic.get("is_active", True)]
        
        if not active_topics:
            return BrandScrapeResponse(
                message=f"No active topics found for brand '{brand['name']}'",
                brand_id=brand_id,
                brand_name=brand["name"],
                keywords_used=[],
                mentions_found=0,
                mentions_saved=0,
                errors=["No active topics found for this brand"]
            )
        
        # Collect all keywords from all active topics and combine with Brand Name
        # This creates "Context Aware" search queries (e.g. "Mærsk Regnskab" instead of just "Regnskab")
        search_queries = set()
        for topic in active_topics:
            keywords = await crud.get_keywords_by_topic(topic["id"])
            for keyword in keywords:
                # Construct query: "{Topic Name}" {Keyword}
                # Changed from Brand+Keyword to Topic+Keyword per user request for better specificity.
                # NOTE: This requires Topics to be named descriptively (e.g. "Lego Sustainability" rather than just "General")
                query = f'"{topic["name"]}" {keyword["text"]}'
                search_queries.add(query)
        
        query_list = list(search_queries)
        
        if not query_list:
            return BrandScrapeResponse(
                message=f"No keywords found for brand '{brand['name']}'",
                brand_id=brand_id,
                brand_name=brand["name"],
                keywords_used=[],
                mentions_found=0,
                mentions_saved=0,
                errors=["No keywords configured for this brand"]
            )
        
        # Fetch mentions using the improved search queries with AI relevance filtering
        mentions = await fetch_and_filter_mentions(query_list, apply_relevance_filter=True)

        if not mentions:
            return BrandScrapeResponse(
                message=f"No mentions found for brand '{brand['name']}'",
                brand_id=brand_id,
                brand_name=brand["name"],
                keywords_used=query_list,
                mentions_found=0,
                mentions_saved=0,
                errors=[]
            )

        errors = []

        # OPTIMIZATION: Pre-fetch all platforms and topic keywords BEFORE the loop
        # This avoids N database queries and reduces latency significantly

        # 1. Get or create all unique platforms
        unique_platforms = set(m.get("platform", "Unknown") for m in mentions)
        scraping_logger.info(f"Unique platforms found in mentions: {unique_platforms}")
        platform_cache = {}

        for platform_name in unique_platforms:
            scraping_logger.debug(f"Looking up platform: {platform_name}")
            platform = await crud.get_platform_by_name(platform_name)
            if not platform:
                scraping_logger.info(f"Platform '{platform_name}' not found, creating...")
                platform = await crud.create_platform(platform_name)
                if platform:
                    scraping_logger.info(f"✅ Created platform '{platform_name}' with ID {platform['id']}")
                else:
                    scraping_logger.error(f"❌ Failed to create platform '{platform_name}'")
            else:
                scraping_logger.debug(f"Found existing platform '{platform_name}' with ID {platform['id']}")

            if platform:
                platform_cache[platform_name] = platform
            else:
                scraping_logger.error(f"❌ Platform '{platform_name}' is None after lookup/creation")

        scraping_logger.info(f"Platform cache has {len(platform_cache)} entries: {list(platform_cache.keys())}")

        # 2. Pre-fetch all topic keywords
        topic_keywords_cache = {}
        for topic in active_topics:
            keywords = await crud.get_keywords_by_topic(topic["id"])
            topic_keywords_cache[topic["id"]] = keywords

        # 3. Build all mention objects (no database writes yet)
        mentions_to_insert = []

        for mention in mentions:
            try:
                # Convert published_parsed tuple to datetime
                if "published_parsed" in mention and mention["published_parsed"]:
                    published_date = datetime(*mention["published_parsed"][:6], tzinfo=timezone.utc)
                else:
                    published_date = datetime.now(timezone.utc)

                # Get platform from cache
                platform = platform_cache.get(mention.get("platform", "Unknown"))
                if not platform:
                    error_msg = f"Platform not found for mention: {mention.get('title', 'Unknown')}"
                    errors.append(error_msg)
                    continue

                # Find best matching topic based on keywords in mention (using cache)
                best_topic = None
                for topic in active_topics:
                    topic_keywords = topic_keywords_cache.get(topic["id"], [])
                    for keyword in topic_keywords:
                        if keyword["text"].lower() in mention.get("title", "").lower():
                            best_topic = topic
                            break
                    if best_topic:
                        break

                # If no keyword match found, use first active topic
                if not best_topic:
                    best_topic = active_topics[0]

                # Create mention object
                mention_data = {
                    "caption": mention.get("title", ""),
                    "post_link": mention.get("link", ""),
                    "published_at": published_date.isoformat(),
                    "content_teaser": mention.get("content_teaser"),
                    "platform_id": platform["id"],
                    "brand_id": brand_id,
                    "topic_id": best_topic["id"],
                    "read_status": False,
                    "notified_status": False
                }

                mentions_to_insert.append(mention_data)

            except Exception as e:
                error_msg = f"Error preparing mention '{mention.get('title', 'Unknown')}': {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")

        # 4. BATCH INSERT all mentions at once (10-50x faster than individual inserts)
        mentions_saved = 0
        if mentions_to_insert:
            mentions_saved, batch_errors = await crud.batch_create_mentions(mentions_to_insert)
            errors.extend(batch_errors)
            print(f"✅ Batch saved {mentions_saved} mentions for {brand['name']}")

        # 5. Update last_scraped_at timestamp for the brand
        await crud.update_brand_last_scraped(brand_id)
        print(f"✅ Updated last_scraped_at for brand '{brand['name']}'")

        return BrandScrapeResponse(
            message=f"Scraping completed for brand '{brand['name']}'",
            brand_id=brand_id,
            brand_name=brand["name"],
            keywords_used=query_list,
            mentions_found=len(mentions),
            mentions_saved=mentions_saved,
            errors=errors
        )
        
    except Exception as e:
        return BrandScrapeResponse(
            message=f"Scraping failed for brand '{brand['name']}'",
            brand_id=brand_id,
            brand_name=brand["name"],
            keywords_used=[],
            mentions_found=0,
            mentions_saved=0,
            errors=[f"Critical error: {str(e)}"]
        )

@router.post("/user", response_model=UserScrapeResponse)
async def scrape_user(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Run scraping process for all brands belonging to the current user
    """
    try:
        # Get all brands for the user
        brands = await crud.get_brands_by_profile(current_user.id)
        
        if not brands:
            return UserScrapeResponse(
                message="No brands found for user",
                total_brands_processed=0,
                total_mentions_found=0,
                total_mentions_saved=0,
                brand_results=[],
                errors=["No brands configured for this user"]
            )
        
        brand_results = []
        total_mentions_found = 0
        total_mentions_saved = 0
        global_errors = []
        
        # Filter out inactive brands
        active_brands = [b for b in brands if b.get("is_active", True)]

        if not active_brands:
            return UserScrapeResponse(
                message="No active brands to scrape",
                total_brands_processed=0,
                total_mentions_found=0,
                total_mentions_saved=0,
                brand_results=[],
                errors=["All brands are inactive"]
            )

        # Process each active brand
        for brand in active_brands:
            try:
                result = await scrape_brand(brand["id"], crud, current_user)
                brand_results.append(result)
                total_mentions_found += result.mentions_found
                total_mentions_saved += result.mentions_saved
                global_errors.extend(result.errors)

            except Exception as e:
                error_msg = f"Failed to process brand '{brand.get('name', 'Unknown')}': {str(e)}"
                global_errors.append(error_msg)
                print(f"❌ {error_msg}")
        
        return UserScrapeResponse(
            message=f"Scraping completed for {len(active_brands)} active brands",
            total_brands_processed=len(brand_results),
            total_mentions_found=total_mentions_found,
            total_mentions_saved=total_mentions_saved,
            brand_results=brand_results,
            errors=global_errors
        )
        
    except Exception as e:
        return UserScrapeResponse(
            message="User scraping failed",
            total_brands_processed=0,
            total_mentions_found=0,
            total_mentions_saved=0,
            brand_results=[],
            errors=[f"Critical error: {str(e)}"]
        )

@router.get("/keywords/user", response_model=List[str])
async def get_user_keywords(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Get all keywords for the current user (for testing scraping scope)
    """
    keywords = await crud.get_all_user_keywords(current_user.id)
    return keywords