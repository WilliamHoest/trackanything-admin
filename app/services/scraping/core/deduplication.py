from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from app.services.scraping.core.domain_utils import get_etld_plus_one


_TITLE_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


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
    return " ".join(tokens[:6])


def _comparison_text(mention: Dict) -> str:
    title = (mention.get("title") or "").strip()
    teaser = (mention.get("content_teaser") or "").strip()

    if len(title) >= 20:
        return title
    if title and teaser:
        return f"{title} {teaser}"
    return title or teaser


def near_deduplicate_mentions(
    mentions: List[Dict],
    threshold: int = 92,
    day_window: int = 2,
) -> Tuple[List[Dict], int]:
    """
    Remove near-duplicates using blocking + fuzzy matching.

    Blocking (cheap pre-filter):
    - Same eTLD+1
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
    # key: (domain, signature) -> indices into unique_mentions
    buckets: Dict[Tuple[str, str], List[int]] = {}
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
        bucket_key = (domain, signature)
        mention_dt = _mention_published_at(mention)

        is_duplicate = False
        candidate_indices = buckets.get(bucket_key, [])
        for idx in candidate_indices:
            candidate = unique_mentions[idx]
            candidate_text = _normalize_title(_comparison_text(candidate))
            if not candidate_text:
                continue

            candidate_dt = _mention_published_at(candidate)
            if mention_dt and candidate_dt and abs(mention_dt - candidate_dt) > day_delta:
                continue

            score = fuzz.token_set_ratio(normalized_text, candidate_text)
            if score >= safe_threshold:
                is_duplicate = True
                break

        if is_duplicate:
            removed += 1
            continue

        unique_mentions.append(mention)
        buckets.setdefault(bucket_key, []).append(len(unique_mentions) - 1)

    return unique_mentions, removed
