from typing import List, Dict, Optional, Iterator
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, quote_plus
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
import httpx
import asyncio
import re
import logging

from app.crud.supabase_crud import SupabaseCRUD
from app.services.scraping.core.http_client import (
    fetch_with_retry, 
    get_random_user_agent, 
    TIMEOUT_SECONDS
)
from app.services.scraping.core.text_processing import (
    compile_keyword_patterns, 
    keyword_matches_text, 
    normalize_url, 
    get_platform_from_url
)
from app.core.selectors import (
    GENERIC_TITLE_SELECTORS,
    GENERIC_CONTENT_SELECTORS,
    GENERIC_DATE_SELECTORS
)

logger = logging.getLogger("scraping")


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[Configurable] %s", prefix, message)

DATE_CERTAINTY_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b(19|20)\d{2}\b"
)
ARTICLE_DATE_PATH_PATTERN = re.compile(r"/20\d{2}/\d{2}/\d{2}/")
ARTICLE_ID_PATH_PATTERN = re.compile(r"(?:article|art)\d{5,}|/\d{6,}(?:[./-]|$)", re.IGNORECASE)
LONG_SLUG_SEGMENT_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$", re.IGNORECASE)
NON_ARTICLE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf", ".xml", ".rss",
    ".mp3", ".mp4", ".mov", ".avi", ".zip", ".css", ".js", ".json"
)
NON_ARTICLE_PATH_SEGMENTS = {
    "tag", "tags", "live", "services", "service", "abonnement", "abonnementer",
    "kampagner", "faq", "kontakt", "cookiepolitik", "cookies", "persondata-politik",
    "privatlivspolitik", "tilgaengelighed", "nyhedsbreve", "mine-sider", "drtv",
    "om-dr", "om_politiken"
}


def _normalize_domain(domain: str) -> str:
    domain = (domain or "").strip().lower()
    if not domain:
        return ""
    if "://" in domain:
        domain = urlparse(domain).netloc.lower()
    domain = domain.split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _domain_candidates(domain: str) -> Iterator[str]:
    """
    Yield the most specific domain first, then broader fallbacks.
    Example: a.b.example.com -> a.b.example.com, b.example.com, example.com
    """
    normalized = _normalize_domain(domain)
    if not normalized:
        return
    parts = normalized.split(".")
    for idx in range(0, max(1, len(parts) - 1)):
        candidate = ".".join(parts[idx:])
        if candidate:
            yield candidate


def _is_same_or_subdomain(host: str, domain: str) -> bool:
    host_norm = _normalize_domain(host)
    domain_norm = _normalize_domain(domain)
    return host_norm == domain_norm or host_norm.endswith(f".{domain_norm}")


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
        # Keep URL if it still has strong article signals (e.g. explicit article ID)
        if not (has_date_path or has_article_id):
            return False

    return True


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_date_value(date_elem) -> tuple[str, bool]:
    """
    Return extracted date text and whether it came from a machine-readable attribute.
    """
    attribute_value = date_elem.get("datetime") or date_elem.get("content")
    if attribute_value:
        return attribute_value.strip(), True
    return date_elem.get_text(strip=True), False


def _is_confident_date_for_filtering(date_str: str, from_attribute: bool) -> bool:
    if from_attribute:
        return True
    return bool(DATE_CERTAINTY_PATTERN.search(date_str))


async def _get_config_for_domain(
    domain: str,
    config_cache: Optional[Dict[str, Optional[Dict]]] = None,
    scrape_run_id: Optional[str] = None
) -> Optional[Dict]:
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
        candidates = list(_domain_candidates(domain))
        if not candidates:
            return None

        if config_cache is not None:
            for candidate in candidates:
                if candidate in config_cache:
                    config = config_cache[candidate]
                    if config:
                        # Cache lookup under requested domain too for faster future hits
                        config_cache[candidates[0]] = config
                        return config

            # Known miss in cache for requested domain
            if candidates[0] in config_cache and config_cache[candidates[0]] is None:
                return None

        crud = SupabaseCRUD()
        for candidate in candidates:
            config = await crud.get_source_config_by_domain(candidate)
            if config:
                _log(scrape_run_id, f"Found source config for {candidate}")
                _log(scrape_run_id, f"  Title: {config.get('title_selector')}", logging.DEBUG)
                _log(scrape_run_id, f"  Content: {config.get('content_selector')}", logging.DEBUG)
                _log(scrape_run_id, f"  Date: {config.get('date_selector')}", logging.DEBUG)
                if config_cache is not None:
                    config_cache[candidates[0]] = config
                    config_cache[candidate] = config
                return config

        if config_cache is not None:
            config_cache[candidates[0]] = None
        return None
    except Exception as e:
        _log(scrape_run_id, f"Error fetching config for {domain}: {e}", logging.WARNING)
        return None


