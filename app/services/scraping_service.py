"""
Production-Ready Async Scraping Service

Features:
- Async I/O with httpx for non-blocking HTTP requests
- Tenacity retry logic with exponential backoff
- Rotating User-Agent headers to avoid blocking
- Regex word boundary matching for precision
- Parallel execution with asyncio.gather
- Robust error handling per source
"""

import asyncio
import re
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse, quote_plus
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dateutil import parser as dateparser

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from fake_useragent import UserAgent

from app.core.config import settings


# === Configuration ===
TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
RETRY_WAIT_MIN = 2  # seconds
RETRY_WAIT_MAX = 8  # seconds

# Initialize User-Agent rotator
ua = UserAgent()

# Politiken configuration
POLITIKEN_BASE_URL = "https://politiken.dk"
POLITIKEN_SECTIONS = [
    "/",               # forsiden
    "/senestenyt",     # seneste nyt
    "/danmark",
    "/udland",
    "/kultur",
]

# DR RSS feeds
DR_FEEDS = [
    "https://www.dr.dk/nyheder/service/feeds/allenyheder",
    "https://www.dr.dk/nyheder/service/feeds/indland",
    "https://www.dr.dk/nyheder/service/feeds/udland",
    "https://www.dr.dk/nyheder/service/feeds/politik",
]


# === Helper Functions ===

def get_random_user_agent() -> str:
    """Get a random User-Agent string"""
    try:
        return ua.random
    except Exception:
        # Fallback if fake-useragent fails
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def clean_keywords(keywords: List[str]) -> List[str]:
    """Clean keywords by removing dots and commas"""
    return [kw.replace(".", "").replace(",", "").strip() for kw in keywords if kw.strip()]


def compile_keyword_patterns(keywords: List[str]) -> List[re.Pattern]:
    """
    Compile regex patterns for word boundary matching.
    This prevents partial matches (e.g., "Gap" won't match "Singapore").
    """
    patterns = []
    for keyword in keywords:
        # Escape special regex characters and add word boundaries
        escaped = re.escape(keyword)
        pattern = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)
        patterns.append(pattern)
    return patterns


def keyword_matches_text(patterns: List[re.Pattern], text: str) -> bool:
    """Check if any keyword pattern matches the text"""
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False


def normalize_url(url: str) -> str:
    """Normalize URL by removing query parameters and fragments"""
    try:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    except Exception:
        return url


def get_platform_from_url(url: str) -> str:
    """Determine platform from URL domain"""
    try:
        domain = urlparse(url).netloc.lower()
        if "politiken" in domain:
            return "Politiken"
        elif "dr.dk" in domain:
            return "DR"
        else:
            return "Unknown"
    except Exception:
        return "Unknown"


# === Retry Decorator for HTTP Requests ===

@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    reraise=True
)
async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    **kwargs
) -> httpx.Response:
    """
    Fetch URL with automatic retry on network errors or 5xx status codes.
    Uses exponential backoff: 2s, 4s, 8s.
    """
    response = await client.get(url, **kwargs)
    response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
    return response


# === Scrapers ===

async def scrape_politiken(
    keywords: List[str],
    max_articles: int = 50
) -> List[Dict]:
    """
    Scrape Politiken sections for articles matching keywords.
    Uses async httpx with retry logic and rotating User-Agent.
    """
    if not keywords:
        return []

    patterns = compile_keyword_patterns(keywords)
    articles = []
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        for section in POLITIKEN_SECTIONS:
            url = POLITIKEN_BASE_URL + section

            try:
                headers = {"User-Agent": get_random_user_agent()}
                response = await fetch_with_retry(client, url, headers=headers)
                soup = BeautifulSoup(response.text, "lxml")

                # Find all article links
                for link in soup.select("a[href]"):
                    href = link.get("href", "")
                    title = link.get_text(strip=True)

                    if not href or not title:
                        continue
                    if "art" not in href:  # Only want articles
                        continue

                    full_url = urljoin(POLITIKEN_BASE_URL, href)

                    # Find teaser text in same article block
                    teaser = ""
                    parent_article = link.find_parent("article")
                    if parent_article:
                        teaser_tag = parent_article.find("p")
                        if teaser_tag:
                            teaser = teaser_tag.get_text(strip=True)

                    # Check for keyword match using regex word boundaries
                    text_to_search = f"{title} {teaser}"
                    if keyword_matches_text(patterns, text_to_search):
                        article = {
                            "title": title,
                            "link": full_url,
                            "published_parsed": since.timetuple(),
                            "platform": "Politiken",
                            "content_teaser": teaser
                        }
                        articles.append(article)
                        print(f"📰 Politiken match: {title}")

                        if len(articles) >= max_articles:
                            return articles

            except Exception as e:
                print(f"⚠️ Politiken section {section} failed: {e}")
                continue

    return articles


