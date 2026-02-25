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


def _build_gnews_attempts(base_params: Dict[str, str]) -> List[Dict[str, str]]:
    """
    Build a short fallback sequence for GNews free-tier compatibility.
    Some accounts reject combined languages (lang=da,en) with HTTP 400.
    """
    attempts: List[Dict[str, str]] = []

    # 1) Preferred: combined language filter for broader coverage.
    combined = dict(base_params)
    combined["lang"] = "da,en"
    attempts.append(combined)

    # 2) Fallback: single language.
    danish = dict(base_params)
    danish["lang"] = "da"
    attempts.append(danish)

    # 3) Fallback: single language.
    english = dict(base_params)
    english["lang"] = "en"
    attempts.append(english)

    # 4) Last resort: no lang filter at all.
    no_lang = dict(base_params)
    attempts.append(no_lang)

    return attempts


async def scrape_gnews(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
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
    query = " OR ".join(cleaned)
    max_results = max(1, min(int(settings.gnews_max_results), 10))
    base_params: Dict[str, str] = {
        "q": query,
        "token": settings.gnews_api_key,
        "max": str(max_results),
        "sortby": "publishedAt",
        "from": _to_gnews_iso(since),
    }
    attempts = _build_gnews_attempts(base_params)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            from app.services.scraping.core.http_client import get_default_headers
            headers = get_default_headers()
            response: Optional[httpx.Response] = None
            last_400_body: Optional[str] = None

            for idx, params in enumerate(attempts, start=1):
                try:
                    lang_label = params.get("lang", "<none>")
                    _log(
                        scrape_run_id,
                        f"Request attempt {idx}/{len(attempts)} "
                        f"(lang={lang_label}, max={params.get('max')})",
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
                    if status == 400:
                        body_preview = ""
                        if exc.response is not None:
                            body_preview = (exc.response.text or "")[:300]
                        last_400_body = body_preview
                        _log(
                            scrape_run_id,
                            (
                                f"Attempt {idx} rejected with HTTP 400 "
                                f"(lang={params.get('lang', '<none>')}). "
                                f"Trying fallback..."
                            ),
                            logging.WARNING,
                        )
                        continue
                    raise

            if response is None:
                if last_400_body:
                    _log(
                        scrape_run_id,
                        f"All GNews attempts failed with HTTP 400. "
                        f"Response preview: {last_400_body}",
                        logging.ERROR,
                    )
                return []

            data = response.json()

            articles_data = data.get("articles", [])
            entries = []
            skipped_missing_date = 0
            skipped_unparseable_date = 0
            skipped_before_cutoff = 0
            _log(scrape_run_id, f"Applying API cutoff from={_to_gnews_iso(since)}")

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
