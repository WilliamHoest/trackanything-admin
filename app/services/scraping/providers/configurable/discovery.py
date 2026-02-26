from datetime import datetime
from typing import Dict, Optional
from urllib.parse import quote_plus, urljoin, urlparse
import asyncio
import logging
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import httpx

from app.services.scraping.core.date_utils import is_within_interval, parse_mention_date
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
                metrics_provider="configurable",
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


async def discover_via_rss(
    client: httpx.AsyncClient,
    config: Dict,
    from_date: Optional[datetime] = None,
    discovery_sem: asyncio.Semaphore = None,
    scrape_run_id: Optional[str] = None,
) -> tuple[str, set[str]]:
    """Discover article URLs from RSS/Atom feed(s) configured in source config.

    Fetches each URL in config['rss_urls'], detects RSS 2.0 vs Atom, and filters
    by from_date at discovery time to avoid fetching stale articles.
    Returns (domain, set[normalized_article_urls]).
    """
    domain = _normalize_domain(config.get("domain", ""))
    if not domain:
        return "", set()

    rss_urls = config.get("rss_urls") or []
    if not rss_urls:
        return domain, set()

    found_urls: set[str] = set()

    for rss_url in rss_urls:
        async with discovery_sem:
            try:
                headers = {"User-Agent": get_random_user_agent()}
                response = await fetch_with_retry(
                    client,
                    rss_url,
                    rate_profile="rss",
                    metrics_provider="configurable",
                    headers=headers,
                )
                soup = BeautifulSoup(response.text, "lxml-xml")
                is_atom = bool(soup.find("feed"))

                if is_atom:
                    for entry in soup.find_all("entry"):
                        link_el = entry.find("link", rel="alternate") or entry.find("link")
                        url = (link_el.get("href", "") if link_el else "").strip()
                        if not url:
                            continue
                        if from_date is not None:
                            pub_el = entry.find("published") or entry.find("updated")
                            raw_date = pub_el.string if pub_el else None
                            if raw_date:
                                pub_dt = parse_mention_date(raw_date)
                                if pub_dt and not is_within_interval(pub_dt, from_date):
                                    continue
                        full_url = normalize_url(url)
                        if _is_candidate_article_url(full_url, domain):
                            found_urls.add(full_url)
                else:
                    # RSS 2.0
                    for item in soup.find_all("item"):
                        link_el = item.find("link")
                        url = (link_el.string or "").strip() if link_el else ""
                        if not url:
                            continue
                        if from_date is not None:
                            pub_date_el = item.find("pubDate")
                            raw_date = pub_date_el.string if pub_date_el else None
                            if raw_date:
                                pub_dt = parse_mention_date(raw_date)
                                if pub_dt and not is_within_interval(pub_dt, from_date):
                                    continue
                        full_url = normalize_url(url)
                        if _is_candidate_article_url(full_url, domain):
                            found_urls.add(full_url)

                _log(scrape_run_id, f"RSS discovery: {len(found_urls)} URLs from {rss_url}", logging.DEBUG)

            except Exception as e:
                _log(scrape_run_id, f"RSS fetch failed for {rss_url} ({domain}): {e}", logging.WARNING)

    return domain, found_urls


# Sitemap XML namespaces
_SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"


def _parse_urlset(
    xml_text: str,
    domain: str,
    from_date: Optional[datetime],
    scrape_run_id: Optional[str],
) -> set[str]:
    """Parse a sitemap <urlset> and return filtered article URLs."""
    urls: set[str] = set()
    try:
        root = ET.fromstring(xml_text)
        for url_el in root.findall(f"{{{_SM_NS}}}url"):
            loc_el = url_el.find(f"{{{_SM_NS}}}loc")
            if loc_el is None or not (loc_el.text or "").strip():
                continue
            article_url = loc_el.text.strip()

            if from_date is not None:
                # Prefer news:publication_date, fall back to lastmod
                raw_date = None
                news_el = url_el.find(f"{{{_NEWS_NS}}}news")
                if news_el is not None:
                    pub_el = news_el.find(f"{{{_NEWS_NS}}}publication_date")
                    if pub_el is not None:
                        raw_date = pub_el.text
                if not raw_date:
                    lastmod_el = url_el.find(f"{{{_SM_NS}}}lastmod")
                    if lastmod_el is not None:
                        raw_date = lastmod_el.text
                if raw_date:
                    pub_dt = parse_mention_date(raw_date)
                    if pub_dt and not is_within_interval(pub_dt, from_date):
                        continue

            full_url = normalize_url(article_url)
            if _is_candidate_article_url(full_url, domain):
                urls.add(full_url)
    except Exception as e:
        _log(scrape_run_id, f"Sitemap urlset parse error for {domain}: {e}", logging.WARNING)
    return urls


async def discover_via_sitemap(
    client: httpx.AsyncClient,
    config: Dict,
    from_date: Optional[datetime] = None,
    discovery_sem: asyncio.Semaphore = None,
    scrape_run_id: Optional[str] = None,
) -> tuple[str, set[str]]:
    """Discover article URLs from a news sitemap configured in source config.

    Handles both <urlset> (direct) and <sitemapindex> (index → child sitemaps).
    For indexes, prioritises sitemaps with 'news' in the URL (max 3 fetched).
    Filters by from_date using <news:publication_date> or <lastmod>.
    Returns (domain, set[normalized_article_urls]).
    """
    domain = _normalize_domain(config.get("domain", ""))
    sitemap_url = (config.get("sitemap_url") or "").strip()
    if not domain or not sitemap_url:
        return domain, set()

    found_urls: set[str] = set()
    child_sitemap_urls: list[str] = []
    headers = {"User-Agent": get_random_user_agent()}

    async with discovery_sem:
        try:
            response = await fetch_with_retry(
                client,
                sitemap_url,
                rate_profile="html",
                metrics_provider="configurable",
                headers=headers,
            )
            root = ET.fromstring(response.text)

            if f"{{{_SM_NS}}}sitemapindex" in root.tag or "sitemapindex" in root.tag:
                # Collect child sitemaps: news-named ones first
                news_urls, other_urls = [], []
                for sm_el in root.findall(f"{{{_SM_NS}}}sitemap"):
                    loc_el = sm_el.find(f"{{{_SM_NS}}}loc")
                    if loc_el is None or not (loc_el.text or "").strip():
                        continue
                    child_url = loc_el.text.strip()
                    (news_urls if "news" in child_url.lower() else other_urls).append(child_url)
                child_sitemap_urls = (news_urls + other_urls)[:3]
            else:
                found_urls.update(_parse_urlset(response.text, domain, from_date, scrape_run_id))

        except Exception as e:
            _log(scrape_run_id, f"Sitemap fetch failed for {sitemap_url} ({domain}): {e}", logging.WARNING)

    for child_url in child_sitemap_urls:
        async with discovery_sem:
            try:
                response = await fetch_with_retry(
                    client,
                    child_url,
                    rate_profile="html",
                    metrics_provider="configurable",
                    headers=headers,
                )
                found_urls.update(_parse_urlset(response.text, domain, from_date, scrape_run_id))
            except Exception as e:
                _log(scrape_run_id, f"Child sitemap fetch failed for {child_url}: {e}", logging.WARNING)

    _log(scrape_run_id, f"Sitemap discovery: {len(found_urls)} URLs from {sitemap_url}", logging.DEBUG)
    return domain, found_urls
