import feedparser
import asyncio
from typing import List, Dict
from datetime import datetime, timezone, timedelta

async def scrape_rss(keywords: List[str]) -> List[Dict]:
    """
    Scraper RSS feeds via Google News RSS endpoint.

    NOTE: Da vi søger på keywords, er RSS lidt tricky.
    Normalt abonnerer man på et feed URL.
    Her laver vi en Google News RSS søgning som fallback/gratis alternativ.
    Dette giver os data uden API key limits (dog med rate limits).
    """
    if not keywords:
        print("⚠️ No keywords provided for RSS scraping")
        return []

    mentions = []

    # Vi bruger Google News RSS endpoint som en gratis "hack"
    # Det giver os data uden API key limits (dog med rate limits)
    base_url = "https://news.google.com/rss/search?q={}&hl=da&gl=DK&ceid=DK:da"

    # Limit for at undgå for mange requests
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    print(f"🔍 RSS: Scraping {len(keywords)} keyword(s) via Google News RSS...")

    for keyword in keywords:
        try:
            url = base_url.format(keyword.replace(" ", "+"))

            # feedparser er blokerende, så vi kører det i en thread
            feed = await asyncio.to_thread(feedparser.parse, url)

            if not hasattr(feed, 'entries'):
                continue

            for entry in feed.entries:
                try:
                    # Parse published date
                    published_parsed = entry.get("published_parsed")
                    if published_parsed:
                        published_dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)

                        # Skip old articles
                        if published_dt < since:
                            continue

                    # Extract link (Google News RSS wraps the real link)
                    link = entry.get("link", "")

                    mentions.append({
                        "title": entry.get("title", "Ingen titel"),
                        "link": link,
                        "content_teaser": entry.get("summary", "")[:200],
                        "platform": "Google RSS",
                        "published_parsed": published_parsed,
                    })
                    print(f"  📰 RSS match: {entry.get('title', 'Ingen titel')[:60]}")

                except Exception as entry_error:
                    print(f"  ⚠️ RSS entry parse error: {entry_error}")
                    continue

        except Exception as e:
            print(f"⚠️ RSS fejl for '{keyword}': {e}")
            continue

    print(f"✅ RSS: Found {len(mentions)} articles")
    return mentions
