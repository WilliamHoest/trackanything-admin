from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

class BrandBase(BaseModel):
    name: str

class BrandCreate(BrandBase):
    scrape_frequency_hours: Optional[int] = 24
    is_active: Optional[bool] = True

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    scrape_frequency_hours: Optional[int] = None
    is_active: Optional[bool] = None

class BrandResponse(BrandBase):
    id: int
    profile_id: uuid.UUID
    scrape_frequency_hours: int
    is_active: bool
    last_scraped_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

# For nested responses
class BrandWithTopics(BrandResponse):
    topics: List["TopicResponse"] = []

# Import needed for forward reference
from app.schemas.topic import TopicResponse
BrandWithTopics.model_rebuild()
