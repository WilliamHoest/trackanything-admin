from fastapi import Depends, HTTPException, status
from app.core.config import settings
import uuid

class MockUser:
    """Mock user for development"""
    def __init__(self, user_id: str, email: str):
        self.id = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        self.email = email

def get_dev_user():
    """
    Development-only: Returns a mock user without database operations
    Only works when DEBUG=True
    """
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Development auth only available in debug mode"
        )
    
    # Use your real user ID from Supabase auth
    dev_user_id = uuid.UUID("db186e82-e79c-45c8-bb4a-0261712e269c")
    dev_email = "madsrunge@hotmail.dk"
    
    # Create mock user
    mock_user = MockUser(dev_user_id, dev_email)
    print(f"🚀 Using development user: {dev_email}")
    
    return mock_user