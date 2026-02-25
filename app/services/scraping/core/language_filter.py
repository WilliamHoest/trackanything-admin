import logging
from typing import Dict, List, Optional, Tuple

from langdetect import LangDetectException, detect

logger = logging.getLogger("scraping")


def filter_by_language(
    mentions: List[Dict],
    allowed_languages: Optional[List[str]],
    scrape_run_id: Optional[str] = None,
) -> Tuple[List[Dict], int]:
    """
    Filter mentions by detected language of title.

    Keeps mentions when:
    - allowed_languages is None or empty (no filter)
    - Title is too short to detect reliably (< 15 chars)
    - Language detection fails (LangDetectException)
    - Detected language is in allowed_languages
    """
    if not allowed_languages:
        return mentions, 0

    kept, removed = [], 0
    for mention in mentions:
        title = (mention.get("title") or "").strip()
        if len(title) < 15:
            kept.append(mention)  # too short to detect reliably — keep
            continue
        try:
            lang = detect(title)
            if lang in allowed_languages:
                kept.append(mention)
            else:
                removed += 1
                logger.debug(
                    "[run:%s] Language filter removed '%s' (detected=%s, allowed=%s)",
                    scrape_run_id,
                    title[:80],
                    lang,
                    allowed_languages,
                )
        except LangDetectException:
            kept.append(mention)  # keep on detection failure
    return kept, removed
