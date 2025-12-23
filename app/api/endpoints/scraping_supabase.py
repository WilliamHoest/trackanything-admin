from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timezone
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.scraping_service import fetch_all_mentions

router = APIRouter()

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
        
        # Collect all keywords from all active topics
        all_keywords = set()
        for topic in active_topics:
            keywords = await crud.get_keywords_by_topic(topic["id"])
            for keyword in keywords:
                all_keywords.add(keyword["word"])
        
        keyword_list = list(all_keywords)
        
        if not keyword_list:
            return BrandScrapeResponse(
                message=f"No keywords found for brand '{brand['name']}'",
                brand_id=brand_id,
                brand_name=brand["name"],
                keywords_used=[],
                mentions_found=0,
                mentions_saved=0,
                errors=["No keywords configured for this brand"]
            )
        
        # Fetch mentions from all sources
        mentions = fetch_all_mentions(keyword_list)
        
        errors = []
        mentions_saved = 0
        
        # Save mentions to database
        for mention in mentions:
            try:
                # Convert published_parsed tuple to datetime
                if "published_parsed" in mention and mention["published_parsed"]:
                    published_date = datetime(*mention["published_parsed"][:6], tzinfo=timezone.utc)
                else:
                    published_date = datetime.now(timezone.utc)
                
                # Get or create platform
                platform = await crud.get_platform_by_name(mention.get("platform", "Unknown"))
                if not platform:
                    platform = await crud.create_platform(mention.get("platform", "Unknown"))
                
                # Find best matching topic based on keywords in mention
                best_topic = None
                for topic in active_topics:
                    topic_keywords = await crud.get_keywords_by_topic(topic["id"])
                    for keyword in topic_keywords:
                        if keyword["word"].lower() in mention.get("title", "").lower():
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
                
                # Save to database
                saved_mention = await crud.create_mention(mention_data)
                if saved_mention:
                    mentions_saved += 1
                    print(f"✅ Saved mention for {brand['name']}: {mention.get('title', '')}")
                    
            except Exception as e:
                error_msg = f"Error saving mention '{mention.get('title', 'Unknown')}': {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
        
        return BrandScrapeResponse(
            message=f"Scraping completed for brand '{brand['name']}'",
            brand_id=brand_id,
            brand_name=brand["name"],
            keywords_used=keyword_list,
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
        
        # Process each brand
        for brand in brands:
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
            message=f"Scraping completed for {len(brands)} brands",
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