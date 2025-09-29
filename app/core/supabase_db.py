from app.crud.supabase_crud import SupabaseCRUD, supabase_crud
from typing import Generator

def get_supabase_crud() -> SupabaseCRUD:
    """
    Dependency function to get Supabase CRUD instance
    This replaces the SQLAlchemy get_db() dependency
    """
    return supabase_crud