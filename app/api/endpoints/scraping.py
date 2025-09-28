from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timezone
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.database import get_db
from app.core.config import settings
from app.crud import crud
from app.services.scraping_service import fetch_all_mentions
from app.schemas.mention import MentionCreate

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

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

class ScheduledScrapeRequest(BaseModel):
    schedule_time: Optional[str] = "0 9 * * *"  # Default: Daily at 9 AM
    is_active: bool = True

@router.post("/brand/{brand_id}", response_model=BrandScrapeResponse)
def scrape_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Run scraping process for all keywords in a specific brand scope
    """
    # Verify brand belongs to current user
    brand = crud.get_brand(db, brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    try:
        # Get all active topics for this brand
        topics = crud.get_topics_by_brand(db, brand_id)
        active_topics = [topic for topic in topics if topic.is_active]
        
        if not active_topics:
            return BrandScrapeResponse(
                message=f"No active topics found for brand '{brand.name}'",
                brand_id=brand_id,
                brand_name=brand.name,
                keywords_used=[],
                mentions_found=0,
                mentions_saved=0,
                errors=["No active topics found for this brand"]
            )
        
        # Collect all keywords from all active topics
        all_keywords = set()
        for topic in active_topics:
            keywords = crud.get_keywords_by_topic(db, topic.id)
            for keyword in keywords:
                all_keywords.add(keyword.text)
        
        keyword_list = list(all_keywords)
        
        if not keyword_list:
            return BrandScrapeResponse(
                message=f"No keywords found for brand '{brand.name}'",
                brand_id=brand_id,
                brand_name=brand.name,
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
                platform = crud.get_platform_by_name(db, mention.get("platform", "Unknown"))
                if not platform:
                    from app.schemas.platform import PlatformCreate
                    platform = crud.create_platform(db, PlatformCreate(name=mention.get("platform", "Unknown")))
                
                # Find best matching topic based on keywords in mention
                best_topic = None
                for topic in active_topics:
                    topic_keywords = crud.get_keywords_by_topic(db, topic.id)
                    for keyword in topic_keywords:
                        if keyword.text.lower() in mention.get("title", "").lower():
                            best_topic = topic
                            break
                    if best_topic:
                        break
                
                # If no keyword match found, use first active topic
                if not best_topic:
                    best_topic = active_topics[0]
                
                # Create mention object
                mention_create = MentionCreate(
                    caption=mention.get("title", ""),
                    post_link=mention.get("link", ""),
                    published_at=published_date,
                    platform_id=platform.id,
                    brand_id=brand_id,
                    topic_id=best_topic.id,
                    read_status=False,
                    notified_status=False
                )
                
                # Save to database
                saved_mention = crud.create_mention(db, mention_create)
                if saved_mention:
                    mentions_saved += 1
                    print(f"✅ Saved mention for {brand.name}: {mention.get('title', '')}")
                    
            except Exception as e:
                error_msg = f"Error saving mention '{mention.get('title', 'Unknown')}': {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
                continue
        
        return BrandScrapeResponse(
            message=f"Brand scraping completed for '{brand.name}'",
            brand_id=brand_id,
            brand_name=brand.name,
            keywords_used=keyword_list,
            mentions_found=len(mentions),
            mentions_saved=mentions_saved,
            errors=errors
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during brand scraping: {str(e)}"
        )

@router.post("/user/all-brands", response_model=UserScrapeResponse)
def scrape_all_user_brands(
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Run scraping process for all brand scopes belonging to the current user
    """
    try:
        # Get all brands for current user
        brands = crud.get_brands_by_user(db, current_user.id)
        
        if not brands:
            return UserScrapeResponse(
                message="No brands found for current user",
                total_brands_processed=0,
                total_mentions_found=0,
                total_mentions_saved=0,
                brand_results=[],
                errors=["No brands found for current user"]
            )
        
        brand_results = []
        total_mentions_found = 0
        total_mentions_saved = 0
        global_errors = []
        
        # Process each brand
        for brand in brands:
            try:
                # Get all active topics for this brand
                topics = crud.get_topics_by_brand(db, brand.id)
                active_topics = [topic for topic in topics if topic.is_active]
                
                if not active_topics:
                    brand_result = BrandScrapeResponse(
                        message=f"No active topics for brand '{brand.name}'",
                        brand_id=brand.id,
                        brand_name=brand.name,
                        keywords_used=[],
                        mentions_found=0,
                        mentions_saved=0,
                        errors=["No active topics found"]
                    )
                    brand_results.append(brand_result)
                    continue
                
                # Collect keywords for this brand
                brand_keywords = set()
                for topic in active_topics:
                    keywords = crud.get_keywords_by_topic(db, topic.id)
                    for keyword in keywords:
                        brand_keywords.add(keyword.text)
                
                keyword_list = list(brand_keywords)
                
                if not keyword_list:
                    brand_result = BrandScrapeResponse(
                        message=f"No keywords for brand '{brand.name}'",
                        brand_id=brand.id,
                        brand_name=brand.name,
                        keywords_used=[],
                        mentions_found=0,
                        mentions_saved=0,
                        errors=["No keywords configured"]
                    )
                    brand_results.append(brand_result)
                    continue
                
                # Fetch mentions for this brand
                mentions = fetch_all_mentions(keyword_list)
                brand_errors = []
                brand_mentions_saved = 0
                
                # Save mentions
                for mention in mentions:
                    try:
                        # Convert published_parsed tuple to datetime
                        if "published_parsed" in mention and mention["published_parsed"]:
                            published_date = datetime(*mention["published_parsed"][:6], tzinfo=timezone.utc)
                        else:
                            published_date = datetime.now(timezone.utc)
                        
                        # Get or create platform
                        platform = crud.get_platform_by_name(db, mention.get("platform", "Unknown"))
                        if not platform:
                            from app.schemas.platform import PlatformCreate
                            platform = crud.create_platform(db, PlatformCreate(name=mention.get("platform", "Unknown")))
                        
                        # Find best matching topic
                        best_topic = None
                        for topic in active_topics:
                            topic_keywords = crud.get_keywords_by_topic(db, topic.id)
                            for keyword in topic_keywords:
                                if keyword.text.lower() in mention.get("title", "").lower():
                                    best_topic = topic
                                    break
                            if best_topic:
                                break
                        
                        if not best_topic:
                            best_topic = active_topics[0]
                        
                        # Create mention
                        mention_create = MentionCreate(
                            caption=mention.get("title", ""),
                            post_link=mention.get("link", ""),
                            published_at=published_date,
                            platform_id=platform.id,
                            brand_id=brand.id,
                            topic_id=best_topic.id,
                            read_status=False,
                            notified_status=False
                        )
                        
                        saved_mention = crud.create_mention(db, mention_create)
                        if saved_mention:
                            brand_mentions_saved += 1
                            print(f"✅ Saved mention for {brand.name}: {mention.get('title', '')}")
                            
                    except Exception as e:
                        error_msg = f"Error saving mention '{mention.get('title', 'Unknown')}': {str(e)}"
                        brand_errors.append(error_msg)
                        continue
                
                # Create brand result
                brand_result = BrandScrapeResponse(
                    message=f"Completed scraping for '{brand.name}'",
                    brand_id=brand.id,
                    brand_name=brand.name,
                    keywords_used=keyword_list,
                    mentions_found=len(mentions),
                    mentions_saved=brand_mentions_saved,
                    errors=brand_errors
                )
                
                brand_results.append(brand_result)
                total_mentions_found += len(mentions)
                total_mentions_saved += brand_mentions_saved
                
            except Exception as e:
                error_msg = f"Error processing brand '{brand.name}': {str(e)}"
                global_errors.append(error_msg)
                print(f"❌ {error_msg}")
                continue
        
        return UserScrapeResponse(
            message=f"Completed scraping for {len(brands)} brands",
            total_brands_processed=len(brand_results),
            total_mentions_found=total_mentions_found,
            total_mentions_saved=total_mentions_saved,
            brand_results=brand_results,
            errors=global_errors
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during user scraping: {str(e)}"
        )