async def _scrape_article_content(
    url: str,
    keywords: List[str],
    from_date: Optional[datetime] = None,
    config_cache: Optional[Dict[str, Optional[Dict]]] = None,
    scrape_run_id: Optional[str] = None
) -> Optional[Dict]:
    """
    Unified method to scrape article content from any URL.

    This method is the core of the configuration-based scraping system:
    1. Extracts domain from URL
    2. Tries to load configuration from database
    3. If config exists, uses it for extraction with automatic fallback
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
    from_date_utc = _normalize_utc(from_date)

    try:
        # Extract domain from URL
        parsed = urlparse(url)
        domain = _normalize_domain(parsed.netloc)

        # Try to get configuration for this domain
        config = await _get_config_for_domain(
            domain,
            config_cache=config_cache,
            scrape_run_id=scrape_run_id
        )

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            from app.services.scraping.core.http_client import get_default_headers
            headers = get_default_headers()
            response = await fetch_with_retry(client, url, headers=headers)
            soup = BeautifulSoup(response.text, "lxml")

            title = ""
            content = ""
            date_str = ""
            date_confident = False

            def try_selectors(soup_obj, selectors):
                for selector in selectors:
                    elem = soup_obj.select_one(selector)
                    if elem:
                        return elem
                return None

            # === Title Extraction ===
            if config and config.get('title_selector'):
                title_elem = soup.select_one(config['title_selector'])
                if title_elem:
                    title = title_elem.get_text(strip=True)
            
            if not title:
                if config and config.get('title_selector'):
                    _log(
                        scrape_run_id,
                        f"Configured title selector '{config['title_selector']}' failed or empty. Trying fallbacks.",
                        logging.DEBUG
                    )
                
                title_elem = try_selectors(soup, GENERIC_TITLE_SELECTORS)
                if title_elem:
                    title = title_elem.get_text(strip=True)

            # === Content Extraction ===
            if config and config.get('content_selector'):
                content_elem = soup.select_one(config['content_selector'])
                if content_elem:
                    content = content_elem.get_text(strip=True)
            
            if not content:
                if config and config.get('content_selector'):
                    _log(
                        scrape_run_id,
                        f"Configured content selector '{config['content_selector']}' failed or empty. Trying fallbacks.",
                        logging.DEBUG
                    )
                
                content_elem = try_selectors(soup, GENERIC_CONTENT_SELECTORS)
                if content_elem:
                    content = content_elem.get_text(strip=True)

            # === Date Extraction ===
            if config and config.get('date_selector'):
                date_elem = soup.select_one(config['date_selector'])
                if date_elem:
                    date_str, date_confident = _extract_date_value(date_elem)
                
                # If configured selector failed to find date, log warning but continue to generic fallback
                if not date_str:
                    _log(
                        scrape_run_id,
                        f"Configured date selector '{config['date_selector']}' found no date. Trying fallbacks.",
                        logging.DEBUG
                    )

            if not date_str:
                date_elem = try_selectors(soup, GENERIC_DATE_SELECTORS)
                if date_elem:
                    date_str, date_confident = _extract_date_value(date_elem)

            # Check for keyword match
            text_to_search = f"{title} {content}"
            if keyword_matches_text(patterns, text_to_search):
                # Use config domain as platform name if available, otherwise extract from URL
                if config and config.get('domain'):
                    platform = config['domain']
                else:
                    platform = get_platform_from_url(url)

                # Parse date if available
                published_parsed = None
                if date_str:
                    try:
                        parsed_date = dateparser.parse(date_str)
                        if parsed_date:
                            if parsed_date.tzinfo is None:
                                parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                            else:
                                parsed_date = parsed_date.astimezone(timezone.utc)

                            # Filter by from_date only when we trust the extracted date value.
                            if from_date_utc and parsed_date < from_date_utc:
                                if _is_confident_date_for_filtering(date_str, date_confident):
                                    _log(
                                        scrape_run_id,
                                        f"Date too old for {url}: {parsed_date} < {from_date_utc}",
                                        logging.DEBUG
                                    )
                                    return None
                                _log(
                                    scrape_run_id,
                                    f"Date looked old but extraction was low confidence for {url}. Keeping article.",
                                    logging.DEBUG
                                )
                            published_parsed = parsed_date.timetuple()
                    except Exception as e:
                        _log(scrape_run_id, f"Date parse failed for '{date_str}': {e}", logging.DEBUG)
                        pass

                # If date parsing failed or date was missing, default to NOW
                # This ensures we don't skip valid articles just because date extraction failed
                if not published_parsed:
                    _log(scrape_run_id, f"Date missing or unparseable for {url}. Defaulting to NOW.", logging.DEBUG)
                    published_parsed = datetime.now(timezone.utc).timetuple()

                article = {
                    "title": title or "Uden titel",
                    "link": url,
                    "published_parsed": published_parsed,
                    "platform": platform,
                    "content_teaser": content[:500] if content else ""
                }

                config_status = "config" if config else "generic"
                _log(scrape_run_id, f"Match ({platform}, {config_status}): {title}", logging.DEBUG)
                return article
            else:
                _log(scrape_run_id, f"Keyword match failed for {url}", logging.DEBUG)
                _log(scrape_run_id, f"  Title: {len(title)} chars, Content: {len(content)} chars", logging.DEBUG)
                # print(f"         Text snippet: {text_to_search[:100]}...") # Un-comment for deep debug

            return None

    except Exception as e:
        _log(scrape_run_id, f"Failed to scrape {url}: {e}", logging.WARNING)
        return None


async def scrape_configurable_sources(
    keywords: List[str],
    max_articles_per_source: int = 50,
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None
) -> List[Dict]:
    """
    Universal scraper that works with any source configured in database.

    OPTIMIZED: Uses parallel execution with asyncio.gather and Semaphore
    to avoid sequential bottlenecks. Can handle 10+ sources and 5+ keywords
    in 2-3 seconds instead of 50+ seconds.

    Logic:
    1. Fetch all configs with search_url_pattern from database
    2. For each config + keyword: Generate search URL, fetch HTML (PARALLEL)
    3. Extract article links using heuristic (same domain, path > 20 chars)
    4. Call _scrape_article_content() for each link (PARALLEL)

    Args:
        keywords: List of search keywords
        max_articles_per_source: Maximum articles to extract per source (default: 50)
        from_date: Optional datetime to filter articles from. Defaults to 24 hours ago.

    Returns:
        List of article dictionaries with title, link, date, platform, content
    """
    if not keywords:
        return []

    _log(scrape_run_id, "Starting universal discovery...")

    # Fetch all configs with search patterns
    crud = SupabaseCRUD()
    all_configs = await crud.get_all_source_configs()
    searchable_configs = [
        c for c in all_configs
        if c.get('search_url_pattern') and '{keyword}' in c['search_url_pattern']
    ]
    config_cache: Dict[str, Optional[Dict]] = {}
    for config in all_configs:
        domain = _normalize_domain(config.get("domain", ""))
        if domain:
            config_cache[domain] = config

    _log(scrape_run_id, f"Found {len(searchable_configs)} searchable configs")
    if not searchable_configs:
        _log(scrape_run_id, "No searchable configs found (missing search_url_pattern)", logging.WARNING)
        return []

    # Semaphore to limit concurrent requests (avoid rate limiting)
    sem = asyncio.Semaphore(20)  # Max 20 concurrent requests

    # Phase 1: Discovery - Find article URLs via search (PARALLEL)
    _log(scrape_run_id, "Running parallel discovery...")

    async def search_single_keyword(client: httpx.AsyncClient, config: Dict, keyword: str) -> tuple[str, set]:
        """Search a single keyword on a single source."""
        domain = _normalize_domain(config.get("domain", ""))
        if not domain:
            return "", set()

        search_pattern = config['search_url_pattern']
        found_urls = set()

        async with sem:  # Wait if more than 20 requests are in progress
            try:
                search_url = search_pattern.replace('{keyword}', quote_plus(keyword))
                headers = {"User-Agent": get_random_user_agent()}
                response = await fetch_with_retry(client, search_url, headers=headers)
                soup = BeautifulSoup(response.text, "lxml")

                # Heuristic: Find <a> tags, filter by domain + path length
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

    # Build all search tasks
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        tasks = []
        for config in searchable_configs:
            for keyword in keywords[:5]:  # Limit keywords to avoid rate limiting
                tasks.append(search_single_keyword(client, config, keyword))

        # Run all searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect discovered URLs
    discovered_urls = {}
    for result in results:
        if isinstance(result, tuple):
            domain, urls = result
            if not domain:
                continue
            if domain not in discovered_urls:
                discovered_urls[domain] = set()
            discovered_urls[domain].update(urls)

    # Print discovery summary
    for domain, urls in discovered_urls.items():
        _log(scrape_run_id, f"Discovered {len(urls)} URLs for {domain}", logging.DEBUG)

    # Phase 2: Extraction - Scrape each URL using unified method (PARALLEL)
    _log(scrape_run_id, "Starting extraction phase...")

    async def extract_single_article(url: str) -> Optional[Dict]:
        """Extract content from a single article URL."""
        async with sem:
            try:
                return await _scrape_article_content(
                    url,
                    keywords,
                    from_date=from_date,
                    config_cache=config_cache,
                    scrape_run_id=scrape_run_id
                )
            except Exception as e:
                _log(scrape_run_id, f"Extraction failed for {url}: {e}", logging.WARNING)
                return None

    # Build extraction tasks (limit per source)
    extraction_tasks = []
    skipped_non_article_urls = 0
    for domain, urls in discovered_urls.items():
        limited_urls = list(urls)[:max_articles_per_source]
        for url in limited_urls:
            if not _is_candidate_article_url(url, domain):
                skipped_non_article_urls += 1
                continue
            extraction_tasks.append(extract_single_article(url))

    if skipped_non_article_urls:
        _log(
            scrape_run_id,
            f"Skipped {skipped_non_article_urls} non-article URLs before extraction",
            logging.DEBUG
        )

    # Run all extractions in parallel
    _log(scrape_run_id, f"Extracting {len(extraction_tasks)} articles in parallel...")
    article_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

    # Filter out None and exceptions
    articles = [a for a in article_results if a and not isinstance(a, Exception)]

    _log(scrape_run_id, f"Found {len(articles)} matching articles")
    return articles
