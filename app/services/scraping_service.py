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
from app.crud.supabase_crud import SupabaseCRUD


# === Configuration ===
TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
RETRY_WAIT_MIN = 2  # seconds
RETRY_WAIT_MAX = 8  # seconds

# Initialize User-Agent rotator
ua = UserAgent()

# Politiken discovery configuration
POLITIKEN_BASE_URL = "https://politiken.dk"
POLITIKEN_SECTIONS = [
    "/",               # forsiden
    "/senestenyt",     # seneste nyt
    "/danmark",
    "/udland",
    "/kultur",
]

# DR RSS feeds for discovery
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


async def _get_config_for_domain(domain: str) -> Optional[Dict]:
    """
    Get saved source configuration for a specific domain.

    This method allows the scraping service to be a "consumer" of
    configurations created by the SourceConfigService.

    Args:
        domain: The domain to look up (e.g., 'berlingske.dk')

    Returns:
        Dictionary with CSS selectors or None if not configured
    """
    try:
        # Normalize domain (remove www. and protocol)
        domain = domain.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        crud = SupabaseCRUD()
        config = await crud.get_source_config_by_domain(domain)

        if config:
            print(f"✅ Found source config for {domain}")
            print(f"   Title: {config.get('title_selector')}")
            print(f"   Content: {config.get('content_selector')}")
            print(f"   Date: {config.get('date_selector')}")

        return config
    except Exception as e:
        print(f"⚠️ Error fetching config for {domain}: {e}")
        return None


