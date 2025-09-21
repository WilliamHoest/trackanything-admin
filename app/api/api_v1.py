from fastapi import APIRouter
from app.api.endpoints import topics, scraping, users, brands, digests

api_router = APIRouter()

api_router.include_router(brands.router, prefix="/brands", tags=["brands"])
api_router.include_router(topics.router, prefix="/topics", tags=["topics"])
api_router.include_router(scraping.router, prefix="/scraping", tags=["scraping"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(digests.router, prefix="/digests", tags=["digests"])