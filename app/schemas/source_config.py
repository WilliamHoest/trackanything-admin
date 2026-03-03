from pydantic import BaseModel, Field, field_validator
from pydantic import model_validator
from typing import List, Literal, Optional
from datetime import datetime
import uuid
from urllib.parse import urlparse


def _is_valid_absolute_http_url(value: str) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

class SourceConfigBase(BaseModel):
    """Base schema for source configuration"""
    domain: str = Field(..., description="Domain name (e.g., berlingske.dk)", max_length=255)
    title_selector: Optional[str] = Field(None, description="CSS selector for article title", max_length=500)
    content_selector: Optional[str] = Field(None, description="CSS selector for article content", max_length=500)
    date_selector: Optional[str] = Field(None, description="CSS selector for publication date", max_length=500)
    search_url_pattern: Optional[str] = Field(None, description="URL pattern for searching. Use {keyword} as placeholder (e.g., https://domain.com/search?q={keyword})", max_length=500)
    rss_urls: Optional[List[str]] = Field(None, description="RSS/Atom feed URLs (used when discovery_type=rss)")
    sitemap_url: Optional[str] = Field(None, description="News sitemap URL (used when discovery_type=sitemap)", max_length=500)
    discovery_type: Optional[Literal["rss", "sitemap", "site_search"]] = Field(
        None,
        description="Discovery strategy: rss | sitemap | site_search",
    )

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
    @field_validator("search_url_pattern")
    @classmethod
    def validate_search_url_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        if not value:
            return None
        if "{keyword}" not in value:
            raise ValueError("search_url_pattern must include the {keyword} placeholder")
        if not _is_valid_absolute_http_url(value.replace("{keyword}", "test")):
            raise ValueError("search_url_pattern must be an absolute http(s) URL pattern")
        return value

    @field_validator("rss_urls")
    @classmethod
    def validate_rss_urls(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned: List[str] = []
        for url in v:
            candidate = (url or "").strip()
            if not candidate:
                continue
            if not _is_valid_absolute_http_url(candidate):
                raise ValueError("rss_urls must contain absolute http(s) URLs")
            cleaned.append(candidate)
        return cleaned or None

    @field_validator("sitemap_url")
    @classmethod
    def validate_sitemap_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        if not value:
            return None
        if not _is_valid_absolute_http_url(value):
            raise ValueError("sitemap_url must be an absolute http(s) URL")
        return value

    @model_validator(mode="after")
    def validate_discovery_fields(self):
        if self.discovery_type == "rss" and not self.rss_urls:
            raise ValueError("discovery_type='rss' requires rss_urls")
        if self.discovery_type == "sitemap" and not self.sitemap_url:
            raise ValueError("discovery_type='sitemap' requires sitemap_url")
        if self.discovery_type == "site_search":
            if not self.search_url_pattern:
                raise ValueError("discovery_type='site_search' requires search_url_pattern")
            if "{keyword}" not in self.search_url_pattern:
                raise ValueError("search_url_pattern must include {keyword} for site_search")
        return self


class SourceConfigUpdate(BaseModel):
    """Schema for updating a source configuration"""
    title_selector: Optional[str] = Field(None, max_length=500)
    content_selector: Optional[str] = Field(None, max_length=500)
    date_selector: Optional[str] = Field(None, max_length=500)
    search_url_pattern: Optional[str] = Field(None, max_length=500)
    rss_urls: Optional[List[str]] = None
    sitemap_url: Optional[str] = Field(None, max_length=500)
    discovery_type: Optional[Literal["rss", "sitemap", "site_search"]] = None

    @field_validator("search_url_pattern")
    @classmethod
    def validate_search_url_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        if not value:
            return None
        if "{keyword}" not in value:
            raise ValueError("search_url_pattern must include the {keyword} placeholder")
        if not _is_valid_absolute_http_url(value.replace("{keyword}", "test")):
            raise ValueError("search_url_pattern must be an absolute http(s) URL pattern")
        return value

    @field_validator("rss_urls")
    @classmethod
    def validate_rss_urls(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned: List[str] = []
        for url in v:
            candidate = (url or "").strip()
            if not candidate:
                continue
            if not _is_valid_absolute_http_url(candidate):
                raise ValueError("rss_urls must contain absolute http(s) URLs")
            cleaned.append(candidate)
        return cleaned or None

    @field_validator("sitemap_url")
    @classmethod
    def validate_sitemap_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        if not value:
            return None
        if not _is_valid_absolute_http_url(value):
            raise ValueError("sitemap_url must be an absolute http(s) URL")
        return value

    @model_validator(mode="after")
    def validate_discovery_fields(self):
        if self.discovery_type == "rss" and not self.rss_urls:
            raise ValueError("discovery_type='rss' requires rss_urls in update payload")
        if self.discovery_type == "sitemap" and not self.sitemap_url:
            raise ValueError("discovery_type='sitemap' requires sitemap_url in update payload")
        if self.discovery_type == "site_search":
            if not self.search_url_pattern:
                raise ValueError("discovery_type='site_search' requires search_url_pattern in update payload")
            if "{keyword}" not in self.search_url_pattern:
                raise ValueError("search_url_pattern must include {keyword} for site_search")
        return self


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
    search_url_pattern: Optional[str] = None
    confidence: str = Field(default="low", description="Confidence level: low, medium, high")
    message: str = Field(default="Analysis completed", description="Human-readable message")
