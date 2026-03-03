from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.ai_setup import AIAutoSetupRequest, AIAutoSetupResponse
from app.schemas.brand import BrandCreate
from app.schemas.topic import TopicCreate
from app.schemas.keyword import KeywordCreate
from app.security.auth import get_current_user
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.services.ai.setup_assistant import generate_setup

router = APIRouter()


@router.post("/auto-setup", response_model=AIAutoSetupResponse, status_code=status.HTTP_201_CREATED)
async def ai_auto_setup(
    request: AIAutoSetupRequest,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user=Depends(get_current_user),
):
    """Generate brand monitoring setup via AI and persist it to Supabase."""
    # 1. Generate topics + keywords with AI
    try:
        topics = await generate_setup(request.brand_name, request.description)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI generation failed: {str(e)}",
        )

    if not topics:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AI returned no topics",
        )

    # 2. Create brand
    brand = await crud.create_brand(
        BrandCreate(name=request.brand_name, description=request.description),
        current_user.id,
    )
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create brand",
        )

    brand_id: int = brand["id"]
    topics_created = 0
    keywords_created = 0

    # 3. Create topics and keywords
    for topic_data in topics:
        topic = await crud.create_topic(TopicCreate(name=topic_data.name), brand_id)
        if not topic:
            continue
        topics_created += 1
        topic_id: int = topic["id"]

        for keyword_text in topic_data.keywords:
            result = await crud.create_keyword(KeywordCreate(text=keyword_text), topic_id)
            if result:
                keywords_created += 1

    return AIAutoSetupResponse(
        brand_id=brand_id,
        brand_name=request.brand_name,
        topics_created=topics_created,
        keywords_created=keywords_created,
    )
