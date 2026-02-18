from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
import uuid
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.logging_config import (
    add_scrape_run_file_handler,
    remove_scrape_run_file_handler,
    reset_current_scrape_run_id,
    set_current_scrape_run_id,
)
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.scraping.orchestrator import fetch_all_mentions, fetch_and_filter_mentions
from app.services.scraping.core.text_processing import sanitize_search_input
import logging

router = APIRouter()
scraping_logger = logging.getLogger("scraping")

def build_search_query(topic: Dict, keyword_text: str, brand_name: str) -> str:
    topic_value = sanitize_search_input(topic.get("name", ""))
    keyword_value = sanitize_search_input(keyword_text)
    brand_value = sanitize_search_input(brand_name)

    template = topic.get("query_template")
    if template:
        return (
            template
            .replace("{{topic}}", topic_value)
            .replace("{{keyword}}", keyword_value)
            .replace("{{brand}}", brand_value)
            .strip()
        )
    return f"{topic_value} {keyword_value}".strip()

def score_topic_match(topic_keywords: List[Dict], title: str, teaser: str) -> tuple[int, List[Dict]]:
    matches = []
    score = 0

    for keyword in topic_keywords:
        keyword_text = keyword.get("text", "").lower()
        if not keyword_text:
            continue

        in_title = keyword_text in title
        in_teaser = keyword_text in teaser
        if not (in_title or in_teaser):
            continue

        matched_in = "both" if in_title and in_teaser else "title" if in_title else "teaser"
        keyword_score = (2 if in_title else 0) + (1 if in_teaser else 0)
        if len(keyword_text) >= 8:
            keyword_score += 1

        matches.append({
            "keyword": keyword,
            "matched_in": matched_in,
            "score": keyword_score
        })
        score += keyword_score

    return score, matches

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
    scrape_run_id = f"b{brand_id}-{uuid.uuid4().hex[:8]}"

    run_handler = None
    run_context_token = None
    lock_acquired = False
    run_started_at = datetime.now(timezone.utc)

    try:
        lock_acquired = await crud.try_acquire_brand_scrape_lock(brand_id)
        if not lock_acquired:
            return BrandScrapeResponse(
                message=f"Scrape already in progress for brand '{brand['name']}'",
                brand_id=brand_id,
                brand_name=brand["name"],
                keywords_used=[],
                mentions_found=0,
                mentions_saved=0,
                errors=["Another scrape run is active for this brand"]
            )

        run_context_token = set_current_scrape_run_id(scrape_run_id)
        run_handler, run_log_path = add_scrape_run_file_handler(scrape_run_id)
        scraping_logger.info(f"[run:{scrape_run_id}] Per-run log file: {run_log_path}")

        scraping_logger.info(f"[run:{scrape_run_id}] Starting scrape for brand '{brand['name']}' ({brand_id})")
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
                # Construct query using optional template if configured.
                # NOTE: This requires Topics to be named descriptively (e.g. "Lego Sustainability" rather than just "General")
                query = build_search_query(topic, keyword["text"], brand["name"])
                if query:
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
        
        # Determine from_date: use last_scraped_at for subsequent scrapes,
        # initial_lookback_days only for the first scrape
        last_scraped_at = brand.get("last_scraped_at")
        from_date = None

        if last_scraped_at:
            # Subsequent scrape: only fetch articles since last scrape
            if isinstance(last_scraped_at, str):
                from_date = dateparser.parse(last_scraped_at)
            else:
                from_date = last_scraped_at
            if from_date and from_date.tzinfo is None:
                from_date = from_date.replace(tzinfo=timezone.utc)
            scraping_logger.info(f"[run:{scrape_run_id}] Subsequent scrape — looking back to last_scraped_at: {from_date}")
        else:
            # First scrape: use initial_lookback_days
            lookback_days = brand.get("initial_lookback_days", 1) or 1
            from_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
            scraping_logger.info(f"[run:{scrape_run_id}] First scrape — looking back {lookback_days} day(s) to {from_date}")

        # Fetch mentions using the improved search queries with AI relevance filtering
        mentions = await fetch_and_filter_mentions(
            query_list,
            apply_relevance_filter=True,
            from_date=from_date,
            scrape_run_id=scrape_run_id
        )

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
        scraping_logger.info(f"[run:{scrape_run_id}] Unique platforms found in mentions: {unique_platforms}")
        platform_cache = {}

        for platform_name in unique_platforms:
            scraping_logger.debug(f"[run:{scrape_run_id}] Looking up platform: {platform_name}")
            platform = await crud.get_platform_by_name(platform_name)
            if not platform:
                scraping_logger.info(f"[run:{scrape_run_id}] Platform '{platform_name}' not found, creating...")
                platform = await crud.create_platform(platform_name)
                if platform:
                    scraping_logger.info(f"[run:{scrape_run_id}] Created platform '{platform_name}' with ID {platform['id']}")
                else:
                    scraping_logger.error(f"[run:{scrape_run_id}] Failed to create platform '{platform_name}'")
            else:
                scraping_logger.debug(f"[run:{scrape_run_id}] Found existing platform '{platform_name}' with ID {platform['id']}")

            if platform:
                platform_cache[platform_name] = platform
            else:
                scraping_logger.error(f"[run:{scrape_run_id}] Platform '{platform_name}' is None after lookup/creation")

        scraping_logger.info(f"[run:{scrape_run_id}] Platform cache has {len(platform_cache)} entries: {list(platform_cache.keys())}")

        # 2. Pre-fetch all topic keywords
        topic_keywords_cache = {}
        for topic in active_topics:
            keywords = await crud.get_keywords_by_topic(topic["id"])
            topic_keywords_cache[topic["id"]] = keywords

        # 3. Build all mention objects (no database writes yet)
        mentions_to_insert = []
        mention_keyword_matches = {}

        for mention in mentions:
            try:
                # Convert published_parsed tuple to datetime
                if "published_parsed" in mention and mention["published_parsed"]:
                    published_date = datetime(*mention["published_parsed"][:6], tzinfo=timezone.utc)
                else:
                    published_date = None

                # Get platform from cache
                platform = platform_cache.get(mention.get("platform", "Unknown"))
                if not platform:
                    error_msg = f"Platform not found for mention: {mention.get('title', 'Unknown')}"
                    errors.append(error_msg)
                    continue

                # Find best matching topic based on keywords in mention (using cache)
                best_topic = None
                best_topic_score = -1
                best_topic_matches = []
                title = (mention.get("title") or "").lower()
                teaser = (mention.get("content_teaser") or "").lower()

                for topic in active_topics:
                    topic_keywords = topic_keywords_cache.get(topic["id"], [])
                    topic_score, topic_matches = score_topic_match(topic_keywords, title, teaser)
                    if topic_score > best_topic_score:
                        best_topic_score = topic_score
                        best_topic = topic
                        best_topic_matches = topic_matches

                # If no keyword match found, use first active topic
                if not best_topic:
                    best_topic = active_topics[0]
                    best_topic_matches = []

                primary_keyword_id = None
                if best_topic_matches:
                    best_match = sorted(
                        best_topic_matches,
                        key=lambda match: (match["score"], len(match["keyword"].get("text", ""))),
                        reverse=True
                    )[0]
                    primary_keyword_id = best_match["keyword"].get("id")

                # Create mention object
                mention_data = {
                    "caption": mention.get("title", ""),
                    "post_link": mention.get("link", ""),
                    "published_at": published_date.isoformat() if published_date else None,
                    "content_teaser": mention.get("content_teaser"),
                    "platform_id": platform["id"],
                    "brand_id": brand_id,
                    "topic_id": best_topic["id"],
                    "primary_keyword_id": primary_keyword_id,
                    "read_status": False,
                    "notified_status": False
                }

                mentions_to_insert.append(mention_data)

                if best_topic_matches and mention_data["post_link"]:
                    mention_key = (mention_data["post_link"], mention_data["topic_id"])
                    mention_keyword_matches[mention_key] = [
                        {
                            "keyword_id": match["keyword"]["id"],
                            "matched_in": match["matched_in"],
                            "score": match["score"]
                        }
                        for match in best_topic_matches
                    ]

            except Exception as e:
                error_msg = f"Error preparing mention '{mention.get('title', 'Unknown')}': {str(e)}"
                errors.append(error_msg)
                scraping_logger.error(f"[run:{scrape_run_id}] {error_msg}")

        # 4. BATCH INSERT all mentions at once (10-50x faster than individual inserts)
        mentions_saved = 0
        if mentions_to_insert:
            mentions_saved, batch_errors = await crud.batch_create_mentions(mentions_to_insert)
            errors.extend(batch_errors)
            scraping_logger.info(f"[run:{scrape_run_id}] Batch saved {mentions_saved} mentions for {brand['name']}")

        if mention_keyword_matches:
            mention_id_map = await crud.get_mentions_by_keys(brand_id, list(mention_keyword_matches.keys()))
            mention_keyword_rows = []
            for mention_key, matches in mention_keyword_matches.items():
                mention_id = mention_id_map.get(mention_key)
                if not mention_id:
                    continue
                for match in matches:
                    mention_keyword_rows.append({
                        "mention_id": mention_id,
                        **match
                    })

            if mention_keyword_rows:
                match_errors = await crud.batch_create_mention_keywords(mention_keyword_rows)
                errors.extend(match_errors)

        # 5. Update last_scraped_at timestamp for the brand
        await crud.update_brand_last_scraped(brand_id, run_started_at)
        scraping_logger.info(f"[run:{scrape_run_id}] Updated last_scraped_at for brand '{brand['name']}'")

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
        scraping_logger.exception(f"[run:{scrape_run_id}] Critical scrape error for brand '{brand['name']}': {e}")
        return BrandScrapeResponse(
            message=f"Scraping failed for brand '{brand['name']}'",
            brand_id=brand_id,
            brand_name=brand["name"],
            keywords_used=[],
            mentions_found=0,
            mentions_saved=0,
            errors=[f"Critical error: {str(e)}"]
        )
    finally:
        if lock_acquired:
            released = await crud.release_brand_scrape_lock(brand_id)
            if not released:
                scraping_logger.warning(f"[run:{scrape_run_id}] Failed to release scrape lock for brand {brand_id}")
        if run_handler is not None:
            remove_scrape_run_file_handler(run_handler)
        if run_context_token is not None:
            reset_current_scrape_run_id(run_context_token)

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
                scraping_logger.error(error_msg)
        
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
