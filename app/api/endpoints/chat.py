from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.database import get_db
from app.core.config import settings
from app.crud import crud
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
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Stream AI chat response with user's mention data context"""
    try:
        # Get the user's profile from the database
        profile = crud.get_profile(db, current_user.id)
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
        
        async def generate():
            try:
                async for chunk in get_ai_chat_response(
                    db=db,
                    current_user=profile,
                    message=request.message,
                    conversation_history=conversation_history
                ):
                    # Format as Server-Sent Events
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                
                # Send final event to signal completion
                yield f"data: [DONE]\n\n"
                    
            except Exception as e:
                error_message = f"Error generating response: {str(e)}"
                yield f"data: {json.dumps({'error': error_message})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat request: {str(e)}"
        )

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """Non-streaming chat endpoint for simpler integrations"""
    try:
        # Get the user's profile from the database
        profile = crud.get_profile(db, current_user.id)
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
        
        # Collect all response chunks
        response_content = ""
        async for chunk in get_ai_chat_response(
            db=db,
            current_user=profile,
            message=request.message,
            conversation_history=conversation_history
        ):
            response_content += chunk
        
        return ChatResponse(content=response_content)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat request: {str(e)}"
        )