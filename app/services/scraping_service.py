import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse, quote_plus
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from dateutil import parser as dateparser
from app.core.config import settings

# Politiken scraper
BASE_URL = "https://politiken.dk"

def crawl_politiken(keywords, max_articles=50):
    """
    Crawler Politiken forsiden og sektioner for artikler, 
    og returnerer dem der matcher keywords i titel eller teaser.
    """
    urls_to_check = [
        BASE_URL + "/",               # forsiden
        BASE_URL + "/senestenyt",     # seneste nyt
        BASE_URL + "/danmark",
        BASE_URL + "/udland",
        BASE_URL + "/kultur",
    ]

    all_articles = []
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    for url in urls_to_check:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if r.status_code != 200:
                print(f"⚠️ Politiken {url} gav {r.status_code}")
                continue
        except Exception as e:
            print(f"❌ Fejl ved {url}: {e}")
            continue

        soup = BeautifulSoup(r.text, "lxml")

        # Gennemgå alle links
        for a in soup.select("a[href]"):
            href = a["href"]
            title = a.get_text(strip=True)

            if not href or not title:
                continue
            if "art" not in href:  # vi vil kun have artikler
                continue

            full_url = urljoin(BASE_URL, href)

            # Find evt. teasertekst i samme artikel-blok
            teaser = ""
            parent_article = a.find_parent("article")
            if parent_article:
                teaser_tag = parent_article.find("p")
                if teaser_tag:
                    teaser = teaser_tag.get_text(strip=True)

            # tjek for keyword match i både titel og teaser
            text_to_search = f"{title} {teaser}"
            for kw in keywords:
                if kw.lower() in text_to_search.lower():
                    article = {
                        "title": title,
                        "link": full_url,
                        "published_parsed": since.timetuple(),
                        "platform": "Politiken"
                    }
                    all_articles.append(article)
                    print(f"📰 Politiken match: {title} ({full_url})")
                    break  # undgå dobbelt match af samme artikel

            if len(all_articles) >= max_articles:
                break

    return all_articles

# DR scraper
DR_FEEDS = [
    "https://www.dr.dk/nyheder/service/feeds/allenyheder",
    "https://www.dr.dk/nyheder/service/feeds/indland",
    "https://www.dr.dk/nyheder/service/feeds/udland",
    "https://www.dr.dk/nyheder/service/feeds/politik",
]

