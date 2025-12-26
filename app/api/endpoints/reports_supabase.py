from fastapi import APIRouter, Depends, HTTPException, status, Path, Query
from typing import List, Optional
from uuid import UUID
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.security.auth import get_current_user
from app.schemas import report as report_schemas

router = APIRouter()

@router.get("/", response_model=List[report_schemas.ReportMetadata])
async def get_reports(
    brand_id: Optional[int] = Query(None, description="Filter by brand ID"),
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Get all reports for the current user, optionally filtered by brand"""
    reports = await crud.get_reports_by_user(current_user.id, brand_id=brand_id)
    return reports

@router.get("/{report_id}", response_model=report_schemas.ReportResponse)
async def get_report(
    report_id: UUID = Path(..., description="The ID of the report to retrieve"),
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Get a specific report by ID with full content"""
    report = await crud.get_report_by_id(report_id, current_user.id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    return report

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID = Path(..., description="The ID of the report to delete"),
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Delete a report"""
    success = await crud.delete_report(report_id, current_user.id)
    if not success:
        # Check if it was not found or if it failed
        existing = await crud.get_report_by_id(report_id, current_user.id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete report"
        )
    return None
