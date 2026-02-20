"""
User Context Model for AI Agent Dependency Injection
"""

from typing import Any, Dict, List, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.schemas.mention import MentionContext

if TYPE_CHECKING:
    from app.crud.supabase_crud import SupabaseCRUD
else:
    SupabaseCRUD = Any


class UserContext(BaseModel):
    """User context passed to AI agent via dependency injection"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: str
    user_profile: Dict[str, Any]
    brands: List[Dict[str, Any]]
    recent_mentions: List[MentionContext]
    recent_mentions_count: int
    crud: SupabaseCRUD | None = None  # SupabaseCRUD instance for tool access
