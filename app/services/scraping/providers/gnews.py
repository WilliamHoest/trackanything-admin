import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.scraping.core.date_utils import parse_mention_date
from app.services.scraping.core.http_client import TIMEOUT_SECONDS, fetch_with_retry
from app.services.scraping.core.text_processing import clean_keywords

logger = logging.getLogger("scraping")
GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"
GNEWS_QUERY_MAX_CHARS = 190


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[GNews] %s", prefix, message)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_gnews_iso(dt: datetime) -> str:
    # GNews expects RFC3339/ISO8601, e.g. 2026-02-17T12:30:00Z
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dedupe_keywords(keywords: List[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = keyword.strip()
        if not normalized:
            continue
        token = normalized.lower()
        if token in seen:
            continue
        seen.add(token)
        deduped.append(normalized)
    return deduped


def _build_keyword_query(keyword: str) -> str:
    return f"\"{keyword}\"" if " " in keyword else keyword


def _build_gnews_attempts(
    base_params: Dict[str, str],
    allowed_languages: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Build language fallback sequence for GNews compatibility.

    When allowed_languages is provided, the first attempt uses those languages
    directly. The original da/en fallback chain is only used when no explicit
    filter is set, to avoid spurious fallbacks.
    """
    attempts: List[Dict[str, str]] = []

    first = dict(base_params)
    first["lang"] = ",".join(allowed_languages) if allowed_languages else "da,en"
    attempts.append(first)

    if not allowed_languages:
        danish = dict(base_params)
        danish["lang"] = "da"
        attempts.append(danish)

        english = dict(base_params)
        english["lang"] = "en"
        attempts.append(english)

    # Always: no-lang fallback (ensures we never silently drop a keyword)
    no_lang = dict(base_params)
    attempts.append(no_lang)

    return attempts


async def _fetch_gnews_with_attempts(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    attempts: List[Dict[str, str]],
    scrape_run_id: Optional[str],
    keyword_idx: int,
    total_keywords: int,
) -> Optional[httpx.Response]:
    response: Optional[httpx.Response] = None
    last_error_status: Optional[int] = None
    last_error_body: Optional[str] = None

    for idx, params in enumerate(attempts, start=1):
        try:
            _log(
                scrape_run_id,
                (
                    f"Attempt {idx}/{len(attempts)} for keyword {keyword_idx}/{total_keywords} "
                    f"(lang={params.get('lang', '<none>')}, max={params.get('max')})"
                ),
                logging.DEBUG,
            )
            response = await fetch_with_retry(
                client,
                GNEWS_SEARCH_URL,
                rate_profile="api",
                metrics_provider="gnews",
                headers=headers,
                params=params,
            )
            break
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (400, 429):
                last_error_status = status
                last_error_body = (exc.response.text or "")[:300] if exc.response is not None else ""
                _log(
                    scrape_run_id,
                    (
                        f"Attempt {idx} for keyword {keyword_idx}/{total_keywords} failed "
                        f"with HTTP {status} (lang={params.get('lang', '<none>')}). Trying fallback..."
                    ),
                    logging.WARNING,
                )
                continue
            raise

    if response is None:
        _log(
            scrape_run_id,
            (
                f"All attempts failed for keyword {keyword_idx}/{total_keywords} "
                f"(last_status={last_error_status}, preview={last_error_body or '<none>'})"
            ),
            logging.ERROR,
        )

    return response


async def scrape_gnews(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Fetch articles from GNews API.

    Args:
        keywords: List of keywords to search for.
        from_date: Optional datetime cutoff; defaults to 24 hours ago.
    """
    if not keywords or not settings.gnews_api_key:
        if not settings.gnews_api_key:
            _log(scrape_run_id, "GNEWS_API_KEY is not set.", logging.WARNING)
        return []

    since = _normalize_utc(from_date) or (datetime.now(timezone.utc) - timedelta(hours=24))
    cleaned = clean_keywords(keywords)
    keyword_queries = _dedupe_keywords(cleaned)
    if not keyword_queries:
        _log(scrape_run_id, "No valid keywords after cleaning.", logging.WARNING)
        return []

    oversized_keywords = [kw for kw in keyword_queries if len(kw) > GNEWS_QUERY_MAX_CHARS]
    if oversized_keywords:
        _log(
            scrape_run_id,
            (
                "Some keywords exceed safe GNews query length and may fail: "
                f"{oversized_keywords}"
            ),
            logging.WARNING,
        )

    _log(
        scrape_run_id,
        (
            f"Prepared {len(keyword_queries)} per-keyword query unit(s) "
            f"from {len(cleaned)} keyword(s)"
        ),
    )

    max_results = max(1, min(int(settings.gnews_max_results), 10))

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            from app.services.scraping.core.http_client import get_default_headers
            headers = get_default_headers()
            entries = []
            skipped_missing_date = 0
            skipped_unparseable_date = 0
            skipped_before_cutoff = 0
            _log(scrape_run_id, f"Applying API cutoff from={_to_gnews_iso(since)}")

            for keyword_idx, keyword in enumerate(keyword_queries, start=1):
                if keyword_idx > 1 and settings.scraping_gnews_inter_request_delay_s > 0:
                    await asyncio.sleep(settings.scraping_gnews_inter_request_delay_s)

                query = _build_keyword_query(keyword)
                if len(query) > GNEWS_QUERY_MAX_CHARS:
                    _log(
                        scrape_run_id,
                        (
                            f"Skipping query for keyword {keyword_idx}/{len(keyword_queries)} "
                            f"(chars={len(query)} > {GNEWS_QUERY_MAX_CHARS})"
                        ),
                        logging.WARNING,
                    )
                    continue

                _log(
                    scrape_run_id,
                    (
                        f"Keyword {keyword_idx}/{len(keyword_queries)} "
                        f"single query (chars={len(query)}): {query[:220]}"
                    ),
                    logging.DEBUG,
                )

                params: Dict[str, str] = {
                    "q": query,
                    "token": settings.gnews_api_key,
                    "max": str(max_results),
                    "sortby": "publishedAt",
                    "from": _to_gnews_iso(since),
                }
                response = await _fetch_gnews_with_attempts(
                    client=client,
                    headers=headers,
                    attempts=_build_gnews_attempts(params, allowed_languages=allowed_languages),
                    scrape_run_id=scrape_run_id,
                    keyword_idx=keyword_idx,
                    total_keywords=len(keyword_queries),
                )
                if response is None:
                    continue

                data = response.json()
                articles_data = data.get("articles", [])

                for article in articles_data:
                    if "url" not in article:
                        continue

                    try:
                        published_at = article.get("publishedAt")
                        if not published_at:
                            skipped_missing_date += 1
                            continue
                        parsed = parse_mention_date(published_at)
                        if parsed is None:
                            skipped_unparseable_date += 1
                            continue

                        if parsed < since:
                            skipped_before_cutoff += 1
                            continue

                        entries.append({
                            "title": article.get("title", "Uden titel"),
                            "link": article["url"],
                            "published_parsed": parsed.timetuple(),
                            "platform": "GNews",
                            "content_teaser": article.get("description", ""),
                        })
                        _log(scrape_run_id, f"Match: {article.get('title', 'Uden titel')}", logging.DEBUG)

                    except Exception as e:
                        _log(scrape_run_id, f"Article parse error: {e}", logging.WARNING)
                        continue

            _log(
                scrape_run_id,
                (
                    f"Returning {len(entries)} valid mentions "
                    f"(skipped_before_cutoff={skipped_before_cutoff}, "
                    f"skipped_missing_date={skipped_missing_date}, "
                    f"skipped_unparseable_date={skipped_unparseable_date})"
                ),
            )
            return entries

    except Exception as e:
        _log(scrape_run_id, f"Request failed: {e}", logging.ERROR)
        return []
