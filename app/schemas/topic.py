from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TopicBase(BaseModel):
    title: str
    description: Optional[str] = None

class TopicCreate(TopicBase):
    pass

class TopicUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class TopicResponse(TopicBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True