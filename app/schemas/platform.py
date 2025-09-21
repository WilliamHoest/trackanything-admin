from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PlatformBase(BaseModel):
    name: str

class PlatformCreate(PlatformBase):
    pass

class PlatformUpdate(BaseModel):
    name: Optional[str] = None

class PlatformResponse(PlatformBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True