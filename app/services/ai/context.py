"""
User Context Model for AI Agent Dependency Injection
"""

from typing import List, Dict, Any
from pydantic import BaseModel


class UserContext(BaseModel):
    """User context passed to AI agent via dependency injection"""
    user_id: str
    user_profile: Dict[str, Any]
    brands: List[Dict[str, Any]]
    recent_mentions: List[Dict[str, Any]]
    recent_mentions_count: int
