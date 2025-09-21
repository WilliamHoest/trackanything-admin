from supabase import create_client, Client
from app.core.config import settings

class SupabaseClient:
    _instance: Client = None
    
    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            cls._instance = create_client(
                supabase_url=settings.supabase_url,
                supabase_key=settings.supabase_key
            )
        return cls._instance

def get_supabase() -> Client:
    return SupabaseClient.get_client()