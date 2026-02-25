from typing import Dict, Optional
import asyncio
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
import dateparser
import trafilatura

from app.core.selectors import (
    GENERIC_CONTENT_SELECTORS,
    GENERIC_DATE_SELECTORS,
    GENERIC_TITLE_SELECTORS,
)
from app.services.scraping.core.date_utils import parse_mention_date
from .config import _log

for _trafilatura_logger in ("trafilatura", "trafilatura.core", "trafilatura.utils", "trafilatura.xml"):
    logging.getLogger(_trafilatura_logger).setLevel(logging.CRITICAL)

MIN_MEANINGFUL_CONTENT_CHARS = 80
MIN_TRAFILATURA_HTML_CHARS = 500
DATE_CERTAINTY_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b(19|20)\d{2}\b"
)
DATEPARSER_SETTINGS = {
    "TIMEZONE": "UTC",
    "TO_TIMEZONE": "UTC",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "DATE_ORDER": "DMY",
    "PREFER_DATES_FROM": "past",
}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _extract_date_value(date_elem) -> tuple[str, bool]:
    attribute_value = date_elem.get("datetime") or date_elem.get("content")
    if attribute_value:
        return attribute_value.strip(), True
    return date_elem.get_text(strip=True), False


def _extract_text_from_selector(soup: BeautifulSoup, selector: Optional[str]) -> str:
    if not selector:
        return ""
    elem = soup.select_one(selector)
    if not elem:
        return ""
    return _clean_text(elem.get_text(" ", strip=True))


def _extract_date_from_selector(soup: BeautifulSoup, selector: Optional[str]) -> tuple[str, bool]:
    if not selector:
        return "", False
    elem = soup.select_one(selector)
    if not elem:
        return "", False
    date_value, confident = _extract_date_value(elem)
    return _clean_text(date_value), confident


def _has_meaningful_content(content: str) -> bool:
    return len(_clean_text(content)) >= MIN_MEANINGFUL_CONTENT_CHARS


def _extract_with_selector_list(soup: BeautifulSoup, selectors: list[str], extractor):
    for selector in selectors:
        value = extractor(soup, selector)
        if isinstance(value, tuple):
            if value[0]:
                return value
        elif value:
            return value
    return ("", False) if extractor == _extract_date_from_selector else ""


def _extract_with_trafilatura_sync(html_content: str, scrape_run_id: Optional[str] = None) -> tuple[str, str, str]:
    title = ""
    content = ""
    date_str = ""

    if not html_content or len(html_content) < MIN_TRAFILATURA_HTML_CHARS:
        return title, content, date_str

    try:
        extracted = trafilatura.bare_extraction(html_content)
        if isinstance(extracted, dict):
            title = _clean_text(extracted.get("title", "") or extracted.get("sitename", ""))
            content = _clean_text(extracted.get("text", "") or extracted.get("raw_text", ""))
            date_str = _clean_text(extracted.get("date", "") or extracted.get("date_extracted", ""))

        if not content:
            content = _clean_text(trafilatura.extract(html_content) or "")
    except Exception as e:
        _log(scrape_run_id, f"Trafilatura extraction failed: {e}", logging.DEBUG)

    return title, content, date_str


async def _extract_with_trafilatura(html_content: str, scrape_run_id: Optional[str] = None) -> tuple[str, str, str]:
    return await asyncio.to_thread(_extract_with_trafilatura_sync, html_content, scrape_run_id)


async def _extract_content(
    soup: BeautifulSoup,
    html_content: str,
    config: Optional[Dict],
    scrape_run_id: Optional[str] = None,
) -> tuple[str, str, str, bool, str]:
    title = ""
    content = ""
    date_str = ""
    date_confident = False
    extracted_via = "none"

    if config:
        title = _extract_text_from_selector(soup, config.get("title_selector"))
        content = _extract_text_from_selector(soup, config.get("content_selector"))
        date_str, date_confident = _extract_date_from_selector(soup, config.get("date_selector"))

        if config.get("title_selector") and not title:
            _log(
                scrape_run_id,
                f"Configured title selector '{config['title_selector']}' failed or empty. Trying fallbacks.",
                logging.DEBUG,
            )
        if config.get("content_selector") and not content:
            _log(
                scrape_run_id,
                f"Configured content selector '{config['content_selector']}' failed or empty. Trying fallbacks.",
                logging.DEBUG,
            )
        if config.get("date_selector") and not date_str:
            _log(
                scrape_run_id,
                f"Configured date selector '{config['date_selector']}' found no date. Trying fallbacks.",
                logging.DEBUG,
            )

        if _has_meaningful_content(content):
            extracted_via = "config"

    if not _has_meaningful_content(content):
        if not title:
            title = _extract_with_selector_list(soup, GENERIC_TITLE_SELECTORS, _extract_text_from_selector)

        generic_content = _extract_with_selector_list(soup, GENERIC_CONTENT_SELECTORS, _extract_text_from_selector)
        if len(generic_content) > len(content):
            content = generic_content

        if not date_str:
            date_str, date_confident = _extract_with_selector_list(
                soup,
                GENERIC_DATE_SELECTORS,
                _extract_date_from_selector,
            )

        if _has_meaningful_content(content):
            extracted_via = "generic"

    if not _has_meaningful_content(content):
        tf_title, tf_content, tf_date = await _extract_with_trafilatura(html_content, scrape_run_id=scrape_run_id)

        if tf_title and not title:
            title = tf_title
        if len(tf_content) > len(content):
            content = tf_content
        if tf_date and not date_str:
            date_str = tf_date
            date_confident = bool(DATE_CERTAINTY_PATTERN.search(tf_date))

        if _has_meaningful_content(content):
            extracted_via = "trafilatura"

    return title, content, date_str, date_confident, extracted_via


