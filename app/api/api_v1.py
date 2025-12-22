from fastapi import APIRouter
from app.api.endpoints import (
    brands_supabase, 
    topics_supabase, 
    keywords_supabase, 
    mentions_supabase, 
    users_supabase,
    scraping_supabase,
    digests_supabase,
    chat_supabase,
    chat_history,
    admin_supabase
)

api_router = APIRouter()

# All endpoints now using Supabase REST API 🚀
api_router.include_router(brands_supabase.router, prefix="/brands", tags=["brands"])
api_router.include_router(topics_supabase.router, prefix="/topics", tags=["topics"])
api_router.include_router(keywords_supabase.router, prefix="/keywords", tags=["keywords"])
api_router.include_router(mentions_supabase.router, prefix="/mentions", tags=["mentions"])
api_router.include_router(users_supabase.router, prefix="/users", tags=["users"])
api_router.include_router(scraping_supabase.router, prefix="/scraping", tags=["scraping"])
api_router.include_router(digests_supabase.router, prefix="/digests", tags=["digests"])
api_router.include_router(chat_supabase.router, prefix="/chat", tags=["chat"])
api_router.include_router(chat_history.router, prefix="/chats", tags=["chats"])
api_router.include_router(admin_supabase.router, prefix="/admin", tags=["admin"])