async def scrape_dr(
    keywords: List[str],
    max_articles: int = 50
) -> List[Dict]:
    """
    Scrape DR RSS feeds for articles matching keywords.
    feedparser is sync, so we run it in a thread pool.
    """
    if not keywords:
        return []

    patterns = compile_keyword_patterns(keywords)
    articles = []
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    for feed_url in DR_FEEDS:
        try:
            # feedparser is synchronous, run in executor
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            for entry in feed.entries:
                title = getattr(entry, "title", "")
                desc = getattr(entry, "description", "")
                link = getattr(entry, "link", None)
                published = None

                # Parse published date
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                if not link or not title:
                    continue

                # Skip if too old
                if published and published < since:
                    continue

                # Check keyword match using regex
                text_to_search = f"{title} {desc}"
                if keyword_matches_text(patterns, text_to_search):
                    articles.append({
                        "title": title,
                        "link": link,
                        "published_parsed": published.timetuple() if published else since.timetuple(),
                        "platform": "DR",
                        "content_teaser": desc
                    })
                    print(f"📰 DR match: {title}")

                    if len(articles) >= max_articles:
                        return articles

        except Exception as e:
            print(f"⚠️ DR feed {feed_url} failed: {e}")
            continue

    return articles


async def scrape_gnews(keywords: List[str]) -> List[Dict]:
    """
    Fetch articles from GNews API.
    Uses async httpx with retry logic.
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
            headers = {"User-Agent": get_random_user_agent()}
            response = await fetch_with_retry(client, url, headers=headers)
            data = response.json()

            articles_data = data.get("articles", [])
            entries = []
            since = datetime.now(timezone.utc) - timedelta(hours=24)

            for article in articles_data:
                if "url" not in article:
                    continue

                try:
                    published_at = article.get("publishedAt")
                    parsed = dateparser.parse(published_at) if published_at else datetime.now(timezone.utc)

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


async def scrape_serpapi(keywords: List[str]) -> List[Dict]:
    """
    Fetch articles from SerpAPI (Google News).
    Uses async httpx with retry logic.
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
            headers = {"User-Agent": get_random_user_agent()}
            response = await fetch_with_retry(client, url, headers=headers, params=params)
            data = response.json()

            entries = []
            since = datetime.now(timezone.utc) - timedelta(hours=24)

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


# === Master Fetch Function ===

async def fetch_all_mentions(keywords: List[str]) -> List[Dict]:
    """
    Fetch mentions from all sources in parallel using asyncio.gather.

    Benefits:
    - All 4 sources scrape simultaneously (much faster)
    - One failed source doesn't crash the entire batch
    - Returns deduplicated results based on normalized URLs
    """
    if not keywords:
        print("⚠️ No keywords provided for scraping")
        return []

    print(f"🚀 Starting parallel scraping with {len(keywords)} keywords")
    print(f"📝 Keywords: {keywords}")

    # Run all scrapers in parallel
    # return_exceptions=True ensures one failure doesn't crash others
    results = await asyncio.gather(
        scrape_gnews(keywords),
        scrape_serpapi(keywords),
        scrape_politiken(keywords),
        scrape_dr(keywords),
        return_exceptions=True
    )

    # Collect all mentions, handling exceptions
    all_mentions = []
    source_names = ["GNews", "SerpAPI", "Politiken", "DR"]

    for idx, result in enumerate(results):
        source = source_names[idx]
        if isinstance(result, Exception):
            print(f"❌ {source} scraping failed with exception: {result}")
        elif isinstance(result, list):
            print(f"✅ {source}: found {len(result)} articles")
            all_mentions.extend(result)
        else:
            print(f"⚠️ {source}: unexpected result type {type(result)}")

    # Deduplicate based on normalized URLs
    seen_links = set()
    unique_mentions = []

    for mention in all_mentions:
        if "link" not in mention or not mention["link"]:
            continue

        normalized = normalize_url(mention["link"])
        if normalized not in seen_links:
            seen_links.add(normalized)

            # Ensure platform is set
            if "platform" not in mention or not mention["platform"]:
                mention["platform"] = get_platform_from_url(mention["link"])

            unique_mentions.append(mention)

    duplicates_removed = len(all_mentions) - len(unique_mentions)
    print(f"✅ Scraping complete: {len(unique_mentions)} unique mentions ({duplicates_removed} duplicates removed)")

    return unique_mentions
