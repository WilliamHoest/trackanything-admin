import re
from urllib.parse import urlparse, urlunparse
from typing import List

_QUOTE_CHARS = "\"'“”„‟«»`´"


def _normalize_quotes(text: str) -> str:
    return (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("„", '"')
        .replace("‟", '"')
        .replace("«", '"')
        .replace("»", '"')
        .replace("`", "'")
        .replace("´", "'")
    )


def sanitize_search_input(text: str) -> str:
    """
    Sanitize user/topic keyword text for provider queries.

    Removes quote characters anywhere in the string to avoid malformed
    provider query syntax like: Iran" Krig.
    """
    if not text:
        return ""

    candidate = _normalize_quotes(text)
    candidate = re.sub(r'["\']', " ", candidate)
    candidate = candidate.replace(".", " ").replace(",", " ")
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate


def clean_keywords(keywords: List[str]) -> List[str]:
    """Clean keywords by sanitizing quotes/punctuation and collapsing whitespace."""
    cleaned = []
    for kw in keywords:
        candidate = sanitize_search_input(kw)
        if candidate:
            cleaned.append(candidate)
    return cleaned


def _keyword_to_regex(keyword: str) -> re.Pattern | None:
    """
    Build one phrase regex per keyword (no single-word splitting logic).
    """
    cleaned = sanitize_search_input(keyword)
    if not cleaned:
        return None

    tokens = [re.escape(token) for token in cleaned.split() if token]
    if not tokens:
        return None

    # Allow punctuation/whitespace between phrase tokens so both
    # "danskefonde.dk" and "danskefonde dk" can match.
    phrase = r"[\s\W_]+".join(tokens)
    pattern = rf"(?<!\w){phrase}(?!\w)"
    return re.compile(pattern, re.IGNORECASE)


def compile_keyword_patterns(keywords: List[str]) -> List[List[re.Pattern]]:
    """
    Compile keyword groups as phrase regex lists.
    Each input keyword becomes one phrase-group.
    """
    groups: List[List[re.Pattern]] = []
    for keyword in keywords:
        phrase_pattern = _keyword_to_regex(keyword)
        if phrase_pattern is None:
            continue
        groups.append([phrase_pattern])
    return groups


def keyword_match_score(patterns: List[List[re.Pattern]], text: str) -> int:
    """
    Return max number of matched terms within any keyword-group.
    """
    if not text:
        return 0

    best_score = 0
    for group in patterns:
        score = sum(1 for term_pattern in group if term_pattern.search(text))
        if score > best_score:
            best_score = score
    return best_score


def keyword_matches_text(
    patterns: List[List[re.Pattern]],
    text: str,
    min_terms: int = 1,
) -> bool:
    return keyword_match_score(patterns, text) >= max(1, int(min_terms))

def normalize_url(url: str) -> str:
    """Normalize URL by removing query/fragment and canonicalizing host/path."""
    try:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "https").lower()
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        path = parsed.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        if path != "/":
            path = path.rstrip("/")

        return urlunparse((scheme, host, path, '', '', ''))
    except Exception:
        return url

def get_platform_from_url(url: str) -> str:
    """Extract platform name from URL domain"""
    try:
        domain = urlparse(url).netloc.lower()
        # Remove www. prefix for cleaner domain names
        domain = domain.replace('www.', '')
        return domain if domain else "Unknown"
    except Exception:
        return "Unknown"
