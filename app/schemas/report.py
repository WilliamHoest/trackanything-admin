from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class ReportBase(BaseModel):
    title: str
    content: str
    report_type: str = Field(..., pattern="^(weekly|crisis|summary|custom)$")
    brand_id: Optional[int] = None

class ReportCreate(ReportBase):
    pass

class ReportResponse(ReportBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    brands: Optional[Dict[str, Any]] = None  # Nested brand data from join

    class Config:
        from_attributes = True

class ReportMetadata(BaseModel):
    """Lightweight report metadata for list views"""
    id: UUID
    title: str
    report_type: str
    brand_id: Optional[int] = None
    brands: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True