def crawl_dr(keywords, max_articles=50):
    """
    Henter artikler fra DR RSS-feeds og returnerer dem, 
    hvis title eller description matcher et keyword.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = []

    for feed_url in DR_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"❌ DR RSS fejl ved {feed_url}: {e}")
            continue

        for entry in feed.entries:
            title = getattr(entry, "title", "")
            desc = getattr(entry, "description", "")
            link = getattr(entry, "link", None)
            published = None

            # DR RSS har altid published_parsed
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            if not link or not title:
                continue

            # skip hvis gammel
            if published and published < since:
                continue

            # check match
            for kw in keywords:
                if kw.lower() in title.lower() or kw.lower() in desc.lower():
                    articles.append({
                        "title": title,
                        "link": link,
                        "published_parsed": published.timetuple() if published else since.timetuple(),
                        "platform": "DR"
                    })
                    print(f"📰 DR match: {title} ({link})")
                    break

            if len(articles) >= max_articles:
                return articles

    return articles

# Helper functions
def clean_keywords(keywords):
    """Clean keywords by removing dots and commas"""
    return [kw.replace(".", "").replace(",", "").strip() for kw in keywords]

# GNews scraper
def fetch_gnews_articles(keywords: List[str]) -> List[Dict]:
    """
    Fetch articles from GNews API based on keywords
    """
    if not settings.gnews_api_key:
        print("❌ GNEWS_API_KEY is not set.")
        return []
    
    cleaned = clean_keywords(keywords)
    query = quote_plus(" OR ".join(cleaned))
    url = f"https://gnews.io/api/v4/search?q={query}&token={settings.gnews_api_key}&lang=da&max=10"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"❌ GNews fetch failed: {response.status_code}")
            return []
        
        articles = response.json().get("articles", [])
        entries = []
        since = datetime.now(timezone.utc) - timedelta(hours=24)   # timezone-aware
        
        for a in articles:
            if "url" not in a:
                continue
            try:
                published_at = a.get("publishedAt")
                parsed = dateparser.parse(published_at) if published_at else datetime.now(timezone.utc)
                
                # Ensure UTC-aware
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                else:
                    parsed = parsed.astimezone(timezone.utc)
                
                if parsed < since:
                    continue
                
                entries.append({
                    "title": a.get("title", "Uden titel"),
                    "link": a["url"],
                    "published_parsed": parsed.timetuple(),
                    "platform": "GNews"
                })
                print(f"🔍 GNews match: {a.get('title', 'Uden titel')} ({a['url']})")
            except Exception as e:
                print(f"⚠️ Kunne ikke parse GNews artikel: {a} – {e}")
        
        return entries
        
    except Exception as e:
        print(f"❌ GNews request failed: {e}")
        return []

def batch_fetch_gnews_articles(keywords: List[str], batch_size: int = 10) -> List[Dict]:
    """
    Fetch GNews articles in batches to handle large keyword lists
    """
    all_articles = []
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]
        articles = fetch_gnews_articles(batch)
        all_articles.extend(articles)
    return all_articles

# SerpAPI scraper
def fetch_serpapi_articles(keywords: List[str]) -> List[Dict]:
    """
    Fetch articles from SerpAPI based on keywords
    """
    if not settings.serpapi_key:
        print("❌ SERPAPI_KEY is not set.")
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
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"❌ SerpAPI fetch failed: {response.status_code}")
            return []
        
        data = response.json()
        entries = []
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        
        for item in data.get("news_results", []):
            if "title" in item and "link" in item and "date" in item:
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
                        "platform": "SerpApi"
                    }
                    entries.append(entry)
                    print(f"🔎 SerpAPI match: {item['title']} ({item['link']})")
                except Exception as e:
                    print(f"⚠️ Kunne ikke parse artikel: {raw_date} – {e}")
            else:
                print(f"⚠️ Ugyldigt SerpAPI-resultat (mangler felt): {item}")
        
        return entries
        
    except Exception as e:
        print(f"❌ SerpAPI request failed: {e}")
        return []

# Helper functions
def normalize_url(url):
    """Normalize URL by removing query parameters and fragments"""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def get_platform_from_url(url):
    """Determine platform from URL domain"""
    domain = urlparse(url).netloc.lower()
    if "politiken" in domain:
        return "Politiken"
    elif "dr.dk" in domain:
        return "DR"
    else:
        return "Unknown"

# Master fetch function
def fetch_all_mentions(keywords: List[str]) -> List[Dict]:
    """
    Fetch all mentions from different sources and deduplicate
    """
    all_mentions = []
    
    # Fetch from GNews
    print(f"🔍 Fetching from GNews with keywords: {keywords}")
    gnews_articles = batch_fetch_gnews_articles(keywords)
    all_mentions.extend(gnews_articles)
    
    # Fetch from SerpAPI
    print(f"🔍 Fetching from SerpAPI with keywords: {keywords}")
    serpapi_articles = fetch_serpapi_articles(keywords)
    all_mentions.extend(serpapi_articles)
    
    # Fetch from Politiken
    print(f"🔍 Fetching from Politiken with keywords: {keywords}")
    politiken_articles = crawl_politiken(keywords)
    all_mentions.extend(politiken_articles)
    
    # Fetch from DR
    print(f"🔍 Fetching from DR with keywords: {keywords}")
    dr_articles = crawl_dr(keywords)
    all_mentions.extend(dr_articles)
    
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
            if "platform" not in mention:
                mention["platform"] = get_platform_from_url(mention["link"])
            unique_mentions.append(mention)
    
    print(f"✅ Found {len(unique_mentions)} unique mentions after deduplication")
    return unique_mentions