from typing import Dict, Iterator, Optional
from urllib.parse import urlparse
import logging

from app.crud.supabase_crud import SupabaseCRUD
from app.core.config import settings

logger = logging.getLogger("scraping")

DEFAULT_MAX_ARTICLES_PER_SOURCE = 10
DISCOVERY_CONCURRENCY = 50
EXTRACTION_CONCURRENCY = 20
PER_DOMAIN_EXTRACTION_CONCURRENCY = 3
DOMAIN_CIRCUIT_BREAKER_THRESHOLD = 5
PLAYWRIGHT_CONCURRENCY_LIMIT = 3
MAX_TOTAL_URLS_PER_RUN = max(1, settings.scraping_max_total_urls_per_run)
BLIND_DOMAIN_CIRCUIT_BREAKER_THRESHOLD = max(1, settings.scraping_blind_domain_circuit_threshold)


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[Configurable] %s", prefix, message)


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


async def _get_config_for_domain(
    domain: str,
    config_cache: Optional[Dict[str, Optional[Dict]]] = None,
    scrape_run_id: Optional[str] = None,
) -> Optional[Dict]:
    """Get saved source configuration for a specific domain."""
    try:
        candidates = list(_domain_candidates(domain))
        if not candidates:
            return None

        if config_cache is not None:
            for candidate in candidates:
                if candidate in config_cache:
                    config = config_cache[candidate]
                    if config:
                        config_cache[candidates[0]] = config
                        return config

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
