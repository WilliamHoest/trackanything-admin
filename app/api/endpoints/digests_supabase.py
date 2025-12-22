from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.digest_service_supabase import create_and_send_digest_supabase

router = APIRouter()

class DigestResponse(BaseModel):
    success: bool
    message: str
    mentions_sent: int
    mentions_updated: int = 0
    webhook_url: str = ""

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