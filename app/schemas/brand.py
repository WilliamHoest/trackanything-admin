from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

class BrandBase(BaseModel):
    name: str

class BrandCreate(BrandBase):
    pass

class BrandUpdate(BaseModel):
    name: Optional[str] = None

class BrandResponse(BrandBase):
    id: int
    profile_id: uuid.UUID
    created_at: datetime
    
    class Config:
        from_attributes = True

# For nested responses
class BrandWithTopics(BrandResponse):
    topics: List["TopicResponse"] = []

# Import needed for forward reference
from app.schemas.topic import TopicResponse
BrandWithTopics.model_rebuild()