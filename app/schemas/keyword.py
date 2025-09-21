from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class KeywordBase(BaseModel):
    text: str

class KeywordCreate(KeywordBase):
    pass

class KeywordUpdate(BaseModel):
    text: Optional[str] = None

class KeywordResponse(KeywordBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True