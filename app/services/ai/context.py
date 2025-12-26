"""
User Context Model for AI Agent Dependency Injection
"""

from typing import List, Dict, Any, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.crud.supabase_crud import SupabaseCRUD


class UserContext(BaseModel):
    """User context passed to AI agent via dependency injection"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: str
    user_profile: Dict[str, Any]
    brands: List[Dict[str, Any]]
    recent_mentions: List[Dict[str, Any]]
    recent_mentions_count: int
    crud: Any = None  # SupabaseCRUD instance for tool access
