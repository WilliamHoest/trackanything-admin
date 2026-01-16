from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TopicBase(BaseModel):
    name: str
    description: Optional[str] = None
    query_template: Optional[str] = None
    is_active: bool = True

class TopicCreate(TopicBase):
    keyword_ids: List[int] = []

class TopicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    query_template: Optional[str] = None
    is_active: Optional[bool] = None
    keyword_ids: Optional[List[int]] = None

class TopicResponse(TopicBase):
    id: int
    brand_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# For nested responses
class TopicWithKeywords(TopicResponse):
    keywords: List["KeywordResponse"] = []

# Import needed for forward reference
from app.schemas.keyword import KeywordResponse
TopicWithKeywords.model_rebuild()
