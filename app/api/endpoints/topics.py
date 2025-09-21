from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.topic import TopicCreate, TopicUpdate, TopicResponse
from app.security.auth import get_current_user
from app.core.supabase_client import get_supabase

router = APIRouter()

@router.get("/", response_model=List[TopicResponse])
async def get_topics(current_user = Depends(get_current_user)):
    supabase = get_supabase()
    
    try:
        result = supabase.table("topics").select("*").eq("user_id", current_user.id).execute()
        return result.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching topics: {str(e)}"
        )

@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(topic_id: str, current_user = Depends(get_current_user)):
    supabase = get_supabase()
    
    try:
        result = supabase.table("topics").select("*").eq("id", topic_id).eq("user_id", current_user.id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Topic not found"
            )
        
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching topic: {str(e)}"
        )

@router.post("/", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(topic: TopicCreate, current_user = Depends(get_current_user)):
    supabase = get_supabase()
    
    try:
        topic_data = {
            "title": topic.title,
            "description": topic.description,
            "user_id": current_user.id
        }
        
        result = supabase.table("topics").insert(topic_data).execute()
        
        return result.data[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating topic: {str(e)}"
        )

@router.put("/{topic_id}", response_model=TopicResponse)
async def update_topic(topic_id: str, topic: TopicUpdate, current_user = Depends(get_current_user)):
    supabase = get_supabase()
    
    try:
        # First check if topic exists and belongs to user
        existing_result = supabase.table("topics").select("*").eq("id", topic_id).eq("user_id", current_user.id).execute()
        
        if not existing_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Topic not found"
            )
        
        # Prepare update data
        update_data = {}
        if topic.title is not None:
            update_data["title"] = topic.title
        if topic.description is not None:
            update_data["description"] = topic.description
            
        if not update_data:
            return existing_result.data[0]
        
        result = supabase.table("topics").update(update_data).eq("id", topic_id).eq("user_id", current_user.id).execute()
        
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating topic: {str(e)}"
        )

@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic_id: str, current_user = Depends(get_current_user)):
    supabase = get_supabase()
    
    try:
        # First check if topic exists and belongs to user
        existing_result = supabase.table("topics").select("*").eq("id", topic_id).eq("user_id", current_user.id).execute()
        
        if not existing_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Topic not found"
            )
        
        supabase.table("topics").delete().eq("id", topic_id).eq("user_id", current_user.id).execute()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting topic: {str(e)}"
        )