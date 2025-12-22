from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import uuid

class ProfileBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None  # Kept for backwards compatibility
    role: Optional[str] = 'customer'

class ProfileCreate(ProfileBase):
    name: str  # Required when creating
    email: EmailStr  # Required when creating
    role: Optional[str] = 'customer'

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    role: Optional[str] = None

class ProfileResponse(ProfileBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True