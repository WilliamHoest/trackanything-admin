import re
from urllib.parse import urlparse, urlunparse
from typing import List

def clean_keywords(keywords: List[str]) -> List[str]:
    """Clean keywords by removing dots and commas"""
    return [kw.replace(".", "").replace(",", "").strip() for kw in keywords if kw.strip()]

def compile_keyword_patterns(keywords: List[str]) -> List[re.Pattern]:
    """
    Compile regex patterns for word boundary matching.
    This prevents partial matches (e.g., "Gap" won't match "Singapore").
    """
    patterns = []
    for keyword in keywords:
        # Escape special regex characters and add word boundaries
        escaped = re.escape(keyword)
        pattern = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)
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
    """Determine platform from URL domain"""
    try:
        domain = urlparse(url).netloc.lower()
        if "politiken" in domain:
            return "Politiken"
        elif "dr.dk" in domain:
            return "DR"
        else:
            return "Unknown"
    except Exception:
        return "Unknown"