async def _scrape_article_content(
    url: str,
    keywords: List[str]
) -> Optional[Dict]:
    """
    Unified method to scrape article content from any URL.

    This method is the core of the configuration-based scraping system:
    1. Extracts domain from URL
    2. Tries to load configuration from database
    3. If config exists, uses it for extraction
    4. If no config, falls back to generic "best guess" extraction
    5. Checks for keyword match
    6. Returns article data or None

    Args:
        url: The article URL to scrape
        keywords: List of keywords to match

    Returns:
        Article dictionary if successful and matches keywords, None otherwise
    """
    if not keywords:
        return None

    patterns = compile_keyword_patterns(keywords)

    try:
        # Extract domain from URL
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        # Try to get configuration for this domain
        config = await _get_config_for_domain(domain)

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            headers = {"User-Agent": get_random_user_agent()}
            response = await fetch_with_retry(client, url, headers=headers)
            soup = BeautifulSoup(response.text, "lxml")

            title = ""
            content = ""
            date_str = ""

            if config:
                # Use database configuration
                print(f"   🔧 Using DB config for {domain}")

                # Extract title
                if config.get('title_selector'):
                    title_elem = soup.select_one(config['title_selector'])
                    if title_elem:
                        title = title_elem.get_text(strip=True)

                # Extract content
                if config.get('content_selector'):
                    content_elem = soup.select_one(config['content_selector'])
                    if content_elem:
                        content = content_elem.get_text(strip=True)

                # Extract date
                if config.get('date_selector'):
                    date_elem = soup.select_one(config['date_selector'])
                    if date_elem:
                        date_str = date_elem.get('datetime') or date_elem.get_text(strip=True)

            else:
                # Fallback to generic "best guess" extraction
                print(f"   ⚙️ Using generic extraction for {domain} (no config)")

                # Try common title patterns
                title_elem = (
                    soup.select_one('article h1') or
                    soup.select_one('h1[itemprop="headline"]') or
                    soup.select_one('h1.article-title') or
                    soup.select_one('header h1') or
                    soup.select_one('h1')
                )
                if title_elem:
                    title = title_elem.get_text(strip=True)

                # Try common content patterns
                content_elem = (
                    soup.select_one('[itemprop="articleBody"]') or
                    soup.select_one('article .article-content') or
                    soup.select_one('.article-body') or
                    soup.select_one('article')
                )
                if content_elem:
                    content = content_elem.get_text(strip=True)

                # Try common date patterns
                date_elem = (
                    soup.select_one('time[datetime]') or
                    soup.select_one('[itemprop="datePublished"]') or
                    soup.select_one('time.published')
                )
                if date_elem:
                    date_str = date_elem.get('datetime') or date_elem.get_text(strip=True)

            # Check for keyword match
            text_to_search = f"{title} {content}"
            if keyword_matches_text(patterns, text_to_search):
                platform = get_platform_from_url(url)

                # Parse date if available
                published_parsed = None
                if date_str:
                    try:
                        parsed_date = dateparser.parse(date_str)
                        if parsed_date:
                            if parsed_date.tzinfo is None:
                                parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                            published_parsed = parsed_date.timetuple()
                    except Exception:
                        pass

                # Use current time as fallback
                if not published_parsed:
                    since = datetime.now(timezone.utc) - timedelta(hours=24)
                    published_parsed = since.timetuple()

                article = {
                    "title": title or "Uden titel",
                    "link": url,
                    "published_parsed": published_parsed,
                    "platform": platform,
                    "content_teaser": content[:500] if content else ""
                }

                config_status = "config" if config else "generic"
                print(f"   📰 {platform} match ({config_status}): {title}")
                return article

            return None

    except Exception as e:
        print(f"   ⚠️ Failed to scrape {url}: {e}")
        return None


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
    Scrape Politiken for articles matching keywords.

    Architecture:
    - Phase 1 (Discovery): Find article URLs from section pages
    - Phase 2 (Extraction): Use _scrape_article_content for each URL
      (which uses database configs if available)

    This method is now config-agnostic - all parsing logic happens
    in the unified _scrape_article_content method.
    """
    if not keywords:
        return []

    print("🔍 Politiken: Starting discovery phase...")
    discovered_urls = set()

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        # Phase 1: Discovery - Find article URLs
        for section in POLITIKEN_SECTIONS:
            url = POLITIKEN_BASE_URL + section

            try:
                headers = {"User-Agent": get_random_user_agent()}
                response = await fetch_with_retry(client, url, headers=headers)
                soup = BeautifulSoup(response.text, "lxml")

                # Find all article links
                for link in soup.select("a[href]"):
                    href = link.get("href", "")

                    if not href or "art" not in href:  # Only want articles
                        continue

                    full_url = urljoin(POLITIKEN_BASE_URL, href)
                    normalized_url = normalize_url(full_url)

                    # Avoid duplicates
                    if normalized_url not in discovered_urls:
                        discovered_urls.add(normalized_url)

            except Exception as e:
                print(f"   ⚠️ Section {section} failed: {e}")
                continue

        print(f"   ✅ Discovered {len(discovered_urls)} unique article URLs")

    # Phase 2: Extraction - Scrape each URL using unified method
    print("🔍 Politiken: Starting extraction phase...")
    articles = []

    for article_url in discovered_urls:
        if len(articles) >= max_articles:
            break

        try:
            # Use the unified extraction method (config-aware)
            article = await _scrape_article_content(article_url, keywords)
            if article:
                articles.append(article)

        except Exception as e:
            print(f"   ⚠️ Failed to extract {article_url}: {e}")
            continue

    print(f"✅ Politiken: Found {len(articles)} matching articles")
    return articles


async def scrape_dr(
    keywords: List[str],
    max_articles: int = 50
) -> List[Dict]:
    """
    Scrape DR RSS feeds for articles matching keywords.

    Architecture:
    - Phase 1 (Discovery): Find article URLs from RSS feeds
    - Phase 2 (Extraction): Use _scrape_article_content for each URL
      (which uses database configs if available)

    This method is now config-agnostic - all parsing logic happens
    in the unified _scrape_article_content method.
    """
    if not keywords:
        return []

    print("🔍 DR: Starting discovery phase (RSS)...")
    discovered_urls = []
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Phase 1: Discovery - Find article URLs from RSS feeds
    for feed_url in DR_FEEDS:
        try:
            # feedparser is synchronous, run in executor
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            for entry in feed.entries:
                link = getattr(entry, "link", None)

                if not link:
                    continue

                # Parse published date to filter old articles
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                # Skip if too old
                if published and published < since:
                    continue

                # Normalize and avoid duplicates
                normalized_url = normalize_url(link)
                if normalized_url not in discovered_urls:
                    discovered_urls.append(normalized_url)

        except Exception as e:
            print(f"   ⚠️ Feed {feed_url} failed: {e}")
            continue

    print(f"   ✅ Discovered {len(discovered_urls)} recent article URLs from RSS")

    # Phase 2: Extraction - Scrape each URL using unified method
    print("🔍 DR: Starting extraction phase...")
    articles = []

    for article_url in discovered_urls:
        if len(articles) >= max_articles:
            break

        try:
            # Use the unified extraction method (config-aware)
            article = await _scrape_article_content(article_url, keywords)
            if article:
                articles.append(article)

        except Exception as e:
            print(f"   ⚠️ Failed to extract {article_url}: {e}")
            continue

    print(f"✅ DR: Found {len(articles)} matching articles")
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
