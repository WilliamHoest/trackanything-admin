import asyncio
import logging
from time import perf_counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.scraping.core.date_utils import parse_mention_date
from serpapi import GoogleSearch

from app.core.config import settings
from app.services.scraping.core.domain_utils import get_etld_plus_one
from app.services.scraping.core.metrics import observe_http_error, observe_http_request
from app.services.scraping.core.rate_limit import get_domain_limiter
from app.services.scraping.core.text_processing import chunk_or_queries, clean_keywords

logger = logging.getLogger("scraping")
SERPAPI_BASE_URL = "https://serpapi.com"
SERPAPI_ENGINE = "google_news"
SERPAPI_FALLBACK_ENGINE = "google"
SERPAPI_QUERY_MAX_CHARS = 220
SERPAPI_DEFAULT_HL = "da"
SERPAPI_DEFAULT_GL = "dk"
SERPAPI_DEFAULT_GOOGLE_DOMAIN = "google.dk"
SERPAPI_AFTER_PADDING_CHARS = len("() after:YYYY-MM-DD")


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[SerpAPI] %s", prefix, message)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_tbs_from_date(from_date: Optional[datetime]) -> Optional[str]:
    """
    Map an absolute datetime cutoff to Google News tbs buckets.
    """
    cutoff = _normalize_utc(from_date)
    if cutoff is None:
        return None

    now = datetime.now(timezone.utc)
    if cutoff > now:
        return "qdr:d"

    age_days = (now - cutoff).total_seconds() / (24 * 3600)
    # Use slightly wider bucket boundaries to avoid bucket flapping due to
    # second-level timing differences between cutoff computation and request.
    if age_days <= 2:
        return "qdr:d"
    # Keep 14-day windows on weekly filter to reduce stale result spillover.
    # Add a small tolerance for second-level drift.
    if age_days <= 15:
        return "qdr:w"
    if age_days <= 60:
        return "qdr:m"
    if age_days <= 400:
        return "qdr:y"
    return None


def _apply_after_operator(query: str, from_date: Optional[datetime]) -> str:
    """
    Add a hard lower date bound to the query string for Google-style engines.
    """
    cutoff = _normalize_utc(from_date)
    if cutoff is None:
        return query
    return f"({query}) after:{cutoff.date().isoformat()}"


def _effective_query_max_chars(from_date: Optional[datetime]) -> int:
    cutoff = _normalize_utc(from_date)
    if cutoff is None:
        return SERPAPI_QUERY_MAX_CHARS
    return max(1, SERPAPI_QUERY_MAX_CHARS - SERPAPI_AFTER_PADDING_CHARS)


def _detect_limit_signal(error_message: str) -> Optional[str]:
    message = (error_message or "").lower()
    if not message:
        return None

    if "rate limit" in message or "too many requests" in message:
        return "rate_limit"
    if "quota" in message or "searches left" in message:
        return "quota"
    if "monthly" in message and "search" in message:
        return "quota"
    if "insufficient" in message and "balance" in message:
        return "quota"
    if "limit reached" in message:
        return "limit_reached"
    return None


def _is_no_results_error(error_message: str) -> bool:
    message = (error_message or "").lower()
    return "no results" in message or "hasn't returned any results" in message


