from pydantic import BaseModel
from typing import List


class AIAutoSetupRequest(BaseModel):
    brand_name: str
    description: str


class AISetupTopic(BaseModel):
    name: str
    keywords: List[str]


class AIAutoSetupResponse(BaseModel):
    brand_id: int
    brand_name: str
    topics_created: int
    keywords_created: int
