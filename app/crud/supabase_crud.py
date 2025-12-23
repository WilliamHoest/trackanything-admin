from typing import List, Optional, Dict, Any
from supabase import Client
from app.core.supabase_client import get_supabase
from app.schemas import (
    brand as brand_schemas,
    topic as topic_schemas,
    keyword as keyword_schemas,
    mention as mention_schemas,
    platform as platform_schemas,
    profile as profile_schemas,
    source_config as source_config_schemas,
)
import uuid
from datetime import datetime

class SupabaseCRUD:
    def __init__(self):
        self.supabase: Client = get_supabase()

    # Profile CRUD
    async def get_profile(self, profile_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get profile by ID"""
        try:
            result = self.supabase.table("profiles").select("*").eq("id", str(profile_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting profile: {e}")
            return None

    async def create_profile(self, profile: profile_schemas.ProfileCreate, profile_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Create new profile"""
        try:
            data = {
                "id": str(profile_id),
                "company_name": profile.company_name,
                "contact_email": profile.contact_email,
                "role": profile.role,
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("profiles").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating profile: {e}")
            return None

    async def update_profile(self, profile_id: uuid.UUID, profile: profile_schemas.ProfileUpdate) -> Optional[Dict[str, Any]]:
        """Update profile"""
        try:
            data = profile.model_dump(exclude_unset=True, exclude_none=True)
            result = self.supabase.table("profiles").update(data).eq("id", str(profile_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating profile: {e}")
            return None

    # Brand CRUD
    async def get_brand(self, brand_id: int) -> Optional[Dict[str, Any]]:
        """Get brand by ID"""
        try:
            result = self.supabase.table("brands").select("*").eq("id", brand_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting brand: {e}")
            return None

    async def get_brands_by_profile(self, profile_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Get all brands for a profile"""
        try:
            result = self.supabase.table("brands").select("*").eq("profile_id", str(profile_id)).execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting brands by profile: {e}")
            return []

    async def create_brand(self, brand: brand_schemas.BrandCreate, profile_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Create new brand"""
        try:
            data = {
                "name": brand.name,
                "profile_id": str(profile_id),
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("brands").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating brand: {e}")
            return None

    async def update_brand(self, brand_id: int, brand: brand_schemas.BrandUpdate, profile_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Update brand (with ownership check)"""
        try:
            # First check ownership
            existing = await self.get_brand(brand_id)
            if not existing or existing.get("profile_id") != str(profile_id):
                return None
            
            data = brand.model_dump(exclude_unset=True, exclude_none=True)
            result = self.supabase.table("brands").update(data).eq("id", brand_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating brand: {e}")
            return None

    async def delete_brand(self, brand_id: int, profile_id: uuid.UUID) -> bool:
        """Delete brand (with ownership check)"""
        try:
            # First check ownership
            existing = await self.get_brand(brand_id)
            if not existing or existing.get("profile_id") != str(profile_id):
                return False
            
            result = self.supabase.table("brands").delete().eq("id", brand_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting brand: {e}")
            return False

    # Topic CRUD
    async def get_topic(self, topic_id: int) -> Optional[Dict[str, Any]]:
        """Get topic by ID with keywords"""
        try:
            result = self.supabase.table("topics").select("*, keywords(*)").eq("id", topic_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting topic: {e}")
            return None

    async def get_topics_by_brand(self, brand_id: int) -> List[Dict[str, Any]]:
        """Get all topics for a brand with keywords"""
        try:
            result = self.supabase.table("topics").select("*, keywords(*)").eq("brand_id", brand_id).execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting topics by brand: {e}")
            return []

    async def create_topic(self, topic: topic_schemas.TopicCreate, brand_id: int) -> Optional[Dict[str, Any]]:
        """Create new topic"""
        try:
            data = {
                "name": topic.name,
                "brand_id": brand_id,
                "is_active": topic.is_active if hasattr(topic, 'is_active') else True,
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("topics").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating topic: {e}")
            return None

    async def update_topic(self, topic_id: int, topic: topic_schemas.TopicUpdate) -> Optional[Dict[str, Any]]:
        """Update topic"""
        try:
            data = topic.model_dump(exclude_unset=True, exclude_none=True)
            result = self.supabase.table("topics").update(data).eq("id", topic_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating topic: {e}")
            return None

    async def delete_topic(self, topic_id: int) -> bool:
        """Delete topic"""
        try:
            result = self.supabase.table("topics").delete().eq("id", topic_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting topic: {e}")
            return False

    # Mention CRUD
    async def get_mentions_by_profile(self, profile_id: uuid.UUID, skip: int = 0, limit: int = 50, 
                                    brand_id: Optional[int] = None, platform_id: Optional[int] = None,
                                    read_status: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get mentions with filtering"""
        try:
            # First get user's brand IDs
            brands_result = self.supabase.table("brands").select("id").eq("profile_id", str(profile_id)).execute()
            user_brand_ids = [brand["id"] for brand in brands_result.data or []]
            
            if not user_brand_ids:
                return []
            
            # Filter brand_ids if specific brand requested
            if brand_id:
                if brand_id not in user_brand_ids:
                    return []  # Brand not owned by user
                user_brand_ids = [brand_id]
            
            # Build query for mentions
            query = self.supabase.table("mentions").select("""
                *,
                brands(*),
                topics(*),
                platforms(*)
            """).in_("brand_id", user_brand_ids)
            
            # Apply additional filters
            if platform_id:
                query = query.eq("platform_id", platform_id)
            
            if read_status is not None:
                query = query.eq("read_status", read_status)
            
            # Order by created_at descending and apply pagination
            query = query.order("created_at", desc=True).range(skip, skip + limit - 1)
            
            result = query.execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting mentions: {e}")
            return []

    async def update_mention_read_status(self, mention_id: int, read_status: bool) -> Optional[Dict[str, Any]]:
        """Update mention read status"""
        try:
            result = self.supabase.table("mentions").update({
                "read_status": read_status
            }).eq("id", mention_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating mention read status: {e}")
            return None

    # Keyword CRUD  
    async def get_keywords_by_topic(self, topic_id: int) -> List[Dict[str, Any]]:
        """Get keywords for a topic"""
        try:
            result = self.supabase.table("keywords").select("*").eq("topic_id", topic_id).execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting keywords by topic: {e}")
            return []

    async def create_keyword(self, keyword: keyword_schemas.KeywordCreate, topic_id: int) -> Optional[Dict[str, Any]]:
        """Create new keyword"""
        try:
            data = {
                "word": keyword.word,
                "topic_id": topic_id,
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("keywords").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating keyword: {e}")
            return None

    async def get_keyword(self, keyword_id: int) -> Optional[Dict[str, Any]]:
        """Get keyword by ID"""
        try:
            result = self.supabase.table("keywords").select("*").eq("id", keyword_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting keyword: {e}")
            return None

    async def delete_keyword(self, keyword_id: int) -> bool:
        """Delete keyword"""
        try:
            result = self.supabase.table("keywords").delete().eq("id", keyword_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting keyword: {e}")
            return False

    # Platform CRUD
    async def get_platforms(self) -> List[Dict[str, Any]]:
        """Get all platforms"""
        try:
            result = self.supabase.table("platforms").select("*").execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting platforms: {e}")
            return []

    async def get_platform_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get platform by name"""
        try:
            result = self.supabase.table("platforms").select("*").eq("name", name).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting platform by name: {e}")
            return None

    async def create_platform(self, name: str, logo_url: str = None) -> Optional[Dict[str, Any]]:
        """Create new platform"""
        try:
            data = {
                "name": name,
                "logo_url": logo_url,
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("platforms").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating platform: {e}")
            return None

    # Source Config CRUD
    async def get_source_config_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get source configuration by domain"""
        try:
            result = self.supabase.table("source_configs").select("*").eq("domain", domain).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting source config by domain: {e}")
            return None

    async def get_all_source_configs(self) -> List[Dict[str, Any]]:
        """Get all source configurations"""
        try:
            result = self.supabase.table("source_configs").select("*").order("created_at", desc=True).execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting all source configs: {e}")
            return []

    async def create_or_update_source_config(self, config: source_config_schemas.SourceConfigCreate) -> Optional[Dict[str, Any]]:
        """Create or update source configuration (upsert based on domain)"""
        try:
            # Check if config already exists for this domain
            existing = await self.get_source_config_by_domain(config.domain)

            if existing:
                # Update existing config
                data = config.model_dump(exclude_unset=True, exclude_none=True)
                # Ensure search_url_pattern is included if present in config
                if hasattr(config, 'search_url_pattern'):
                    data['search_url_pattern'] = config.search_url_pattern
                    
                result = self.supabase.table("source_configs").update(data).eq("domain", config.domain).execute()
                return result.data[0] if result.data else None
            else:
                # Create new config
                data = {
                    "domain": config.domain,
                    "title_selector": config.title_selector,
                    "content_selector": config.content_selector,
                    "date_selector": config.date_selector,
                    "search_url_pattern": config.search_url_pattern,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                result = self.supabase.table("source_configs").insert(data).execute()
                return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating/updating source config: {e}")
            return None

    async def delete_source_config_by_domain(self, domain: str) -> bool:
        """Delete source configuration by domain"""
        try:
            result = self.supabase.table("source_configs").delete().eq("domain", domain).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting source config: {e}")
            return False

    # Mention creation for scraping
    async def create_mention(self, mention_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new mention from scraping data"""
        try:
            data = {
                "caption": mention_data.get("caption", ""),
                "post_link": mention_data.get("post_link", ""),
                "published_at": mention_data.get("published_at", datetime.utcnow().isoformat()),
                "content_teaser": mention_data.get("content_teaser"),
                "platform_id": mention_data.get("platform_id"),
                "brand_id": mention_data.get("brand_id"),
                "topic_id": mention_data.get("topic_id"),
                "read_status": mention_data.get("read_status", False),
                "notified_status": mention_data.get("notified_status", False),
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("mentions").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating mention: {e}")
            return None

    # Utility functions for scraping
    async def get_all_user_keywords(self, profile_id: uuid.UUID) -> List[str]:
        """Get all keywords for all active topics of all brands for a user"""
        try:
            # Get user's brands
            brands = await self.get_brands_by_profile(profile_id)
            brand_ids = [brand["id"] for brand in brands]
            
            if not brand_ids:
                return []
            
            # Get all active topics for these brands
            topics_result = self.supabase.table("topics").select("id").in_("brand_id", brand_ids).eq("is_active", True).execute()
            topic_ids = [topic["id"] for topic in topics_result.data or []]
            
            if not topic_ids:
                return []
            
            # Get all keywords for these topics
            keywords_result = self.supabase.table("keywords").select("word").in_("topic_id", topic_ids).execute()
            keywords = [kw["word"] for kw in keywords_result.data or []]
            
            # Return unique keywords
            return list(set(keywords))
        except Exception as e:
            print(f"Error getting user keywords: {e}")
            return []

    # Digest functions
    async def get_webhook_config_by_profile(self, profile_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get webhook configuration for a profile"""
        try:
            result = self.supabase.table("integration_configs").select("*").eq("profile_id", str(profile_id)).eq("type", "webhook").execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting webhook config: {e}")
            return None

    async def get_unsent_mentions_by_brand(self, brand_id: int) -> List[Dict[str, Any]]:
        """Get unsent mentions for a brand with topic information"""
        try:
            result = self.supabase.table("mentions").select("""
                *,
                topics(name)
            """).eq("brand_id", brand_id).eq("notified_status", False).order("created_at", desc=False).execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting unsent mentions: {e}")
            return []

    async def mark_mentions_as_sent(self, mention_ids: List[int]) -> bool:
        """Mark mentions as sent (notified)"""
        try:
            result = self.supabase.table("mentions").update({"notified_status": True}).in_("id", mention_ids).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error marking mentions as sent: {e}")
            return False

    # Chat History CRUD
    async def create_chat(self, user_id: uuid.UUID, title: str = "New Chat") -> Optional[Dict[str, Any]]:
        """Create a new chat session"""
        try:
            data = {
                "user_id": str(user_id),
                "title": title,
                "updated_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("chats").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating chat: {e}")
            return None

    async def get_chats(self, user_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Get all chats for a user"""
        try:
            result = self.supabase.table("chats").select("*").eq("user_id", str(user_id)).order("updated_at", desc=True).execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting chats: {e}")
            return []

    async def get_chat_details(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get chat details with messages"""
        try:
            # First verify ownership and get chat
            chat_result = self.supabase.table("chats").select("*").eq("id", str(chat_id)).eq("user_id", str(user_id)).execute()
            if not chat_result.data:
                return None
            
            chat = chat_result.data[0]
            
            # Get messages
            msgs_result = self.supabase.table("messages").select("*").eq("chat_id", str(chat_id)).order("created_at", desc=False).execute()
            chat["messages"] = msgs_result.data or []
            
            return chat
        except Exception as e:
            print(f"Error getting chat details: {e}")
            return None

    async def delete_chat(self, chat_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a chat session"""
        try:
            # RLS policies should handle the user_id check, but we add it for safety
            result = self.supabase.table("chats").delete().eq("id", str(chat_id)).eq("user_id", str(user_id)).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting chat: {e}")
            return False

    async def update_chat_title(self, chat_id: uuid.UUID, title: str, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Update chat title"""
        try:
            result = self.supabase.table("chats").update({"title": title, "updated_at": datetime.utcnow().isoformat()}).eq("id", str(chat_id)).eq("user_id", str(user_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating chat title: {e}")
            return None

    async def create_message(self, chat_id: uuid.UUID, role: str, content: str) -> Optional[Dict[str, Any]]:
        """Create a new message in a chat"""
        try:
            data = {
                "chat_id": str(chat_id),
                "role": role,
                "content": content,
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("messages").insert(data).execute()
            
            # Update parent chat's updated_at
            self.supabase.table("chats").update({"updated_at": datetime.utcnow().isoformat()}).eq("id", str(chat_id)).execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating message: {e}")
            return None

# Create singleton instance
supabase_crud = SupabaseCRUD()