from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    supabase_service_role_key: str  # Needed for admin operations (creating users)
    deepseek_api_key: str
    deepseek_model: str = "deepseek-chat"  # DeepSeek V3 model for relevance filtering
    gnews_api_key: str
    serpapi_key: str
    tavily_api_key: str = ""  # Optional web search tool
    database_url: str = ""  # PostgreSQL connection string
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
    scraping_rate_html_rps: float = 1.5
    scraping_rate_api_rps: float = 3.0
    scraping_rate_rss_rps: float = 2.0
    scraping_provider_gnews_enabled: bool = True
    scraping_provider_serpapi_enabled: bool = True
    scraping_provider_configurable_enabled: bool = True
    scraping_provider_rss_enabled: bool = True
    scraping_max_keywords_per_run: int = 50
    scraping_max_total_urls_per_run: int = 200
    scraping_blind_domain_circuit_threshold: int = 8
    scraping_historical_dedup_enabled: bool = True
    scraping_historical_dedup_days: int = 3
    scraping_historical_dedup_limit: int = 1000
    scraping_fuzzy_dedup_enabled: bool = True
    scraping_fuzzy_dedup_threshold: int = 92
    scraping_fuzzy_dedup_day_window: int = 2
    
    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
