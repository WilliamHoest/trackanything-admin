import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import httpx
import trafilatura

from app.services.scraping.core.date_utils import parse_mention_date
from app.services.scraping.core.http_client import TIMEOUT_SECONDS, fetch_with_retry, get_default_headers
from app.services.scraping.core.text_processing import (
    compile_keyword_patterns,
    keyword_match_score,
    normalize_url,
)

logger = logging.getLogger("scraping")

# (platform_name, sitemap_url, url_must_contain)
FONDE_SITEMAP_SOURCES: List[Tuple[str, str, Optional[str]]] = [
    (
        "Fondenesvidenscenter.dk",
        "https://fondenesvidenscenter.dk/news-sitemap.xml",
        None,
    ),
    (
        "Godfondsledelse.dk",
        "https://godfondsledelse.dk/sitemap.xml",
        "/nyheder",
    ),
]

MAX_ARTICLES_PER_SOURCE = 40
MAX_CONCURRENT_FETCHES = 4

SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[FONDE_SITEMAP] %s", prefix, message)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_sitemap_xml(xml_bytes: bytes) -> List[Tuple[str, Optional[datetime], Optional[str]]]:
    """Returns list of (url, date, title) from sitemap XML."""
    results = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return results

    for url_el in root.findall("sm:url", SITEMAP_NS):
        loc = url_el.findtext("sm:loc", namespaces=SITEMAP_NS)
        if not loc:
            continue

        # Try news sitemap date first, then lastmod
        raw_date = (
            url_el.findtext("news:news/news:publication_date", namespaces=SITEMAP_NS)
            or url_el.findtext("sm:lastmod", namespaces=SITEMAP_NS)
        )
        title = url_el.findtext("news:news/news:title", namespaces=SITEMAP_NS)

        parsed_date = parse_mention_date(raw_date) if raw_date else None
        results.append((normalize_url(loc), parsed_date, title))

    return results


async def _fetch_sitemap(
    client: httpx.AsyncClient,
    platform: str,
    sitemap_url: str,
    scrape_run_id: Optional[str] = None,
) -> List[Tuple[str, Optional[datetime], Optional[str]]]:
    headers = get_default_headers()
    headers["Accept"] = "application/xml, text/xml, */*"
    try:
        response = await fetch_with_retry(
            client,
            sitemap_url,
            rate_profile="html",
            metrics_provider="fonde_sitemap",
            headers=headers,
        )
        entries = await asyncio.to_thread(_parse_sitemap_xml, response.content)
        _log(scrape_run_id, f"{platform}: parsed {len(entries)} sitemap URLs", logging.DEBUG)
        return entries
    except Exception as exc:
        _log(scrape_run_id, f"{platform}: sitemap fetch failed ({type(exc).__name__}: {exc})", logging.WARNING)
        return []


async def _fetch_and_extract(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    url: str,
    scrape_run_id: Optional[str] = None,
) -> Optional[Dict]:
    async with semaphore:
        try:
            response = await fetch_with_retry(
                client,
                url,
                rate_profile="html",
                metrics_provider="fonde_sitemap",
                headers=get_default_headers(),
            )
            if response.status_code != 200:
                return None

            html = response.text
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
            }
        except Exception as exc:
            _log(scrape_run_id, f"Article fetch failed for {url}: {exc}", logging.DEBUG)
            return None


async def scrape_fonde_sitemap(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
) -> List[Dict]:
    if not keywords:
        return []

    since = _normalize_utc(from_date) or (datetime.now(timezone.utc) - timedelta(hours=24))
    patterns = compile_keyword_patterns(keywords)
    mentions: List[Dict] = []
    seen_links: set[str] = set()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

    _log(scrape_run_id, f"Fetching {len(FONDE_SITEMAP_SOURCES)} sitemaps, since={since.isoformat()}")

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        for platform, sitemap_url, url_filter in FONDE_SITEMAP_SOURCES:
            entries = await _fetch_sitemap(client, platform, sitemap_url, scrape_run_id)

            # Filter by URL pattern and date
            candidates = []
            for url, date, sitemap_title in entries:
                if url_filter and url_filter not in url:
                    continue
                if date is not None and date < since:
                    continue
                if url not in seen_links:
                    candidates.append((url, date, sitemap_title))

            # Most recent first, cap at max
            candidates = candidates[:MAX_ARTICLES_PER_SOURCE]
            _log(scrape_run_id, f"{platform}: {len(candidates)} candidate URLs after date/filter")

            # Fetch articles in parallel (with semaphore)
            fetch_tasks = [
                _fetch_and_extract(client, semaphore, url, scrape_run_id)
                for url, _, _ in candidates
            ]
            fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

            kept = 0
            for (url, sitemap_date, sitemap_title), extracted in zip(candidates, fetch_results):
                if not extracted or isinstance(extracted, Exception):
                    continue

                title = extracted.get("title") or sitemap_title or ""
                text = extracted.get("text", "")
                raw_date = extracted.get("date") or sitemap_date

                published_dt = parse_mention_date(raw_date) if raw_date else sitemap_date
                if published_dt is not None and published_dt < since:
                    continue

                if patterns and keyword_match_score(patterns, f"{title}\n{text}") < 1:
                    continue

                if url in seen_links:
                    continue
                seen_links.add(url)

                mentions.append({
                    "title": title.strip(),
                    "link": url,
                    "content_teaser": text[:200].strip(),
                    "platform": platform,
                    "published_parsed": published_dt.timetuple() if published_dt else None,
                })
                kept += 1

            _log(scrape_run_id, f"{platform}: kept {kept}/{len(candidates)}")

    _log(scrape_run_id, f"Total: {len(mentions)} mentions from fonde sitemaps")
    return mentions
