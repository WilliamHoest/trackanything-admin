from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel
from app.security.auth import get_current_user
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.ai import UserContext, stream_chat_response
import json

router = APIRouter()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    conversation_history: List[ChatMessage] = []
    chat_id: Optional[UUID] = None

class ChatResponse(BaseModel):
    content: str
    chat_id: Optional[UUID] = None

@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Stream AI chat response with user's mention data context and history persistence"""
    try:
        # Get the user's profile from Supabase
        profile = await crud.get_profile(current_user.id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        # Handle Chat Persistence
        chat_id = request.chat_id
        
        # 1. If no chat_id, create new chat with auto-generated title
        if not chat_id:
            # Generate title from first 30 chars of message
            title = (request.message[:30] + '...') if len(request.message) > 30 else request.message
            new_chat = await crud.create_chat(current_user.id, title)
            if new_chat:
                chat_id = UUID(new_chat["id"])
        
        # 2. Save User Message
        if chat_id:
            await crud.create_message(chat_id, "user", request.message)
        
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

        # Build context for AI with UserContext model (PydanticAI)
        context = UserContext(
            user_id=str(current_user.id),
            user_profile={
                "name": profile.get("name", ""),
                "email": profile.get("email", ""),
                "phone_number": profile.get("phone_number", ""),
                "company_name": profile.get("company_name", ""),
                "contact_email": profile.get("contact_email", "")
            },
            brands=[{"id": b["id"], "name": b["name"]} for b in brands],
            recent_mentions=recent_mentions[:50],  # Increased from 10 to 50 for tool access
            recent_mentions_count=len(recent_mentions)
        )

        # Get persona from profile (future extension)
        persona = profile.get("ai_persona", "general")
        
        # 3. Stream and Accumulate for Persistence
        async def stream_with_persistence():
            full_response = ""
            # Yield chat_id first if it was newly created (client might need it)
            # But StreamingResponse expects string bytes.
            # We will rely on client re-fetching or handling the chat_id from response headers if we could,
            # but standard StreamingResponse is body-only.
            # Alternatively, we assume client updates URL if they provided no ID, 
            # but since we can't send JSON + Stream easily, we just stream the text.
            # The client will have to refresh the chat list to see the new chat.
            
            async for chunk in stream_chat_response(request.message, conversation_history, context, persona):
                full_response += chunk
                yield chunk
            
            # 4. Save Assistant Message after stream completes
            if chat_id and full_response.strip():
                await crud.create_message(chat_id, "assistant", full_response)
        
        return StreamingResponse(
            stream_with_persistence(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Chat-ID": str(chat_id) if chat_id else "" # Pass Chat ID in header so client knows
            }
        )
        
    except Exception as e:
        print(f"Chat error: {e}") # Log error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat service error: {str(e)}"
        )

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
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

        # Build context for AI with UserContext model (PydanticAI)
        context = UserContext(
            user_id=str(current_user.id),
            user_profile={
                "name": profile.get("name", ""),
                "email": profile.get("email", ""),
                "phone_number": profile.get("phone_number", ""),
                "company_name": profile.get("company_name", ""),
                "contact_email": profile.get("contact_email", "")
            },
            brands=[{"id": b["id"], "name": b["name"]} for b in brands],
            recent_mentions=recent_mentions[:20],  # Limited context for non-streaming
            recent_mentions_count=len(recent_mentions)
        )

        # Get persona from profile (future extension)
        persona = profile.get("ai_persona", "general")
        
        # Convert conversation history
        conversation_history = [
            {"role": msg.role, "content": msg.content} 
            for msg in request.conversation_history
        ]
        
        # Get AI response (collect all chunks)
        response_chunks = []
        async for chunk in stream_chat_response(request.message, conversation_history, context, persona):
            if chunk.strip():
                response_chunks.append(chunk)

        full_response = "".join(response_chunks)
        
        return ChatResponse(content=full_response)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat service error: {str(e)}"
        )