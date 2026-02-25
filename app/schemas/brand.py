from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

class BrandBase(BaseModel):
    name: str
    description: Optional[str] = None

class BrandCreate(BrandBase):
    scrape_frequency_hours: Optional[int] = 24
    is_active: Optional[bool] = True
    initial_lookback_days: Optional[int] = 1
    allowed_languages: Optional[List[str]] = None

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scrape_frequency_hours: Optional[int] = None
    is_active: Optional[bool] = None
    initial_lookback_days: Optional[int] = None
    allowed_languages: Optional[List[str]] = None

class BrandResponse(BrandBase):
    id: int
    profile_id: uuid.UUID
    description: Optional[str] = None
    scrape_frequency_hours: int
    is_active: bool
    initial_lookback_days: int = 1
    last_scraped_at: Optional[datetime] = None
    created_at: datetime
    allowed_languages: Optional[List[str]] = None

    class Config:
        from_attributes = True

# For nested responses
class BrandWithTopics(BrandResponse):
    topics: List["TopicWithKeywords"] = []

# Import needed for forward reference
from app.schemas.topic import TopicWithKeywords
BrandWithTopics.model_rebuild()
