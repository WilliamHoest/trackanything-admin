from typing import List, Optional, Dict, Any, Tuple
from supabase import Client
from app.core.supabase_client import get_supabase
from app.schemas import (
    brand as brand_schemas,
    topic as topic_schemas,
    keyword as keyword_schemas,
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
                "description": brand.description,
                "scrape_frequency_hours": brand.scrape_frequency_hours,
                "initial_lookback_days": brand.initial_lookback_days,
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

    async def update_brand_last_scraped(self, brand_id: int) -> bool:
        """Update brand's last_scraped_at timestamp"""
        try:
            result = self.supabase.table("brands").update({
                "last_scraped_at": datetime.utcnow().isoformat()
            }).eq("id", brand_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error updating brand last_scraped_at: {e}")
            return False

    # Topic CRUD
    async def get_topic(self, topic_id: int) -> Optional[Dict[str, Any]]:
        """Get topic by ID with keywords"""
        try:
            result = self.supabase.table("topics").select("*").eq("id", topic_id).execute()
            if not result.data:
                return None

            topic = result.data[0]
            # Fetch keywords via junction table
            keywords = await self.get_keywords_by_topic(topic_id)
            topic["keywords"] = keywords
            return topic
        except Exception as e:
            print(f"Error getting topic: {e}")
            return None

    async def get_topics_by_brand(self, brand_id: int) -> List[Dict[str, Any]]:
        """Get all topics for a brand with keywords"""
        try:
            result = self.supabase.table("topics").select("*").eq("brand_id", brand_id).execute()
            topics = result.data or []

            # Fetch keywords for each topic
            for topic in topics:
                keywords = await self.get_keywords_by_topic(topic["id"])
                topic["keywords"] = keywords

            return topics
        except Exception as e:
            print(f"Error getting topics by brand: {e}")
            return []

    async def create_topic(self, topic: topic_schemas.TopicCreate, brand_id: int) -> Optional[Dict[str, Any]]:
        """Create new topic"""
        try:
            data = {
                "name": topic.name,
                "brand_id": brand_id,
                "query_template": getattr(topic, "query_template", None),
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
                                    read_status: Optional[bool] = None,
                                    from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
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
                platforms(*),
                mention_keywords(keyword_id, matched_in, score, keywords(*))
            """).in_("brand_id", user_brand_ids)
            
            # Apply additional filters
            if platform_id:
                query = query.eq("platform_id", platform_id)

            if read_status is not None:
                query = query.eq("read_status", read_status)

            # Apply date range filters
            if from_date:
                query = query.gte("published_at", from_date.isoformat())

            if to_date:
                query = query.lte("published_at", to_date.isoformat())

            # Order by created_at descending and apply pagination
            query = query.order("created_at", desc=True).range(skip, skip + limit - 1)

            result = query.execute()
            mentions = result.data or []

            # Transform Supabase plural join names to singular for Pydantic schema
            for mention in mentions:
                if "brands" in mention:
                    mention["brand"] = mention.pop("brands")
                if "topics" in mention:
                    mention["topic"] = mention.pop("topics")
                if "platforms" in mention:
                    mention["platform"] = mention.pop("platforms")
                if "mention_keywords" in mention:
                    keyword_matches = []
                    for match in mention.pop("mention_keywords") or []:
                        keyword = match.get("keywords")
                        if keyword:
                            keyword_matches.append({
                                "keyword": keyword,
                                "matched_in": match.get("matched_in"),
                                "score": match.get("score")
                            })
                    mention["keyword_matches"] = keyword_matches

            return mentions
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
        """Get keywords for a topic via junction table"""
        try:
            # Step 1: Get keyword IDs from junction table
            junction_result = self.supabase.table("topic_keywords").select("keyword_id").eq("topic_id", topic_id).execute()

            if not junction_result.data:
                return []

            # Step 2: Extract keyword IDs
            keyword_ids = [item["keyword_id"] for item in junction_result.data]

            if not keyword_ids:
                return []

            # Step 3: Fetch keywords by IDs
            keywords_result = self.supabase.table("keywords").select("*").in_("id", keyword_ids).execute()

            return keywords_result.data or []
        except Exception as e:
            print(f"Error getting keywords by topic: {e}")
            return []

    async def create_keyword(self, keyword: keyword_schemas.KeywordCreate, topic_id: int) -> Optional[Dict[str, Any]]:
        """Create new keyword and link it to topic via junction table"""
        try:
            # Step 1: Check if keyword already exists (text is UNIQUE)
            existing = self.supabase.table("keywords").select("*").eq("text", keyword.text).execute()

            if existing.data:
                # Keyword exists, use it
                keyword_record = existing.data[0]
            else:
                # Create new keyword
                keyword_data = {
                    "text": keyword.text,
                    "created_at": datetime.utcnow().isoformat()
                }
                keyword_result = self.supabase.table("keywords").insert(keyword_data).execute()
                if not keyword_result.data:
                    return None
                keyword_record = keyword_result.data[0]

            # Step 2: Create relationship in topic_keywords junction table
            junction_data = {
                "topic_id": topic_id,
                "keyword_id": keyword_record["id"]
            }
            junction_result = self.supabase.table("topic_keywords").insert(junction_data).execute()

            if not junction_result.data:
                return None

            # Return the keyword record
            return keyword_record
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

    async def delete_keyword(self, topic_id: int, keyword_id: int) -> bool:
        """Delete keyword relationship from topic (via junction table)"""
        try:
            # Delete from topic_keywords junction table
            result = self.supabase.table("topic_keywords").delete().eq("topic_id", topic_id).eq("keyword_id", keyword_id).execute()
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

    async def create_platform(self, name: str) -> Optional[Dict[str, Any]]:
        """Create new platform"""
        try:
            data = {
                "name": name,
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
                "published_at": mention_data.get("published_at"),
                "content_teaser": mention_data.get("content_teaser"),
                "platform_id": mention_data.get("platform_id"),
                "brand_id": mention_data.get("brand_id"),
                "topic_id": mention_data.get("topic_id"),
                "primary_keyword_id": mention_data.get("primary_keyword_id"),
                "read_status": mention_data.get("read_status", False),
                "notified_status": mention_data.get("notified_status", False),
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("mentions").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating mention: {e}")
            return None

    async def batch_create_mentions(self, mentions_data: List[Dict[str, Any]]) -> tuple[int, List[str]]:
        """
        Create multiple mentions using chunked batch upserts.
        Handles duplicates automatically using the (post_link, topic_id) unique constraint.
        This allows multiple brands to track the same URL.
        """
        if not mentions_data:
            return 0, []

        total_saved = 0
        errors = []
        now = datetime.utcnow().isoformat()
        
        # 1. Pre-deduplicate in memory (per topic)
        unique_mentions = {}
        for m in mentions_data:
            link = m.get("post_link")
            topic_id = m.get("topic_id")
            if link and topic_id:
                # Key is now combination of link AND topic_id
                key = (link, topic_id)
                unique_mentions[key] = m
        
        data_to_save = []
        for (link, _), m in unique_mentions.items():
            data_to_save.append({
                "caption": m.get("caption", m.get("title", "")),
                "post_link": link,
                "published_at": m.get("published_at"),
                "content_teaser": m.get("content_teaser"),
                "platform_id": m.get("platform_id"),
                "brand_id": m.get("brand_id"),
                "topic_id": m.get("topic_id"),
                "primary_keyword_id": m.get("primary_keyword_id"),
                "read_status": m.get("read_status", False),
                "notified_status": m.get("notified_status", False),
                "created_at": now
            })

        # 2. Chunk processing (process 100 mentions at a time)
        chunk_size = 100
        for i in range(0, len(data_to_save), chunk_size):
            chunk = data_to_save[i:i + chunk_size]
            try:
                # ignore_duplicates=True means "ON CONFLICT DO NOTHING"
                # Updated to use composite key (post_link, topic_id)
                result = self.supabase.table("mentions").upsert(
                    chunk, 
                    on_conflict="post_link, topic_id", 
                    ignore_duplicates=True
                ).execute()
                
                if result.data:
                    total_saved += len(result.data)
            except Exception as e:
                error_msg = f"Chunk error ({i}-{i+chunk_size}): {str(e)}"
                print(f"❌ {error_msg}")
                errors.append(error_msg)

        print(f"✅ Batch complete: {total_saved} new mentions saved ({len(mentions_data) - total_saved} skipped/duplicates)")
        return total_saved, errors

    async def get_mentions_by_keys(
        self,
        brand_id: int,
        keys: List[Tuple[str, int]]
    ) -> Dict[Tuple[str, int], int]:
        """Fetch mention IDs for (post_link, topic_id) pairs scoped to a brand."""
        if not keys:
            return {}

        post_links = list({key[0] for key in keys})
        topic_ids = list({key[1] for key in keys})
        key_set = set(keys)

        try:
            result = self.supabase.table("mentions").select(
                "id, post_link, topic_id"
            ).eq("brand_id", brand_id).in_("post_link", post_links).in_("topic_id", topic_ids).execute()
            mentions = result.data or []
            return {
                (m["post_link"], m["topic_id"]): m["id"]
                for m in mentions
                if (m["post_link"], m["topic_id"]) in key_set
            }
        except Exception as e:
            print(f"Error getting mentions by keys: {e}")
            return {}

    async def batch_create_mention_keywords(self, matches: List[Dict[str, Any]]) -> List[str]:
        """Create mention-keyword relations in batch with de-duplication."""
        if not matches:
            return []

        errors = []
        now = datetime.utcnow().isoformat()
        data_to_save = [
            {
                "mention_id": m["mention_id"],
                "keyword_id": m["keyword_id"],
                "matched_in": m.get("matched_in"),
                "score": m.get("score"),
                "created_at": now
            }
            for m in matches
            if m.get("mention_id") and m.get("keyword_id")
        ]

        chunk_size = 200
        for i in range(0, len(data_to_save), chunk_size):
            chunk = data_to_save[i:i + chunk_size]
            try:
                self.supabase.table("mention_keywords").upsert(
                    chunk,
                    on_conflict="mention_id, keyword_id",
                    ignore_duplicates=True
                ).execute()
            except Exception as e:
                error_msg = f"Mention-keyword chunk error ({i}-{i+chunk_size}): {str(e)}"
                print(f"❌ {error_msg}")
                errors.append(error_msg)

        return errors

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

    # Generated Reports CRUD
    async def create_report(self, user_id: uuid.UUID, title: str, content: str,
                          report_type: str, brand_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Create a new generated report"""
        try:
            data = {
                "user_id": str(user_id),
                "title": title,
                "content": content,
                "report_type": report_type,
                "brand_id": brand_id,
                "created_at": datetime.utcnow().isoformat()
            }
            result = self.supabase.table("generated_reports").insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating report: {e}")
            return None

    async def get_reports_by_user(self, user_id: uuid.UUID, brand_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all reports for a user, optionally filtered by brand"""
        try:
            query = self.supabase.table("generated_reports").select("""
                *,
                brands(id, name)
            """).eq("user_id", str(user_id))

            # Filter by brand if specified
            if brand_id is not None:
                query = query.eq("brand_id", brand_id)

            query = query.order("created_at", desc=True)
            result = query.execute()
            return result.data or []
        except Exception as e:
            print(f"Error getting reports by user: {e}")
            return []

    async def get_report_by_id(self, report_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get a specific report by ID (with ownership check)"""
        try:
            result = self.supabase.table("generated_reports").select("""
                *,
                brands(id, name)
            """).eq("id", str(report_id)).eq("user_id", str(user_id)).execute()

            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            print(f"Error getting report by id: {e}")
            return None

    async def delete_report(self, report_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete a report (with ownership check)"""
        try:
            result = self.supabase.table("generated_reports").delete().eq("id", str(report_id)).eq("user_id", str(user_id)).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting report: {e}")
            return False

# Create singleton instance
supabase_crud = SupabaseCRUD()