def _build_attempt_params(base_params: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Try Google News first, then fallback to Google News vertical (tbm=nws).
    """
    attempts: List[Tuple[str, Dict[str, Any]]] = []

    primary = dict(base_params)
    primary["engine"] = SERPAPI_ENGINE
    attempts.append((SERPAPI_ENGINE, primary))

    fallback = dict(base_params)
    fallback["engine"] = SERPAPI_FALLBACK_ENGINE
    fallback["tbm"] = "nws"
    attempts.append((f"{SERPAPI_FALLBACK_ENGINE}+tbm=nws", fallback))

    return attempts


def _extract_results(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize result shapes across serpapi engines.
    """
    news_results = payload.get("news_results")
    if isinstance(news_results, list):
        return [item for item in news_results if isinstance(item, dict)]

    organic_results = payload.get("organic_results")
    if not isinstance(organic_results, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in organic_results:
        if not isinstance(item, dict):
            continue
        source = item.get("source", "")
        source_obj = source if isinstance(source, dict) else {"title": str(source) if source else "Google"}
        normalized.append({
            "title": item.get("title", "No title"),
            "link": item.get("link") or item.get("url") or "",
            "snippet": item.get("snippet", ""),
            "iso_date": item.get("date"),
            "source": source_obj,
        })
    return normalized


async def scrape_serpapi(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
) -> List[Dict]:
    """
    Fetch articles from SerpAPI (Google News).

    Args:
        keywords: List of keywords to search for.
        from_date: Optional datetime cutoff.
    """
    if not keywords:
        return []

    cleaned = clean_keywords(keywords)
    query_chunks = chunk_or_queries(cleaned, _effective_query_max_chars(from_date))
    if not query_chunks:
        _log(scrape_run_id, "No valid query chunks after keyword cleaning.", logging.WARNING)
        return []

    oversized_keywords = [kw for kw in cleaned if len(kw) > _effective_query_max_chars(from_date)]
    if oversized_keywords:
        _log(
            scrape_run_id,
            (
                "Some keywords exceed safe SerpAPI query length and may fail: "
                f"{oversized_keywords}"
            ),
            logging.WARNING,
        )

    from_date_utc = _normalize_utc(from_date)

    try:
        if not settings.serpapi_key:
            _log(scrape_run_id, "SerpAPI key not found, skipping.", logging.WARNING)
            return []

        _log(
            scrape_run_id,
            (
                f"Scraping {len(keywords)} keywords across "
                f"{len(query_chunks)} chunk(s)"
            ),
        )

        tbs = _build_tbs_from_date(from_date_utc)
        if tbs and from_date_utc is not None:
            _log(scrape_run_id, f"Applying Google News time filter tbs={tbs} for cutoff {from_date_utc.isoformat()}")

        etld1 = get_etld_plus_one(SERPAPI_BASE_URL)
        limiter = get_domain_limiter(etld1, profile="api")

        mentions = []
        skipped_before_cutoff = 0
        skipped_missing_date = 0
        skipped_unparseable_date = 0
        failed_chunks = 0
        empty_chunks = 0

        for chunk_idx, query in enumerate(query_chunks, start=1):
            provider_query = _apply_after_operator(query, from_date_utc)
            _log(
                scrape_run_id,
                (
                    f"Query chunk {chunk_idx}/{len(query_chunks)} "
                    f"(chars={len(provider_query)}): {provider_query[:220]}"
                ),
                logging.DEBUG,
            )

            base_params: Dict[str, Any] = {
                "q": provider_query,
                "api_key": settings.serpapi_key,
                "num": 20,
                "hl": SERPAPI_DEFAULT_HL,
                "gl": SERPAPI_DEFAULT_GL,
                "google_domain": SERPAPI_DEFAULT_GOOGLE_DOMAIN,
            }
            if tbs:
                base_params["tbs"] = tbs

            attempts = _build_attempt_params(base_params)
            chunk_results: List[Dict[str, Any]] = []
            chunk_hard_failure = False

            for attempt_idx, (engine_label, params) in enumerate(attempts, start=1):
                _log(
                    scrape_run_id,
                    (
                        f"Chunk {chunk_idx}/{len(query_chunks)} attempt {attempt_idx}/{len(attempts)} "
                        f"using engine={engine_label}"
                    ),
                    logging.DEBUG,
                )

                def run_search(current_params: Dict[str, Any]):
                    search = GoogleSearch(current_params)
                    return search.get_dict()

                request_started_at = perf_counter()
                async with limiter:
                    results = await asyncio.to_thread(run_search, params)
                status_code = "200" if "error" not in results else "api_error"
                request_duration = perf_counter() - request_started_at
                observe_http_request(
                    provider="serpapi",
                    domain=etld1,
                    status_code=status_code,
                    duration_seconds=request_duration,
                )

                metadata = results.get("search_metadata", {})
                meta_status = metadata.get("status", "unknown")
                candidate_results = _extract_results(results)
                _log(
                    scrape_run_id,
                    (
                        f"Chunk {chunk_idx}/{len(query_chunks)} engine={engine_label} response: "
                        f"status={meta_status}, http_metric={status_code}, "
                        f"duration={request_duration:.2f}s, results={len(candidate_results)}"
                    ),
                )

                if "error" in results:
                    error_message = str(results.get("error", "Unknown SerpAPI error"))
                    limit_signal = _detect_limit_signal(error_message)
                    if _is_no_results_error(error_message):
                        observe_http_error(
                            provider="serpapi",
                            domain=etld1,
                            error_type="api_no_results",
                        )
                        _log(
                            scrape_run_id,
                            (
                                f"Chunk {chunk_idx}/{len(query_chunks)} engine={engine_label} "
                                f"returned no results error ({error_message}); trying fallback."
                            ),
                            logging.WARNING,
                        )
                        continue

                    observe_http_error(
                        provider="serpapi",
                        domain=etld1,
                        error_type=f"api_{limit_signal or 'error'}",
                    )
                    if limit_signal:
                        _log(
                            scrape_run_id,
                            f"Possible SerpAPI {limit_signal} detected: {error_message}",
                            logging.WARNING,
                        )
                    else:
                        _log(scrape_run_id, f"SerpAPI error: {error_message}", logging.ERROR)

                    # Hard provider failures (quota/rate-limit/unknown) should stop
                    # attempts for this chunk to avoid wasting requests.
                    chunk_hard_failure = True
                    break

                if candidate_results:
                    chunk_results = candidate_results
                    break

            if chunk_hard_failure:
                failed_chunks += 1
                continue
            if not chunk_results:
                empty_chunks += 1
                _log(
                    scrape_run_id,
                    f"Chunk {chunk_idx}/{len(query_chunks)} produced no results after all attempts.",
                    logging.DEBUG,
                )
                continue

            for item in chunk_results:
                # Prefer absolute timestamps when available for strict interval accuracy.
                raw_date = item.get("iso_date") or item.get("published_at") or item.get("date")
                parsed_dt: Optional[datetime] = parse_mention_date(raw_date)

                # Strict mode when cutoff is active:
                # require a parseable date and enforce exact cutoff.
                if from_date_utc is not None:
                    if not raw_date:
                        skipped_missing_date += 1
                        continue
                    if parsed_dt is None:
                        skipped_unparseable_date += 1
                        continue
                    if parsed_dt < from_date_utc:
                        skipped_before_cutoff += 1
                        if skipped_before_cutoff <= 5:
                            _log(
                                scrape_run_id,
                                (
                                    f"Skipping before cutoff: title='{item.get('title', '')[:120]}', "
                                    f"raw_date='{raw_date}', parsed='{parsed_dt.isoformat()}', "
                                    f"cutoff='{from_date_utc.isoformat()}'"
                                ),
                                logging.DEBUG,
                            )
                        continue

                if parsed_dt is None:
                    parsed_dt = datetime.now(timezone.utc)

                source_value = item.get("source")
                if isinstance(source_value, dict):
                    platform = (
                        source_value.get("title")
                        or source_value.get("name")
                        or "Google News"
                    )
                elif isinstance(source_value, str):
                    platform = source_value or "Google News"
                else:
                    platform = "Google News"

                mention = {
                    "title": item.get("title", "No title"),
                    "link": item.get("link", ""),
                    "content_teaser": item.get("snippet", ""),
                    "published_parsed": parsed_dt.timetuple(),
                    "platform": platform,
                }
                mentions.append(mention)

        _log(
            scrape_run_id,
            (
                f"Returning {len(mentions)} valid mentions "
                f"(skipped_before_cutoff={skipped_before_cutoff}, "
                f"skipped_missing_date={skipped_missing_date}, "
                f"skipped_unparseable_date={skipped_unparseable_date}, "
                f"failed_chunks={failed_chunks}, "
                f"empty_chunks={empty_chunks})"
            ),
        )
        return mentions

    except Exception as e:
        observe_http_error(
            provider="serpapi",
            domain=get_etld_plus_one(SERPAPI_BASE_URL),
            error_type=type(e).__name__,
        )
        _log(scrape_run_id, f"Scraping failed: {type(e).__name__}: {e}", logging.ERROR)
        return []
