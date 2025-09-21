from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

class IntegrationConfigBase(BaseModel):
    integration_name: str
    webhook_url: str
    is_active: bool = True

class IntegrationConfigCreate(IntegrationConfigBase):
    pass

class IntegrationConfigUpdate(BaseModel):
    integration_name: Optional[str] = None
    webhook_url: Optional[str] = None
    is_active: Optional[bool] = None

class IntegrationConfigResponse(IntegrationConfigBase):
    id: int
    profile_id: uuid.UUID
    created_at: datetime
    
    class Config:
        from_attributes = True