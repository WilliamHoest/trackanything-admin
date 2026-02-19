from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urlparse
import asyncio
import logging

import httpx

from app.crud.supabase_crud import SupabaseCRUD
from app.services.scraping.core.http_client import TIMEOUT_SECONDS
from app.services.scraping.core.metrics import observe_extraction
from .config import (
    DEFAULT_MAX_ARTICLES_PER_SOURCE,
    DISCOVERY_CONCURRENCY,
    DOMAIN_CIRCUIT_BREAKER_THRESHOLD,
    EXTRACTION_CONCURRENCY,
    PER_DOMAIN_EXTRACTION_CONCURRENCY,
    _log,
    _normalize_domain,
)
from .discovery import _is_candidate_article_url, search_single_keyword
from .fetcher import _scrape_article_content


async def scrape_configurable_sources(
    keywords: List[str],
    max_articles_per_source: int = DEFAULT_MAX_ARTICLES_PER_SOURCE,
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
) -> List[Dict]:
    """Universal scraper that works with all configured sources."""
    if not keywords:
        return []

    _log(scrape_run_id, "Starting universal discovery...")

    crud = SupabaseCRUD()
    all_configs = await crud.get_all_source_configs()
    searchable_configs = [
        c
        for c in all_configs
        if c.get("search_url_pattern") and "{keyword}" in c["search_url_pattern"]
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

    discovery_sem = asyncio.Semaphore(DISCOVERY_CONCURRENCY)
    extraction_sem = asyncio.Semaphore(EXTRACTION_CONCURRENCY)

    _log(scrape_run_id, "Running parallel discovery...")

    discovered_urls: Dict[str, set[str]] = {}
    blind_domain_counts: Dict[str, int] = {}
    domain_failure_counts: Dict[str, int] = {}
    open_circuit_domains: set[str] = set()
    domain_semaphores: Dict[str, asyncio.Semaphore] = {}
    domain_failure_lock = asyncio.Lock()

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, limits=limits) as client:
        discovery_tasks = []
        for config in searchable_configs:
            for keyword in keywords:
                discovery_tasks.append(
                    search_single_keyword(
                        client,
                        config,
                        keyword,
                        discovery_sem=discovery_sem,
                        scrape_run_id=scrape_run_id,
                    )
                )

        discovery_results = await asyncio.gather(*discovery_tasks, return_exceptions=True)

        for result in discovery_results:
            if isinstance(result, tuple):
                domain, urls = result
                if not domain:
                    continue
                if domain not in discovered_urls:
                    discovered_urls[domain] = set()
                discovered_urls[domain].update(urls)

        for domain, urls in discovered_urls.items():
            _log(scrape_run_id, f"Discovered {len(urls)} URLs for {domain}", logging.DEBUG)

        _log(scrape_run_id, "Starting extraction phase...")

        async def extract_single_article(url: str) -> Optional[Dict]:
            domain = _normalize_domain(urlparse(url).netloc) or "unknown"

            if domain in open_circuit_domains:
                _log(scrape_run_id, f"Skipping {url} (circuit open for {domain})", logging.DEBUG)
                observe_extraction("configurable", domain, "circuit_open_skip", 0)
                return None

            domain_sem = domain_semaphores.setdefault(
                domain,
                asyncio.Semaphore(PER_DOMAIN_EXTRACTION_CONCURRENCY),
            )

            async with extraction_sem:
                async with domain_sem:
                    if domain in open_circuit_domains:
                        _log(scrape_run_id, f"Skipping {url} (circuit opened for {domain})", logging.DEBUG)
                        observe_extraction("configurable", domain, "circuit_open_skip", 0)
                        return None

                    try:
                        return await _scrape_article_content(
                            client,
                            url,
                            keywords,
                            from_date=from_date,
                            config_cache=config_cache,
                            blind_domain_counts=blind_domain_counts,
                            scrape_run_id=scrape_run_id,
                        )
                    except Exception as e:
                        async with domain_failure_lock:
                            failures = domain_failure_counts.get(domain, 0) + 1
                            domain_failure_counts[domain] = failures
                            if failures == DOMAIN_CIRCUIT_BREAKER_THRESHOLD:
                                open_circuit_domains.add(domain)
                                _log(
                                    scrape_run_id,
                                    f"Circuit opened for {domain} after {failures} extraction exceptions",
                                    logging.WARNING,
                                )

                        _log(
                            scrape_run_id,
                            f"Extraction failed for {url}: {type(e).__name__}: {repr(e)}",
                            logging.WARNING,
                        )
                        observe_extraction("configurable", domain, f"exception_{type(e).__name__}", 0)
                        return None

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
                logging.DEBUG,
            )

        _log(scrape_run_id, f"Extracting {len(extraction_tasks)} articles in parallel...")
        extraction_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

    articles = [a for a in extraction_results if a and not isinstance(a, Exception)]

    if domain_failure_counts:
        noisy_domains = sorted(domain_failure_counts.items(), key=lambda item: item[1], reverse=True)
        top_noisy = ", ".join(f"{domain} ({count})" for domain, count in noisy_domains[:10])
        _log(scrape_run_id, f"Domain extraction exception counts: {top_noisy}", logging.INFO)

    if open_circuit_domains:
        joined = ", ".join(sorted(open_circuit_domains))
        _log(scrape_run_id, f"Circuit breaker opened for domains: {joined}", logging.WARNING)

    if blind_domain_counts:
        suspected_js_domains = sorted(
            ((domain, count) for domain, count in blind_domain_counts.items() if count >= 3),
            key=lambda item: item[1],
            reverse=True,
        )
        if suspected_js_domains:
            joined = ", ".join(f"{domain} ({count})" for domain, count in suspected_js_domains[:10])
            _log(
                scrape_run_id,
                f"Potential JS/paywall domains (repeated 0-char extractions): {joined}",
                logging.WARNING,
            )

    _log(scrape_run_id, f"Found {len(articles)} matching articles")
    return articles
