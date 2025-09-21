from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
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

class ScrapeRequest(BaseModel):
    keywords: List[str]
    brand_id: int
    topic_id: int

class ScrapeResponse(BaseModel):
    message: str
    mentions_found: int
    mentions_saved: int
    errors: List[str] = []

@router.post("/run", response_model=ScrapeResponse)
def run_scraping(
    request: ScrapeRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Run scraping process for given keywords and save results to database
    """
    if not request.keywords:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keywords list cannot be empty"
        )
    
    # Verify brand and topic belong to current user
    brand = crud.get_brand(db, request.brand_id)
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    topic = crud.get_topic(db, request.topic_id)
    if not topic or topic.brand_id != request.brand_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found or doesn't belong to the specified brand"
        )
    
    errors = []
    mentions_saved = 0
    
    try:
        # Fetch mentions from all sources
        mentions = fetch_all_mentions(request.keywords)
        
        # Save each mention to database
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
                
                # Create mention object
                mention_create = MentionCreate(
                    caption=mention.get("title", ""),
                    post_link=mention.get("link", ""),
                    published_at=published_date,
                    platform_id=platform.id,
                    brand_id=request.brand_id,
                    topic_id=request.topic_id,
                    read_status=False,
                    notified_status=False
                )
                
                # Save to database (crud.create_mention handles duplicates)
                saved_mention = crud.create_mention(db, mention_create)
                if saved_mention:
                    mentions_saved += 1
                    print(f"✅ Saved mention: {mention.get('title', '')}")
                    
            except Exception as e:
                error_msg = f"Error saving mention '{mention.get('title', 'Unknown')}': {str(e)}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
                continue
        
        return ScrapeResponse(
            message=f"Scraping completed successfully",
            mentions_found=len(mentions),
            mentions_saved=mentions_saved,
            errors=errors
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during scraping process: {str(e)}"
        )