from fastapi import APIRouter, Depends, HTTPException, status, Path
from typing import List
from uuid import UUID
from app.core.config import settings
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.security.auth import get_current_user
from app.schemas.chat_history import ChatCreate, ChatResponse

router = APIRouter()

@router.post("/", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    chat_in: ChatCreate,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Create a new empty chat session"""
    chat = await crud.create_chat(current_user.id, chat_in.title)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chat"
        )
    return chat

@router.get("/", response_model=List[ChatResponse])
async def get_chats(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """List all chats for the current user"""
    chats = await crud.get_chats(current_user.id)
    return chats

@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat_details(
    chat_id: UUID = Path(..., title="The ID of the chat to get"),
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Get a specific chat with all its messages"""
    chat = await crud.get_chat_details(chat_id, current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )
    return chat

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID = Path(..., title="The ID of the chat to delete"),
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """Delete a conversation"""
    success = await crud.delete_chat(chat_id, current_user.id)
    if not success:
        # Check if it was not found or if it failed
        existing = await crud.get_chat_details(chat_id, current_user.id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat"
        )
    return None
