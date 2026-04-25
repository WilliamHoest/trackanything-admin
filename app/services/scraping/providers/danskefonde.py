import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import trafilatura

from app.services.scraping.core.date_utils import parse_mention_date
from app.services.scraping.core.text_processing import (
    compile_keyword_patterns,
    keyword_match_score,
    normalize_url,
)

logger = logging.getLogger("scraping")

BLOG_URL = "https://danskefonde.org/blog"
PLATFORM = "Danskefonde.org"
MAX_ARTICLES = 30
MAX_CONCURRENT_PAGES = 3

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
]

BROWSER_CONTEXT_OPTIONS = {
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "locale": "da-DK",
    "viewport": {"width": 1280, "height": 800},
}


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[DANSKEFONDE] %s", prefix, message)


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    # Must be on danskefonde.org and have a path deeper than /blog
    if "danskefonde.org" not in parsed.netloc:
        return False
    parts = [p for p in path.split("/") if p]
    return len(parts) >= 2 and parts[0] == "blog"


async def _get_article_links(page, scrape_run_id: Optional[str]) -> List[str]:
    try:
        await page.goto(BLOG_URL, wait_until="networkidle", timeout=30000)
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(el => el.href)"
        )
        articles = list({normalize_url(l) for l in links if _is_article_url(l)})
        _log(scrape_run_id, f"Found {len(articles)} article links on blog listing")
        return articles[:MAX_ARTICLES]
    except Exception as exc:
        _log(scrape_run_id, f"Blog listing fetch failed: {exc}", logging.WARNING)
        return []


async def _fetch_article(page, semaphore: asyncio.Semaphore, url: str, scrape_run_id: Optional[str]) -> Optional[Dict]:
    async with semaphore:
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            result = await asyncio.to_thread(
                trafilatura.bare_extraction,
                html,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if not result:
                return None
            return {
                "title": result.get("title", ""),
                "text": result.get("text", ""),
                "date": result.get("date"),
                "url": url,
            }
        except Exception as exc:
            _log(scrape_run_id, f"Article fetch failed {url}: {exc}", logging.DEBUG)
            return None


async def scrape_danskefonde(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
) -> List[Dict]:
    if not keywords:
        return []

    try:
        from patchright.async_api import async_playwright
    except ImportError:
        _log(scrape_run_id, "patchright not installed — skipping danskefonde scrape", logging.WARNING)
        return []

    since = from_date or (datetime.now(timezone.utc) - timedelta(hours=24))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    patterns = compile_keyword_patterns(keywords)
    mentions: List[Dict] = []

    _log(scrape_run_id, f"Starting Playwright scrape of {BLOG_URL}")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = await browser.new_context(**BROWSER_CONTEXT_OPTIONS)

            listing_page = await context.new_page()
            article_urls = await _get_article_links(listing_page, scrape_run_id)
            await listing_page.close()

            if not article_urls:
                await browser.close()
                return []

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)
            article_pages = [await context.new_page() for _ in range(min(MAX_CONCURRENT_PAGES, len(article_urls)))]

            # Round-robin pages across articles
            tasks = []
            for i, url in enumerate(article_urls):
                page = article_pages[i % len(article_pages)]
                tasks.append(_fetch_article(page, semaphore, url, scrape_run_id))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for page in article_pages:
                await page.close()
            await browser.close()

        kept = 0
        for extracted in results:
            if not extracted or isinstance(extracted, Exception):
                continue

            title = extracted.get("title", "").strip()
            text = extracted.get("text", "").strip()
            url = extracted.get("url", "")
            raw_date = extracted.get("date")

            published_dt = parse_mention_date(raw_date) if raw_date else None
            if published_dt is not None:
                if published_dt.tzinfo is None:
                    published_dt = published_dt.replace(tzinfo=timezone.utc)
                if published_dt < since:
                    continue

            if patterns and keyword_match_score(patterns, f"{title}\n{text}") < 1:
                continue

            mentions.append({
                "title": title,
                "link": url,
                "content_teaser": text[:200],
                "platform": PLATFORM,
                "published_parsed": published_dt.timetuple() if published_dt else None,
            })
            kept += 1

        _log(scrape_run_id, f"Kept {kept}/{len(article_urls)} articles")

    except Exception as exc:
        _log(scrape_run_id, f"Playwright session failed: {exc}", logging.ERROR)

    return mentions
