from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
import httpx

from app.core.config import settings
from app.services.scraping.core.http_client import (
    fetch_with_retry, 
    get_random_user_agent, 
    TIMEOUT_SECONDS
)
from app.services.scraping.core.text_processing import clean_keywords

async def scrape_serpapi(keywords: List[str], from_date: Optional[datetime] = None) -> List[Dict]:
    """
    Fetch articles from SerpAPI (Google News).
    Uses async httpx with retry logic.
    
    Args:
        keywords: List of keywords to search for
        from_date: Optional datetime to filter articles from. Defaults to 24 hours ago.
    """
    if not keywords or not settings.serpapi_key:
        if not settings.serpapi_key:
            print("⚠️ SERPAPI_KEY is not set.")
        return []

    cleaned = clean_keywords(keywords)
    query = " OR ".join(cleaned)
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "engine": "google_news",
        "hl": "da",
        "gl": "dk",
        "api_key": settings.serpapi_key
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            from app.services.scraping.core.http_client import get_default_headers
            headers = get_default_headers()
            response = await fetch_with_retry(client, url, headers=headers, params=params)
            data = response.json()

            entries = []
            # Use provided from_date or default to 24 hours ago
            since = from_date if from_date else datetime.now(timezone.utc) - timedelta(hours=24)

            for item in data.get("news_results", []):
                if "title" not in item or "link" not in item or "date" not in item:
                    continue

                try:
                    raw_date = item["date"].replace(", +0000 UTC", "")
                    parsed = dateparser.parse(raw_date)

                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    else:
                        parsed = parsed.astimezone(timezone.utc)

                    if parsed < since:
                        continue

                    entry = {
                        "title": item["title"],
                        "link": item["link"],
                        "published_parsed": parsed.timetuple(),
                        "platform": "SerpApi",
                        "content_teaser": item.get("snippet") or item.get("description", "")
                    }
                    entries.append(entry)
                    print(f"🔎 SerpAPI match: {item['title']}")

                except Exception as e:
                    print(f"⚠️ SerpAPI article parse error: {e}")
                    continue

            return entries

    except Exception as e:
        print(f"❌ SerpAPI request failed: {e}")
        return []
