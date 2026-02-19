from typing import Dict

from aiolimiter import AsyncLimiter

from app.core.config import settings


_LIMITER_REGISTRY: Dict[str, AsyncLimiter] = {}


def _profile_rps(profile: str) -> float:
    profile_key = (profile or "html").strip().lower()
    if profile_key == "api":
        return max(settings.scraping_rate_api_rps, 0.01)
    if profile_key == "rss":
        return max(settings.scraping_rate_rss_rps, 0.01)
    return max(settings.scraping_rate_html_rps, 0.01)


def get_domain_limiter(etld1: str, profile: str = "html") -> AsyncLimiter:
    """
    Return a per-(profile, eTLD+1) limiter.
    This enforces request rate over time and complements concurrency semaphores.
    """
    normalized_profile = (profile or "html").strip().lower()
    normalized_domain = (etld1 or "unknown").strip().lower() or "unknown"
    key = f"{normalized_profile}:{normalized_domain}"

    limiter = _LIMITER_REGISTRY.get(key)
    if limiter is not None:
        return limiter

    limiter = AsyncLimiter(max_rate=_profile_rps(normalized_profile), time_period=1.0)
    _LIMITER_REGISTRY[key] = limiter
    return limiter
