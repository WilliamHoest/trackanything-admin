from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class MentionBase(BaseModel):
    caption: str
    post_link: str
    published_at: Optional[datetime] = None
    content_teaser: Optional[str] = None
    primary_keyword_id: Optional[int] = None
    read_status: bool = False
    notified_status: bool = False

class MentionCreate(MentionBase):
    platform_id: int
    brand_id: int
    topic_id: int

class MentionUpdate(BaseModel):
    caption: Optional[str] = None
    content_teaser: Optional[str] = None
    read_status: Optional[bool] = None
    notified_status: Optional[bool] = None

class MentionResponse(MentionBase):
    id: int
    platform_id: int
    brand_id: int
    topic_id: int
    created_at: datetime
    keyword_matches: Optional[List["MentionKeywordMatch"]] = None
    
    class Config:
        from_attributes = True

# For keyword matches
class MentionKeywordMatch(BaseModel):
    keyword: "KeywordResponse"
    matched_in: Optional[str] = None
    score: Optional[int] = None

# For nested responses
class MentionWithDetails(MentionResponse):
    platform: "PlatformResponse"
    brand: "BrandResponse"
    topic: "TopicResponse"

# Import needed for forward references
from app.schemas.platform import PlatformResponse
from app.schemas.brand import BrandResponse
from app.schemas.topic import TopicResponse
from app.schemas.keyword import KeywordResponse
MentionWithDetails.model_rebuild()
MentionKeywordMatch.model_rebuild()
