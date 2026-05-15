from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.digest_service_supabase import (
    create_and_send_digest_supabase,
    generate_digest_text_supabase,
    get_mention_batch_window,
    get_latest_digest_window,
)

router = APIRouter()

class DigestResponse(BaseModel):
    success: bool
    message: str
    mentions_sent: int
    mentions_updated: int = 0
    webhook_url: str = ""


class DigestJobSummary(BaseModel):
    brand_id: int
    brand_name: str
    window_start: datetime
    window_end: datetime
    mention_count: int
    mention_ids: List[int] = []
    batch_label: str
    last_digest_id: Optional[str] = None
    last_digest_created_at: Optional[datetime] = None


class GenerateDigestRequest(BaseModel):
    save_report: bool = True
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    mention_ids: Optional[List[int]] = None


class GenerateDigestResponse(BaseModel):
    success: bool
    message: str
    brand_id: int
    brand_name: str
    window_start: datetime
    window_end: datetime
    mention_count: int
    digest_text: str
    report_id: Optional[str] = None


class DigestSummary(BaseModel):
    id: str
    title: str
    content: str
    brand_id: Optional[int] = None
    brand_name: Optional[str] = None
    created_at: datetime


@router.get("/jobs", response_model=List[DigestJobSummary])
async def get_digest_jobs(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user=Depends(get_current_user),
):
    """List recent mention batches that can be turned into digests."""
    profile = await crud.get_profile(current_user.id)
    is_admin = profile and profile.get("role") == "admin"
    brands = await crud.get_all_brands() if is_admin else await crud.get_brands_by_profile(current_user.id)
    reports = await crud.get_reports_by_user(current_user.id)
    latest_digest_by_brand: Dict[int, Dict[str, Any]] = {}
    for report in reports:
        if report.get("report_type") != "summary" or not str(report.get("title", "")).startswith("Digest:"):
            continue
        brand_id = report.get("brand_id")
        if brand_id is None or brand_id in latest_digest_by_brand:
            continue
        latest_digest_by_brand[int(brand_id)] = report

    summaries: List[DigestJobSummary] = []
    for brand in brands:
        rows = await crud.get_recent_mention_batch_timestamps(brand_id=brand["id"], limit=500)
        latest_digest = latest_digest_by_brand.get(int(brand["id"]))

        batches: Dict[datetime, List[int]] = {}
        for row in rows:
            window_start, _ = get_mention_batch_window(row.get("created_at"))
            batches.setdefault(window_start, []).append(int(row["id"]))

        if not batches:
            fallback_start, fallback_end = get_latest_digest_window(brand)
            summaries.append(
                DigestJobSummary(
                    brand_id=brand["id"],
                    brand_name=brand["name"],
                    window_start=fallback_start,
                    window_end=fallback_end,
                    mention_count=0,
                    mention_ids=[],
                    batch_label="latest-scheduled-window",
                    last_digest_id=str(latest_digest["id"]) if latest_digest else None,
                    last_digest_created_at=latest_digest.get("created_at") if latest_digest else None,
                )
            )
            continue

        for index, (window_start, mention_ids) in enumerate(
            sorted(batches.items(), key=lambda item: item[0], reverse=True)[:10],
            start=1,
        ):
            summaries.append(
                DigestJobSummary(
                    brand_id=brand["id"],
                    brand_name=brand["name"],
                    window_start=window_start,
                    window_end=window_start + timedelta(minutes=1),
                    mention_count=len(mention_ids),
                    mention_ids=mention_ids,
                    batch_label=f"batch-{index}",
                    last_digest_id=str(latest_digest["id"]) if latest_digest else None,
                    last_digest_created_at=latest_digest.get("created_at") if latest_digest else None,
                )
            )

    return sorted(summaries, key=lambda item: item.window_end, reverse=True)


@router.get("/summaries", response_model=List[DigestSummary])
async def get_digest_summaries(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user=Depends(get_current_user),
):
    """List previously generated digest summaries."""
    reports = await crud.get_reports_by_user(current_user.id)
    digest_reports = [
        report
        for report in reports
        if report.get("report_type") == "summary" and str(report.get("title", "")).startswith("Digest:")
    ]
    return [
        DigestSummary(
            id=str(report["id"]),
            title=report["title"],
            content=report["content"],
            brand_id=report.get("brand_id"),
            brand_name=(report.get("brands") or {}).get("name") if report.get("brands") else None,
            created_at=report["created_at"],
        )
        for report in digest_reports
    ]


@router.post("/jobs/{brand_id}/generate", response_model=GenerateDigestResponse)
async def generate_digest_for_job(
    brand_id: int,
    request: GenerateDigestRequest,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user=Depends(get_current_user),
):
    """Generate a DeepSeek digest for the latest scrape window of a brand."""
    try:
        result = await generate_digest_text_supabase(
            crud=crud,
            brand_id=brand_id,
            user_id=current_user.id,
            window_start=request.window_start,
            window_end=request.window_end,
            mention_ids=request.mention_ids,
            save_report=request.save_report,
        )
        return GenerateDigestResponse(**result)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate digest: {str(e)}",
        )

@router.post("/send/{brand_id}", response_model=DigestResponse)
async def send_digest(
    brand_id: int,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Send digest of new mentions for a specific brand to its webhook
    
    Args:
        brand_id: ID of the brand to send digest for
        
    Returns:
        DigestResponse with result information
    """
    
    # Verify brand exists and belongs to current user
    brand = await crud.get_brand(brand_id)
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    try:
        # Create and send the digest
        result = await create_and_send_digest_supabase(crud, brand_id)
        
        return DigestResponse(
            success=result["success"],
            message=result["message"],
            mentions_sent=result["mentions_sent"],
            mentions_updated=result.get("mentions_updated", 0),
            webhook_url=result.get("webhook_url", "")
        )
        
    except ValueError as e:
        # Configuration or data errors (not found, no webhook, etc.)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send digest: {str(e)}"
        )

@router.post("/send/user", response_model=Dict[str, Any])
async def send_user_digest(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Send digest for all brands belonging to the current user
    """
    try:
        # Get all brands for the user
        brands = await crud.get_brands_by_profile(current_user.id)
        
        if not brands:
            return {
                "success": True,
                "message": "No brands found for user",
                "results": []
            }
        
        results = []
        total_sent = 0
        
        # Process each brand
        for brand in brands:
            try:
                result = await create_and_send_digest_supabase(crud, brand["id"])
                results.append({
                    "brand_id": brand["id"],
                    "brand_name": brand["name"],
                    **result
                })
                total_sent += result["mentions_sent"]
                
            except Exception as e:
                results.append({
                    "brand_id": brand["id"],
                    "brand_name": brand["name"],
                    "success": False,
                    "message": f"Error: {str(e)}",
                    "mentions_sent": 0
                })
        
        return {
            "success": True,
            "message": f"Processed {len(brands)} brands, sent {total_sent} total mentions",
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send user digest: {str(e)}"
        )
