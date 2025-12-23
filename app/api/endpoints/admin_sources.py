"""
Admin Source Configuration API Endpoints

This module provides API endpoints for managing source configurations.
These endpoints allow admins to:
1. Analyze a URL to extract CSS selectors
2. View all saved source configurations
3. Delete source configurations

Separation of Concerns:
- This endpoint file handles HTTP request/response
- SourceConfigService handles business logic (URL analysis, LLM interaction)
- SupabaseCRUD handles database operations
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.schemas.source_config import (
    SourceConfigAnalysisRequest,
    SourceConfigAnalysisResponse,
    SourceConfigResponse
)
from app.security.auth import get_current_user
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.source_config_service import SourceConfigService

router = APIRouter()


@router.post("/analyze", response_model=SourceConfigAnalysisResponse)
async def analyze_source_url(
    request: SourceConfigAnalysisRequest,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Analyze a URL to extract CSS selectors for scraping.

    This endpoint:
    1. Fetches the HTML from the provided URL
    2. Analyzes the structure to suggest CSS selectors
    3. Saves the configuration to the database
    4. Returns the suggested selectors

    **Admin only**: This is intended for admin users to configure new sources.

    Example request:
    ```json
    {
        "url": "https://berlingske.dk/some-article"
    }
    ```

    Example response:
    ```json
    {
        "domain": "berlingske.dk",
        "title_selector": "article h1",
        "content_selector": "article .article-body",
        "date_selector": "time[datetime]",
        "confidence": "high",
        "message": "Configuration saved for berlingske.dk"
    }
    ```
    """
    try:
        service = SourceConfigService(crud)
        result = await service.analyze_url(request.url)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze URL: {str(e)}"
        )


@router.get("/configs", response_model=List[dict])
async def get_all_source_configs(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Get all saved source configurations.

    Returns a list of all domains that have been configured with CSS selectors.

    Example response:
    ```json
    [
        {
            "id": "uuid-here",
            "domain": "berlingske.dk",
            "title_selector": "article h1",
            "content_selector": "article .article-body",
            "date_selector": "time[datetime]",
            "created_at": "2025-12-23T10:00:00Z",
            "updated_at": "2025-12-23T10:00:00Z"
        }
    ]
    ```
    """
    try:
        service = SourceConfigService(crud)
        configs = await service.list_all_configs()
        return configs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve configurations: {str(e)}"
        )


@router.get("/configs/{domain}", response_model=dict)
async def get_source_config_by_domain(
    domain: str,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Get source configuration for a specific domain.

    Args:
        domain: The domain to look up (e.g., "berlingske.dk")

    Returns:
        Source configuration for the domain

    Raises:
        404: If no configuration exists for the domain
    """
    try:
        service = SourceConfigService(crud)
        config = await service.get_config_for_domain(domain)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No configuration found for domain: {domain}"
            )

        return config
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve configuration: {str(e)}"
        )


@router.delete("/configs/{domain}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_config(
    domain: str,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Delete a source configuration by domain.

    Args:
        domain: The domain to delete (e.g., "berlingske.dk")

    Returns:
        204 No Content on success

    Raises:
        404: If no configuration exists for the domain
    """
    try:
        service = SourceConfigService(crud)
        success = await service.delete_config(domain)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No configuration found for domain: {domain}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete configuration: {str(e)}"
        )


@router.post("/configs/{domain}/refresh", response_model=SourceConfigAnalysisResponse)
async def refresh_source_config(
    domain: str,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Refresh source configuration by re-analyzing the homepage.

    Finds a fresh article from the homepage and re-analyzes CSS selectors.

    Args:
        domain: The domain to refresh (e.g., "berlingske.dk")

    Returns:
        Updated configuration with new selectors and verification URL

    Raises:
        404: If no article URL found on homepage
        500: If refresh fails
    """
    try:
        service = SourceConfigService(crud)
        result = await service.refresh_config_from_homepage(domain)

        if result.confidence == "low" and "No article URL found" in result.message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.message
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh configuration: {str(e)}"
        )
