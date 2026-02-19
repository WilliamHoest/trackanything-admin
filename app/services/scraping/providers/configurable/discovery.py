from typing import Dict, Optional
from urllib.parse import quote_plus, urljoin, urlparse
import asyncio
import logging
import re

from bs4 import BeautifulSoup
import httpx

from app.services.scraping.core.http_client import fetch_with_retry, get_random_user_agent
from app.services.scraping.core.text_processing import normalize_url
from .config import _is_same_or_subdomain, _log, _normalize_domain

ARTICLE_DATE_PATH_PATTERN = re.compile(r"/20\d{2}/\d{2}/\d{2}/")
ARTICLE_ID_PATH_PATTERN = re.compile(r"(?:article|art)\d{5,}|/\d{6,}(?:[./-]|$)", re.IGNORECASE)
LONG_SLUG_SEGMENT_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$", re.IGNORECASE)
NON_ARTICLE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".xml",
    ".rss",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".zip",
    ".css",
    ".js",
    ".json",
)
NON_ARTICLE_PATH_SEGMENTS = {
    "tag",
    "tags",
    "live",
    "services",
    "service",
    "abonnement",
    "abonnementer",
    "kampagner",
    "faq",
    "kontakt",
    "cookiepolitik",
    "cookies",
    "persondata-politik",
    "privatlivspolitik",
    "tilgaengelighed",
    "nyhedsbreve",
    "mine-sider",
    "drtv",
    "om-dr",
    "om_politiken",
}


def _is_likely_article_slug(segment: str) -> bool:
    if len(segment) < 20:
        return False
    return bool(LONG_SLUG_SEGMENT_PATTERN.match(segment))


def _is_candidate_article_url(url: str, source_domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not _is_same_or_subdomain(parsed.netloc, source_domain):
        return False

    path = (parsed.path or "").strip()
    if not path or path == "/":
        return False
    if any(path.lower().endswith(ext) for ext in NON_ARTICLE_EXTENSIONS):
        return False

    normalized_path = path.lower().rstrip("/")
    segments = [s for s in normalized_path.strip("/").split("/") if s]
    if not segments:
        return False

    has_date_path = bool(ARTICLE_DATE_PATH_PATTERN.search(normalized_path + "/"))
    has_article_id = bool(ARTICLE_ID_PATH_PATTERN.search(normalized_path))
    has_slug_signal = any(_is_likely_article_slug(segment) for segment in segments)
    has_article_signal = has_date_path or has_article_id or has_slug_signal
    if not has_article_signal:
        return False

    if any(segment in NON_ARTICLE_PATH_SEGMENTS for segment in segments):
        if not (has_date_path or has_article_id):
            return False

    return True


async def search_single_keyword(
    client: httpx.AsyncClient,
    config: Dict,
    keyword: str,
    discovery_sem: asyncio.Semaphore,
    scrape_run_id: Optional[str] = None,
) -> tuple[str, set[str]]:
    """Search a single keyword on a single source and return discovered candidate URLs."""
    domain = _normalize_domain(config.get("domain", ""))
    if not domain:
        return "", set()

    search_pattern = config["search_url_pattern"]
    found_urls: set[str] = set()

    async with discovery_sem:
        try:
            search_url = search_pattern.replace("{keyword}", quote_plus(keyword))
            headers = {"User-Agent": get_random_user_agent()}
            response = await fetch_with_retry(
                client,
                search_url,
                rate_profile="html",
                headers=headers,
            )
            soup = BeautifulSoup(response.text, "lxml")

            for link in soup.select("a[href]"):
                href = link.get("href", "")
                if not href:
                    continue

                full_url = urljoin(f"https://{domain}", href)
                if _is_candidate_article_url(full_url, domain):
                    found_urls.add(normalize_url(full_url))

        except Exception as e:
            _log(scrape_run_id, f"Search failed for '{keyword}' on {domain}: {e}", logging.WARNING)

    return domain, found_urls
