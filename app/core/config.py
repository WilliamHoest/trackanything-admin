from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    deepseek_api_key: str
    gnews_api_key: str
    serpapi_key: str
    database_url: str = ""  # PostgreSQL connection string
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()