from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.database import get_db
from app.core.config import settings
from app.crud import crud
from app.schemas.keyword import KeywordCreate, KeywordResponse

# Use development auth in debug mode, real auth in production
get_user = get_dev_user if settings.debug else get_current_user

router = APIRouter()

@router.get("/", response_model=List[KeywordResponse])
def get_keywords(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Get all keywords
    """
    keywords = crud.get_keywords(db, skip=skip, limit=limit)
    return keywords

@router.post("/", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED)
def create_keyword(
    keyword: KeywordCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Create a new keyword
    """
    # Check if keyword already exists
    existing = crud.get_keyword_by_text(db, keyword.text)
    if existing:
        return existing
        
    return crud.create_keyword(db, keyword)

@router.get("/{keyword_id}", response_model=KeywordResponse)
def get_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Get a specific keyword
    """
    keyword = crud.get_keyword(db, keyword_id)
    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keyword not found"
        )
    return keyword

@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(
    keyword_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    """
    Delete a keyword
    """
    success = crud.delete_keyword(db, keyword_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keyword not found"
        )