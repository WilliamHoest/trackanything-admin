from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.api_v1 import api_router
from app.core.config import settings
from app.core.database import engine
from app.models import models

# Create database tables (optional - tables should already exist from SQL migration)
# models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TrackAnything Admin API",
    description="Backend API for TrackAnything admin application with SQLAlchemy ORM",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "TrackAnything Admin API is running!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}

@app.get("/dev-info")
async def dev_info():
    return {
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