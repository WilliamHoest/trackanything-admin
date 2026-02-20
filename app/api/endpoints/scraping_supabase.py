import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.logging_config import (
    add_scrape_run_file_handler,
    remove_scrape_run_file_handler,
    reset_current_scrape_run_id,
    set_current_scrape_run_id,
)
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.security.auth import get_current_user
from app.services.scraping.pipeline import process_brand_scrape

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
    scrape_run_id = f"b{brand_id}-{uuid.uuid4().hex[:8]}"

    run_handler = None
    run_context_token = None

    try:
        run_context_token = set_current_scrape_run_id(scrape_run_id)
        run_handler, run_log_path = add_scrape_run_file_handler(scrape_run_id)
        scraping_logger.info(f"[run:{scrape_run_id}] Per-run log file: {run_log_path}")
        result = await process_brand_scrape(
            brand_id=brand_id,
            crud=crud,
            scrape_run_id=scrape_run_id,
            apply_relevance_filter=True,
            acquire_lock=True,
        )
        return BrandScrapeResponse(
            message=result.message,
            brand_id=result.brand_id,
            brand_name=result.brand_name,
            keywords_used=result.keywords_used,
            mentions_found=result.mentions_found,
            mentions_saved=result.mentions_saved,
            errors=result.errors,
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
