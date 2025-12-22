from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase_client import get_supabase
from typing import Optional
from app.crud.supabase_crud import supabase_crud

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        supabase = get_supabase()
        
        # Verify the JWT token with Supabase
        user_response = supabase.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise credentials_exception
            
        return user_response.user
        
    except Exception as e:
        print(f"Auth error: {e}")
        raise credentials_exception

async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

async def get_current_admin(user = Depends(get_current_user)):
    """
    verifies that the current user has the 'admin' role.
    """
    try:
        profile = await supabase_crud.get_profile(user.id)
        if not profile:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User profile not found",
            )
            
        if profile.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The user doesn't have enough privileges",
            )
        return user
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        print(f"Admin check error: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not verify admin privileges",
        )
