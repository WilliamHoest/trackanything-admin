from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from dateutil import parser as dateparser
import httpx

from app.core.config import settings
from app.services.scraping.core.http_client import (
    fetch_with_retry, 
    get_random_user_agent, 
    TIMEOUT_SECONDS
)
from app.services.scraping.core.text_processing import clean_keywords

async def scrape_gnews(keywords: List[str], from_date: Optional[datetime] = None) -> List[Dict]:
    """
    Fetch articles from GNews API.
    Uses async httpx with retry logic.
    
    Args:
        keywords: List of keywords to search for
        from_date: Optional datetime to filter articles from. Defaults to 24 hours ago.
    """
    if not keywords or not settings.gnews_api_key:
        if not settings.gnews_api_key:
            print("⚠️ GNEWS_API_KEY is not set.")
        return []

    cleaned = clean_keywords(keywords)
    query = quote_plus(" OR ".join(cleaned))
    url = f"https://gnews.io/api/v4/search?q={query}&token={settings.gnews_api_key}&lang=da&max=10"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            from app.services.scraping.core.http_client import get_default_headers
            headers = get_default_headers()
            response = await fetch_with_retry(client, url, headers=headers)
            data = response.json()

            articles_data = data.get("articles", [])
            entries = []
            # Use provided from_date or default to 24 hours ago
            since = from_date if from_date else datetime.now(timezone.utc) - timedelta(hours=24)

            for article in articles_data:
                if "url" not in article:
                    continue

                try:
                    published_at = article.get("publishedAt")
                    if not published_at:
                        continue
                    try:
                        parsed = dateparser.parse(published_at)
                    except Exception:
                        continue
                    if parsed is None:
                        continue

                    # Ensure UTC-aware
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    else:
                        parsed = parsed.astimezone(timezone.utc)

                    if parsed < since:
                        continue

                    entries.append({
                        "title": article.get("title", "Uden titel"),
                        "link": article["url"],
                        "published_parsed": parsed.timetuple(),
                        "platform": "GNews",
                        "content_teaser": article.get("description", "")
                    })
                    print(f"🔍 GNews match: {article.get('title', 'Uden titel')}")

                except Exception as e:
                    print(f"⚠️ GNews article parse error: {e}")
                    continue

            return entries

    except Exception as e:
        print(f"❌ GNews request failed: {e}")
        return []
