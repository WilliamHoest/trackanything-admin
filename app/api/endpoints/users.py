from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from app.core.supabase_client import get_supabase

router = APIRouter()

class UserLogin(BaseModel):
    email: EmailStr
    password: str

@router.post("/login")
async def login(user_login: UserLogin):
    supabase = get_supabase()
    
    try:
        response = supabase.auth.sign_in_with_password({
            "email": user_login.email,
            "password": user_login.password
        })
        
        if response.session:
            return response.session
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )