import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from bs4 import BeautifulSoup
import feedparser
import httpx

from app.services.scraping.core.date_utils import parse_mention_date
from app.services.scraping.core.domain_utils import get_etld_plus_one
from app.services.scraping.core.http_client import TIMEOUT_SECONDS, fetch_with_retry, get_default_headers
from app.services.scraping.core.metrics import observe_http_error
from app.services.scraping.core.text_processing import (
    compile_keyword_patterns,
    keyword_match_score,
    normalize_url,
)

logger = logging.getLogger("scraping")
GOOGLE_NEWS_RSS_SEARCH_URL = "https://news.google.com/rss/search"
RSS_ACCEPT_HEADER = "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"
GOOGLE_DOMAIN_MARKER = "google."
RSS_DEFAULT_LOCALE_CHAIN = ("da", "en")
RSS_MAX_LOCALE_ATTEMPTS = 5
RSS_LANGUAGE_LOCALES = {
    "da": {"hl": "da", "gl": "DK", "ceid": "DK:da"},
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "no": {"hl": "no", "gl": "NO", "ceid": "NO:no"},
    "nb": {"hl": "no", "gl": "NO", "ceid": "NO:no"},
    "nn": {"hl": "no", "gl": "NO", "ceid": "NO:no"},
    "sv": {"hl": "sv", "gl": "SE", "ceid": "SE:sv"},
}


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[RSS] %s", prefix, message)


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_http_url(candidate: str) -> bool:
    parsed = urlparse(candidate or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _host(candidate: str) -> str:
    return (urlparse(candidate).netloc or "").strip().lower()


def _is_google_host(candidate_host: str) -> bool:
    host = (candidate_host or "").strip().lower()
    return bool(host) and GOOGLE_DOMAIN_MARKER in host


def _extract_query_targets(candidate: str) -> List[str]:
    targets: List[str] = []
    parsed = urlparse(candidate or "")
    if not parsed.query:
        return targets

    params = parse_qs(parsed.query, keep_blank_values=False)
    for key in ("url", "u", "q", "target", "redirect"):
        for value in params.get(key, []):
            raw = (value or "").strip()
            if _is_http_url(raw):
                targets.append(raw)
    return targets


def _entry_candidates(entry: Dict) -> List[str]:
    candidates: List[str] = []
    for key in ("link", "id", "guid"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    links_value = entry.get("links")
    if isinstance(links_value, list):
        for item in links_value:
            if not isinstance(item, dict):
                continue
            href = (item.get("href") or "").strip()
            if href:
                candidates.append(href)

    for html_key in ("summary",):
        html = entry.get(html_key)
        if not isinstance(html, str) or not html.strip():
            continue
        try:
            soup = BeautifulSoup(html, "lxml")
            for anchor in soup.select("a[href]"):
                href = (anchor.get("href") or "").strip()
                if href:
                    candidates.append(href)
        except Exception:
            continue

    content_value = entry.get("content")
    if isinstance(content_value, list):
        for block in content_value:
            if not isinstance(block, dict):
                continue
            html = block.get("value")
            if not isinstance(html, str) or not html.strip():
                continue
            try:
                soup = BeautifulSoup(html, "lxml")
                for anchor in soup.select("a[href]"):
                    href = (anchor.get("href") or "").strip()
                    if href:
                        candidates.append(href)
            except Exception:
                continue

    deduped: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


async def _resolve_google_wrapper_link(
    client: httpx.AsyncClient,
    wrapper_url: str,
    scrape_run_id: Optional[str] = None,
) -> Optional[str]:
    headers = get_default_headers()
    headers["Accept"] = RSS_ACCEPT_HEADER
    try:
        response = await fetch_with_retry(
            client,
            wrapper_url,
            rate_profile="rss",
            metrics_provider="rss",
            headers=headers,
            follow_redirects=True,
        )
        final_url = str(response.url)
        if _is_http_url(final_url) and not _is_google_host(_host(final_url)):
            return normalize_url(final_url)

        for extracted in _extract_query_targets(final_url):
            if not _is_google_host(_host(extracted)):
                return normalize_url(extracted)
    except Exception as exc:
        observe_http_error(
            provider="rss",
            domain=get_etld_plus_one(wrapper_url),
            error_type=f"canonical_resolve_{type(exc).__name__}",
        )
        _log(
            scrape_run_id,
            f"Canonical resolve failed for wrapper link ({type(exc).__name__}: {exc})",
            logging.DEBUG,
        )
    return None


async def _extract_canonical_link(
    entry: Dict,
    client: httpx.AsyncClient,
    canonical_cache: Dict[str, str],
    scrape_run_id: Optional[str] = None,
) -> str:
    candidates = _entry_candidates(entry)
    if not candidates:
        return ""

    for candidate in candidates:
        for extracted in _extract_query_targets(candidate):
            if _is_http_url(extracted) and not _is_google_host(_host(extracted)):
                return normalize_url(extracted)

        if _is_http_url(candidate) and not _is_google_host(_host(candidate)):
            return normalize_url(candidate)

    wrapper = next((url for url in candidates if _is_http_url(url)), "")
    if not wrapper:
        return ""

    if wrapper in canonical_cache:
        return canonical_cache[wrapper]

    resolved = await _resolve_google_wrapper_link(client, wrapper, scrape_run_id=scrape_run_id)
    canonical = resolved or normalize_url(wrapper)
    canonical_cache[wrapper] = canonical
    return canonical


def _normalized_languages(allowed_languages: Optional[List[str]]) -> List[str]:
    if not allowed_languages:
        return []
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in allowed_languages:
        if not raw:
            continue
        lang = raw.strip().lower().replace("_", "-").split("-", 1)[0]
        if not lang or lang in seen:
            continue
        seen.add(lang)
        normalized.append(lang)
    return normalized


def _locale_attempts(allowed_languages: Optional[List[str]]) -> List[tuple[str, Dict[str, str]]]:
    attempts: List[tuple[str, Dict[str, str]]] = []
    allowed = _normalized_languages(allowed_languages)

    if allowed:
        for lang in allowed:
            locale = RSS_LANGUAGE_LOCALES.get(lang)
            if locale:
                attempts.append((lang, locale))
    else:
        for lang in RSS_DEFAULT_LOCALE_CHAIN:
            locale = RSS_LANGUAGE_LOCALES.get(lang)
            if locale:
                attempts.append((lang, locale))

    attempts.append(("default", {}))

    deduped: List[tuple[str, Dict[str, str]]] = []
    seen_locale_signature: set[tuple[tuple[str, str], ...]] = set()
    for lang, locale in attempts:
        signature = tuple(sorted(locale.items()))
        if signature in seen_locale_signature:
            continue
        seen_locale_signature.add(signature)
        deduped.append((lang, locale))
        if len(deduped) >= RSS_MAX_LOCALE_ATTEMPTS:
            break

    # Keep at least one no-locale fallback when truncation happens.
    if deduped and deduped[-1][1] != {}:
        fallback = ("default", {})
        if fallback not in deduped:
            deduped = deduped[: max(0, RSS_MAX_LOCALE_ATTEMPTS - 1)] + [fallback]

    return deduped


def _build_rss_url(keyword: str, locale: Dict[str, str]) -> str:
    params = {"q": keyword}
    params.update(locale)
    return f"{GOOGLE_NEWS_RSS_SEARCH_URL}?{urlencode(params)}"


async def scrape_rss(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Scrape Google News RSS search feeds for a keyword set.

    Args:
        keywords: Keywords to search for.
        from_date: Optional UTC cutoff datetime; defaults to now minus 24 hours.
    """
    if not keywords:
        _log(scrape_run_id, "No keywords provided for RSS scraping", logging.WARNING)
        return []

    mentions = []
    total_entries_seen = 0
    total_kept = 0
    total_before_cutoff = 0
    total_missing_date = 0
    total_unparseable_date = 0
    total_parse_errors = 0
    total_phrase_miss = 0
    total_duplicate_links = 0

    # Use provided from_date or default to 24 hours ago
    explicit_cutoff = _normalize_utc(from_date)
    since = explicit_cutoff or (datetime.now(timezone.utc) - timedelta(hours=24))
    locale_attempts = _locale_attempts(allowed_languages)
    canonical_cache: Dict[str, str] = {}

    _log(
        scrape_run_id,
        (
            f"Scraping {len(keywords)} keyword(s) via Google News RSS "
            f"across {len(locale_attempts)} locale attempt(s)"
        ),
    )
    _log(
        scrape_run_id,
        f"Applying strict cutoff since={since.isoformat()} (explicit_from_date={explicit_cutoff is not None})",
    )

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        for keyword in keywords:
            try:
                keyword_patterns = compile_keyword_patterns([keyword])
                if not keyword_patterns:
                    _log(scrape_run_id, f"Keyword '{keyword}': no valid phrase pattern after cleaning", logging.WARNING)
                    continue

                keyword_entries_seen = 0
                keyword_kept = 0
                keyword_before_cutoff = 0
                keyword_missing_date = 0
                keyword_unparseable_date = 0
                keyword_parse_errors = 0
                keyword_phrase_miss = 0
                keyword_duplicate_links = 0
                keyword_seen_links: set[str] = set()

                for locale_label, locale in locale_attempts:
                    rss_url = _build_rss_url(keyword, locale)
                    headers = get_default_headers()
                    headers["Accept"] = RSS_ACCEPT_HEADER

                    try:
                        response = await fetch_with_retry(
                            client,
                            rss_url,
                            rate_profile="rss",
                            metrics_provider="rss",
                            headers=headers,
                        )
                    except Exception as request_error:
                        _log(
                            scrape_run_id,
                            (
                                f"Keyword '{keyword}' locale={locale_label}: "
                                f"fetch failed ({type(request_error).__name__}: {request_error})"
                            ),
                            logging.WARNING,
                        )
                        continue

                    try:
                        # feedparser is blocking and parse() accepts bytes payload.
                        feed = await asyncio.to_thread(feedparser.parse, response.content)
                    except Exception as parse_error:
                        keyword_parse_errors += 1
                        observe_http_error(
                            provider="rss",
                            domain=get_etld_plus_one(rss_url),
                            error_type=f"feed_parse_{type(parse_error).__name__}",
                        )
                        _log(
                            scrape_run_id,
                            (
                                f"Keyword '{keyword}' locale={locale_label}: "
                                f"feed parse failed ({type(parse_error).__name__}: {parse_error})"
                            ),
                            logging.WARNING,
                        )
                        continue

                    if getattr(feed, "bozo", 0):
                        bozo_exception = getattr(feed, "bozo_exception", None)
                        observe_http_error(
                            provider="rss",
                            domain=get_etld_plus_one(rss_url),
                            error_type="feed_bozo",
                        )
                        _log(
                            scrape_run_id,
                            (
                                f"Keyword '{keyword}' locale={locale_label}: "
                                f"feed parser bozo=1 ({bozo_exception})"
                            ),
                            logging.WARNING,
                        )

                    entries = list(getattr(feed, "entries", []) or [])
                    keyword_entries_seen += len(entries)
                    _log(
                        scrape_run_id,
                        (
                            f"Keyword '{keyword}' locale={locale_label}: "
                            f"status={response.status_code}, entries={len(entries)}"
                        ),
                        logging.DEBUG,
                    )

                    for entry in entries:
                        try:
                            raw_date = (
                                entry.get("published_parsed")
                                or entry.get("updated_parsed")
                                or entry.get("published")
                            )
                            if not raw_date:
                                keyword_missing_date += 1
                                continue
                            published_dt = parse_mention_date(raw_date)
                            if published_dt is None:
                                keyword_unparseable_date += 1
                                continue

                            if published_dt < since:
                                keyword_before_cutoff += 1
                                continue

                            title = entry.get("title", "Ingen titel")
                            summary = entry.get("summary", "")
                            text_to_match = f"{title}\n{summary}"
                            if keyword_match_score(keyword_patterns, text_to_match) < 1:
                                keyword_phrase_miss += 1
                                continue

                            canonical_link = await _extract_canonical_link(
                                entry,
                                client=client,
                                canonical_cache=canonical_cache,
                                scrape_run_id=scrape_run_id,
                            )
                            if not canonical_link:
                                keyword_parse_errors += 1
                                continue
                            if canonical_link in keyword_seen_links:
                                keyword_duplicate_links += 1
                                continue
                            keyword_seen_links.add(canonical_link)

                            mentions.append({
                                "title": title,
                                "link": canonical_link,
                                "content_teaser": summary[:200],
                                "platform": "Google RSS",
                                "published_parsed": published_dt.timetuple(),
                            })
                            keyword_kept += 1
                            _log(scrape_run_id, f"Match: {title[:60]}", logging.DEBUG)

                        except Exception as entry_error:
                            keyword_parse_errors += 1
                            _log(scrape_run_id, f"Entry parse error: {entry_error}", logging.WARNING)
                            continue

                total_entries_seen += keyword_entries_seen
                total_kept += keyword_kept
                total_before_cutoff += keyword_before_cutoff
                total_missing_date += keyword_missing_date
                total_unparseable_date += keyword_unparseable_date
                total_parse_errors += keyword_parse_errors
                total_phrase_miss += keyword_phrase_miss
                total_duplicate_links += keyword_duplicate_links
                _log(
                    scrape_run_id,
                    (
                        f"Keyword '{keyword}' summary: entries={keyword_entries_seen}, "
                        f"kept={keyword_kept}, before_cutoff={keyword_before_cutoff}, "
                        f"missing_date={keyword_missing_date}, unparseable_date={keyword_unparseable_date}, "
                        f"parse_errors={keyword_parse_errors}, phrase_miss={keyword_phrase_miss}, "
                        f"duplicate_links={keyword_duplicate_links}"
                    ),
                )

            except Exception as e:
                observe_http_error(
                    provider="rss",
                    domain=get_etld_plus_one(GOOGLE_NEWS_RSS_SEARCH_URL),
                    error_type=type(e).__name__,
                )
                _log(scrape_run_id, f"Error for '{keyword}': {e}", logging.WARNING)
                continue

    _log(
        scrape_run_id,
        (
            f"Found {len(mentions)} articles. Totals: entries={total_entries_seen}, "
            f"kept={total_kept}, before_cutoff={total_before_cutoff}, "
            f"missing_date={total_missing_date}, unparseable_date={total_unparseable_date}, "
            f"parse_errors={total_parse_errors}, phrase_miss={total_phrase_miss}, "
            f"duplicate_links={total_duplicate_links}"
        ),
    )
    return mentions
