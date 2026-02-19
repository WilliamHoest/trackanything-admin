from fastapi import FastAPI
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from app.api.api_v1 import api_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.services.scraping.core.metrics import render_metrics, render_scraping_metrics
import logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Enable detailed HTTP logging for debugging AI requests
logging.getLogger('httpx').setLevel(logging.DEBUG)
logging.getLogger('httpcore').setLevel(logging.DEBUG)

app = FastAPI(
    title="TrackAnything Admin API",
    description="Backend API for TrackAnything admin application with Supabase REST API",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

logger.info("TrackAnything Admin API starting...")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "TrackAnything Admin API is running!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "3.0.0", "database": "Supabase REST API"}

@app.get("/metrics")
async def metrics():
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)

@app.get("/metrics/scraping")
async def scraping_metrics():
    payload, content_type = render_scraping_metrics()
    return Response(content=payload, media_type=content_type)

@app.get("/dev-info")
async def dev_info():
    return {
        "database": "Supabase REST API",
        "debug_mode": settings.debug,
        "auth_mode": "development" if settings.debug else "production",
        "message": "🚀 Development mode: No login required!" if settings.debug else "🔒 Production mode: Authentication required"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
