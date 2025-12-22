from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
from pydantic import BaseModel
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.ai_service import get_ai_chat_response
import json

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    conversation_history: List[ChatMessage] = []

class ChatResponse(BaseModel):
    content: str

@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Stream AI chat response with user's mention data context"""
    try:
        # Get the user's profile from Supabase
        profile = await crud.get_profile(current_user.id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        # Convert conversation history to simple dict format
        conversation_history = [
            {"role": msg.role, "content": msg.content} 
            for msg in request.conversation_history
        ]
        
        # Get user's context data (brands, recent mentions, etc.)
        brands = await crud.get_brands_by_profile(current_user.id)
        recent_mentions = await crud.get_mentions_by_profile(
            current_user.id, 
            skip=0, 
            limit=50
        )
        
        # Build context for AI
        context = {
            "user_profile": {
                "name": profile.get("name", ""),
                "email": profile.get("email", ""),
                "phone_number": profile.get("phone_number", ""),
                "company_name": profile.get("company_name", ""),
                "contact_email": profile.get("contact_email", "")
            },
            "brands": [{"id": b["id"], "name": b["name"]} for b in brands],
            "recent_mentions_count": len(recent_mentions),
            "recent_mentions": recent_mentions[:10]  # Only send top 10 for context
        }
        
        # Get AI response with streaming
        return StreamingResponse(
            get_ai_chat_response(request.message, conversation_history, context),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat service error: {str(e)}"
        )

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    """Non-streaming AI chat response (for testing)"""
    try:
        # Get the user's profile from Supabase
        profile = await crud.get_profile(current_user.id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        # Get user's context data
        brands = await crud.get_brands_by_profile(current_user.id)
        recent_mentions = await crud.get_mentions_by_profile(
            current_user.id, 
            skip=0, 
            limit=20
        )
        
        # Build context for AI
        context = {
            "user_profile": {
                "name": profile.get("name", ""),
                "email": profile.get("email", ""),
                "phone_number": profile.get("phone_number", ""),
                "company_name": profile.get("company_name", ""),
                "contact_email": profile.get("contact_email", "")
            },
            "brands": [{"id": b["id"], "name": b["name"]} for b in brands],
            "recent_mentions_count": len(recent_mentions),
            "recent_mentions": recent_mentions[:5]  # Limited context for non-streaming
        }
        
        # Convert conversation history
        conversation_history = [
            {"role": msg.role, "content": msg.content} 
            for msg in request.conversation_history
        ]
        
        # Get AI response (collect all chunks)
        response_chunks = []
        async for chunk in get_ai_chat_response(request.message, conversation_history, context):
            if chunk.strip():
                response_chunks.append(chunk)
        
        full_response = "".join(response_chunks)
        
        return ChatResponse(content=full_response)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat service error: {str(e)}"
        )