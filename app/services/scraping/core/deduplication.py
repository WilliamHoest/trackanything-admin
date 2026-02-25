from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover
    fuzz = None

from app.services.scraping.core.domain_utils import get_etld_plus_one


_TITLE_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_GOOGLE_NEWS_ETLD1 = "news.google.com"


def _fuzzy_score(left: str, right: str) -> float:
    if fuzz is None:
        return 100.0 if left == right else 0.0
    return float(fuzz.token_set_ratio(left, right))


def _to_utc_datetime(value: object) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    if isinstance(value, tuple) and len(value) >= 6:
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except Exception:
            return None

    return None


def _mention_published_at(mention: Dict) -> Optional[datetime]:
    published = _to_utc_datetime(mention.get("published_at"))
    if published is not None:
        return published
    return _to_utc_datetime(mention.get("published_parsed"))


def _normalize_title(title: str) -> str:
    words = _TITLE_WORD_PATTERN.findall((title or "").lower())
    return " ".join(words)


def _title_signature(normalized_title: str) -> str:
    if not normalized_title:
        return ""
    tokens = normalized_title.split()
    # Fast blocking key to reduce comparisons.
    return " ".join(tokens[:5])


def _comparison_text(mention: Dict) -> str:
    title = (mention.get("title") or "").strip()
    teaser = (mention.get("content_teaser") or "").strip()

    if len(title) >= 20:
        return title
    if title and teaser:
        return f"{title} {teaser}"
    return title or teaser


def _should_cross_domain_compare(left_domain: str, right_domain: str) -> bool:
    return left_domain == _GOOGLE_NEWS_ETLD1 or right_domain == _GOOGLE_NEWS_ETLD1


def near_deduplicate_mentions(
    mentions: List[Dict],
    threshold: int = 92,
    day_window: int = 2,
) -> Tuple[List[Dict], int]:
    """
    Remove near-duplicates using blocking + fuzzy matching.

    Blocking (cheap pre-filter):
    - Same eTLD+1
    - Cross-domain compare when one side is news.google.com
    - Same title signature (first tokens)
    - Published date within +/- day_window days when both dates are available

    Fuzzy comparison:
    - rapidfuzz.fuzz.token_set_ratio on normalized comparison texts
    """
    if len(mentions) <= 1:
        return mentions, 0

    safe_threshold = max(1, min(int(threshold), 100))
    safe_day_window = max(0, int(day_window))
    day_delta = timedelta(days=safe_day_window)

    unique_mentions: List[Dict] = []
    unique_domains: List[str] = []
    # Fast exact-domain blocking.
    buckets_by_domain_signature: Dict[Tuple[str, str], List[int]] = {}
    # Cross-domain fallback blocking for Google News wrapper links.
    buckets_by_signature: Dict[str, List[int]] = {}
    removed = 0

    for mention in mentions:
        raw_text = _comparison_text(mention)
        normalized_text = _normalize_title(raw_text)
        if not normalized_text:
            unique_mentions.append(mention)
            continue

        domain = get_etld_plus_one(
            mention.get("link")
            or mention.get("platform")
            or ""
        )
        signature = _title_signature(normalized_text)
        mention_dt = _mention_published_at(mention)

        is_duplicate = False
        candidate_indices: Set[int] = set(
            buckets_by_domain_signature.get((domain, signature), [])
        )
        for idx in buckets_by_signature.get(signature, []):
            if _should_cross_domain_compare(domain, unique_domains[idx]):
                candidate_indices.add(idx)

        for idx in candidate_indices:
            candidate = unique_mentions[idx]
            candidate_text = _normalize_title(_comparison_text(candidate))
            if not candidate_text:
                continue

            candidate_dt = _mention_published_at(candidate)
            if mention_dt and candidate_dt and abs(mention_dt - candidate_dt) > day_delta:
                continue

            score = _fuzzy_score(normalized_text, candidate_text)
            if score >= safe_threshold:
                is_duplicate = True
                break

        if is_duplicate:
            removed += 1
            continue

        unique_mentions.append(mention)
        unique_domains.append(domain)
        mention_idx = len(unique_mentions) - 1
        buckets_by_domain_signature.setdefault((domain, signature), []).append(mention_idx)
        buckets_by_signature.setdefault(signature, []).append(mention_idx)

    return unique_mentions, removed


def filter_mentions_against_historical(
    new_mentions: List[Dict],
    historical_mentions: List[Dict],
    threshold: int = 92,
    day_window: int = 2,
) -> Tuple[List[Dict], int]:
    """
    Filter new mentions against recent historical mentions for the same brand.
    Returns (filtered_mentions, removed_count).

    Uses same blocking model as near_deduplicate_mentions:
    - eTLD+1
    - cross-domain compare when one side is news.google.com
    - title signature
    - optional published date window when both dates exist
    """
    if not new_mentions or not historical_mentions:
        return new_mentions, 0

    safe_threshold = max(1, min(int(threshold), 100))
    safe_day_window = max(0, int(day_window))
    day_delta = timedelta(days=safe_day_window)

    historical_entries: List[Tuple[str, Optional[datetime], str]] = []
    historical_domain_buckets: Dict[Tuple[str, str], List[int]] = {}
    historical_signature_buckets: Dict[str, List[int]] = {}
    for mention in historical_mentions:
        text = _normalize_title(_comparison_text(mention))
        if not text:
            continue
        domain = get_etld_plus_one(
            mention.get("link")
            or mention.get("platform")
            or ""
        )
        signature = _title_signature(text)
        historical_entries.append((text, _mention_published_at(mention), domain))
        mention_idx = len(historical_entries) - 1
        historical_domain_buckets.setdefault((domain, signature), []).append(mention_idx)
        historical_signature_buckets.setdefault(signature, []).append(mention_idx)

    if not historical_entries:
        return new_mentions, 0

    filtered: List[Dict] = []
    removed = 0

    for mention in new_mentions:
        text = _normalize_title(_comparison_text(mention))
        if not text:
            filtered.append(mention)
            continue

        domain = get_etld_plus_one(
            mention.get("link")
            or mention.get("platform")
            or ""
        )
        signature = _title_signature(text)
        mention_dt = _mention_published_at(mention)
        candidate_indices: Set[int] = set(
            historical_domain_buckets.get((domain, signature), [])
        )
        for idx in historical_signature_buckets.get(signature, []):
            if _should_cross_domain_compare(domain, historical_entries[idx][2]):
                candidate_indices.add(idx)

        is_duplicate = False
        for idx in candidate_indices:
            candidate_text, candidate_dt, _candidate_domain = historical_entries[idx]
            if mention_dt and candidate_dt and abs(mention_dt - candidate_dt) > day_delta:
                continue
            score = _fuzzy_score(text, candidate_text)
            if score >= safe_threshold:
                is_duplicate = True
                break

        if is_duplicate:
            removed += 1
            continue

        filtered.append(mention)

    return filtered, removed
