import re
from urllib.parse import urlparse, urlunparse
from typing import List

def clean_keywords(keywords: List[str]) -> List[str]:
    """Clean keywords by removing punctuation noise around phrase inputs."""
    cleaned = []
    for kw in keywords:
        candidate = kw.replace(".", "").replace(",", "").strip()
        candidate = candidate.strip(_QUOTE_CHARS + " ")
        if candidate:
            cleaned.append(candidate)
    return cleaned

_QUOTE_CHARS = "\"'“”„‟«»`´"
_QUOTED_PHRASE_PATTERN = re.compile(r'["“”„‟«»]([^"“”„‟«»]+)["“”„‟«»]')


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


def _extract_keyword_terms(keyword: str) -> List[str]:
    """
    Split a keyword into searchable terms.
    Example: '"Novo Nordisk" Wegovy' -> ['Novo Nordisk', 'Wegovy']
    """
    normalized = _normalize_quotes(keyword).strip()
    if not normalized:
        return []

    terms: List[str] = []

    # Keep quoted phrases intact
    for phrase in _QUOTED_PHRASE_PATTERN.findall(normalized):
        phrase = " ".join(phrase.split()).strip(_QUOTE_CHARS + " ")
        if phrase:
            terms.append(phrase)

    # Add remaining unquoted segments as phrase terms
    remainder = _QUOTED_PHRASE_PATTERN.sub(" ", normalized)
    phrase = " ".join(remainder.split()).strip(_QUOTE_CHARS + " ")
    if phrase:
        terms.append(phrase)

    # Deduplicate while preserving order
    deduped: List[str] = []
    seen = set()
    for term in terms:
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)

    if deduped:
        return deduped

    fallback = normalized.strip(_QUOTE_CHARS + " ")
    return [fallback] if fallback else []


def _term_to_regex(term: str) -> str:
    """
    Build a regex fragment for a term/phrase with flexible whitespace and
    sane word boundaries when term starts/ends with word chars.
    """
    escaped = re.escape(term)
    # Use optional whitespace to match both "Space x" and "SpaceX".
    escaped = escaped.replace(r"\ ", r"\s*")

    prefix = r"(?<!\w)" if term and term[0].isalnum() else ""
    suffix = r"(?!\w)" if term and term[-1].isalnum() else ""
    return f"{prefix}{escaped}{suffix}"


def compile_keyword_patterns(keywords: List[str]) -> List[re.Pattern]:
    """
    Compile regex patterns where all keyword terms must be present.
    Handles quoted phrases robustly (e.g. '"Novo Nordisk" Wegovy').
    """
    patterns = []
    for keyword in keywords:
        terms = _extract_keyword_terms(keyword)
        if not terms:
            continue

        # Require each term/phrase to exist in the text, in any order.
        lookaheads = "".join(f"(?=.*{_term_to_regex(term)})" for term in terms)
        pattern = re.compile(lookaheads + r".*", re.IGNORECASE | re.DOTALL)
        patterns.append(pattern)
    return patterns

def keyword_matches_text(patterns: List[re.Pattern], text: str) -> bool:
    """Check if any keyword pattern matches the text"""
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False

def normalize_url(url: str) -> str:
    """Normalize URL by removing query parameters and fragments"""
    try:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
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
