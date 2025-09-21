from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import uuid

class ProfileBase(BaseModel):
    company_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None

class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None

class ProfileResponse(ProfileBase):
    id: uuid.UUID
    created_at: datetime
    
    class Config:
        from_attributes = True