def _parse_date_value(date_str: str, scrape_run_id: Optional[str] = None) -> Optional[datetime]:
    normalized = _clean_text(date_str)
    if not normalized:
        return None

    candidates = [normalized]
    lower_candidate = normalized.lower()
    if lower_candidate != normalized:
        candidates.append(lower_candidate)

    for candidate in candidates:
        # First pass: shared date parser used across providers.
        parsed = parse_mention_date(candidate)
        if parsed:
            return parsed

    # Fallback: keep locale-aware parsing behavior for configurable sources.
    for candidate in candidates:
        try:
            parsed = dateparser.parse(candidate, languages=["da", "en"], settings=DATEPARSER_SETTINGS)
            if parsed:
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
        except Exception as e:
            _log(scrape_run_id, f"Date parse failed for '{candidate}': {e}", logging.DEBUG)

    return None


def _is_confident_date_for_filtering(date_str: str, from_attribute: bool) -> bool:
    if from_attribute:
        return True
    return bool(DATE_CERTAINTY_PATTERN.search(date_str))


def _extract_content_adaptive_sync(
    page: object,
    config,
    scrape_run_id=None,
):
    """Sync-worker: kører CSS-selectors med adaptive=True, auto_save=True på Scrapling Selector."""

    def _get_text(selector: str) -> str:
        try:
            results = page.css(selector, adaptive=True, auto_save=True)
            if results:
                return _clean_text(results[0].get_all_text(separator=" ", strip=True))
        except Exception as e:
            _log(scrape_run_id, f"  adaptive css({selector!r}) fejl: {e}", logging.DEBUG)
        return ""

    def _get_date(selector: str) -> tuple:
        try:
            results = page.css(selector, adaptive=True, auto_save=True)
            if results:
                elem = results[0]
                dt = elem.attrib.get("datetime") or elem.attrib.get("content")
                if dt:
                    return _clean_text(str(dt)), True
                return _clean_text(elem.get_all_text(separator=" ", strip=True)), False
        except Exception as e:
            _log(scrape_run_id, f"  adaptive css_date({selector!r}) fejl: {e}", logging.DEBUG)
        return "", False

    title = content = date_str = ""
    date_confident = False

    # Niveau 1: domæne-specifikke config-selectors
    if config:
        if config.get("title_selector"):
            title = _get_text(config["title_selector"])
        if config.get("content_selector"):
            content = _get_text(config["content_selector"])
        if config.get("date_selector"):
            date_str, date_confident = _get_date(config["date_selector"])
        if _has_meaningful_content(content):
            return title, content, date_str, date_confident, "adaptive_config"

    # Niveau 2: generiske selectors (bygger også SQLite-træning selv ved fiasko)
    if not title:
        for sel in GENERIC_TITLE_SELECTORS:
            t = _get_text(sel)
            if t:
                title = t
                break

    for sel in GENERIC_CONTENT_SELECTORS:
        c = _get_text(sel)
        if len(c) > len(content):
            content = c
        if _has_meaningful_content(content):
            break

    if not date_str:
        for sel in GENERIC_DATE_SELECTORS:
            d, conf = _get_date(sel)
            if d:
                date_str, date_confident = d, conf
                break

    if _has_meaningful_content(content):
        return title, content, date_str, date_confident, "adaptive_generic"

    return None  # caller falder igennem til BeautifulSoup


async def _extract_content_adaptive(page: object, config, scrape_run_id=None):
    """Async wrapper til _extract_content_adaptive_sync."""
    try:
        return await asyncio.to_thread(_extract_content_adaptive_sync, page, config, scrape_run_id)
    except Exception as e:
        _log(scrape_run_id, f"Adaptive extraction threw: {type(e).__name__}: {e}", logging.DEBUG)
        return None