@router.post("/schedule/brand/{brand_id}", response_model=dict)
def schedule_brand_scraping(
    brand_id: int,
    schedule_request: ScheduledScrapeRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Schedule automatic scraping for a specific brand scope
    """
    # Verify brand belongs to current user
    brand = crud.get_brand(db, brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    try:
        # Placeholder for cron job scheduling logic
        # You'll need to implement actual cron job management here
        
        return {
            "message": f"Scheduled scraping for brand '{brand.name}'",
            "brand_id": brand_id,
            "brand_name": brand.name,
            "schedule": schedule_request.schedule_time,
            "is_active": schedule_request.is_active,
            "note": "Cron job implementation pending"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error scheduling brand scraping: {str(e)}"
        )

@router.post("/schedule/user/all-brands", response_model=dict)
def schedule_all_user_brands_scraping(
    schedule_request: ScheduledScrapeRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Schedule automatic scraping for all brand scopes belonging to the current user
    """
    try:
        brands = crud.get_brands_by_user(db, current_user.id)
        
        if not brands:
            return {
                "message": "No brands found for current user",
                "scheduled_brands": 0,
                "errors": ["No brands found for current user"]
            }
        
        # Placeholder for cron job scheduling logic
        return {
            "message": f"Scheduled scraping for all {len(brands)} brands",
            "scheduled_brands": len(brands),
            "schedule": schedule_request.schedule_time,
            "is_active": schedule_request.is_active,
            "brand_names": [brand.name for brand in brands],
            "note": "Cron job implementation pending"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error scheduling user scraping: {str(e)}"
        )