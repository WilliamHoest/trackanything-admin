from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import uuid

class SourceConfigBase(BaseModel):
    """Base schema for source configuration"""
    domain: str = Field(..., description="Domain name (e.g., berlingske.dk)", max_length=255)
    title_selector: Optional[str] = Field(None, description="CSS selector for article title", max_length=500)
    content_selector: Optional[str] = Field(None, description="CSS selector for article content", max_length=500)
    date_selector: Optional[str] = Field(None, description="CSS selector for publication date", max_length=500)

    @field_validator('domain')
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Ensure domain is lowercase and stripped"""
        if not v:
            raise ValueError("Domain cannot be empty")
        # Remove protocol if present
        domain = v.lower().strip()
        if domain.startswith('http://'):
            domain = domain[7:]
        if domain.startswith('https://'):
            domain = domain[8:]
        # Remove trailing slash
        domain = domain.rstrip('/')
        # Remove www. prefix for consistency
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain


class SourceConfigCreate(SourceConfigBase):
    """Schema for creating a new source configuration"""
    pass


class SourceConfigUpdate(BaseModel):
    """Schema for updating a source configuration"""
    title_selector: Optional[str] = Field(None, max_length=500)
    content_selector: Optional[str] = Field(None, max_length=500)
    date_selector: Optional[str] = Field(None, max_length=500)


class SourceConfigResponse(SourceConfigBase):
    """Schema for source configuration response"""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SourceConfigAnalysisRequest(BaseModel):
    """Schema for requesting URL analysis"""
    url: str = Field(..., description="URL to analyze for selector extraction")

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL is valid"""
        if not v:
            raise ValueError("URL cannot be empty")
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v


class SourceConfigAnalysisResponse(BaseModel):
    """Schema for URL analysis response"""
    domain: str
    title_selector: Optional[str] = None
    content_selector: Optional[str] = None
    date_selector: Optional[str] = None
    confidence: str = Field(default="low", description="Confidence level: low, medium, high")
    message: str = Field(default="Analysis completed", description="Human-readable message")
