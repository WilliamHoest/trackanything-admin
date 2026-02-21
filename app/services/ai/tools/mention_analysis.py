"""
Mention Analysis Tools

Provides detailed analysis helpers and on-the-fly analyst prompts.
"""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.schemas.mention import MentionContext

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.crud.supabase_crud import SupabaseCRUD
else:
    SupabaseCRUD = Any


class BrandComparisonRequest(BaseModel):
    """Validated input for comparing two brands."""

    brand_a: str = Field(min_length=1)
    brand_b: str = Field(min_length=1)
    days_back: int = Field(default=7, ge=1, le=30)

    @field_validator("brand_a", "brand_b")
    @classmethod
    def _strip_brand_name(cls, value: str) -> str:
        return value.strip()


class SentimentTrendRequest(BaseModel):
    """Validated input for single-brand sentiment trend analysis."""

    brand_name: str = Field(min_length=1)
    days_back: int = Field(default=14, ge=1, le=90)

    @field_validator("brand_name")
    @classmethod
    def _strip_brand_name(cls, value: str) -> str:
        return value.strip()


class AdaptiveFetchResult(BaseModel):
    """Metadata and payload from adaptive mention retrieval."""

    mentions: List[Dict[str, Any]]
    requested_days_back: int
    effective_days_back: int
    requested_limit: int
    effective_limit: int


def _resolve_brand_id(brands: List[Dict[str, Any]], brand_name: str) -> Optional[int]:
    for brand in brands:
        if brand.get("name", "").strip().lower() == brand_name.strip().lower():
            return brand.get("id")
    return None


def _format_mention_row(mention: Dict[str, Any]) -> str:
    topic_name = mention.get("topic", {}).get("name", "N/A") if isinstance(mention.get("topic"), dict) else "N/A"
    platform_name = (
        mention.get("platform", {}).get("name", "N/A")
        if isinstance(mention.get("platform"), dict)
        else "N/A"
    )
    published_at = mention.get("published_at") or mention.get("created_at")
    if isinstance(published_at, datetime):
        published_text = published_at.isoformat()
    else:
        published_text = str(published_at) if published_at else "N/A"

    caption = (mention.get("caption") or "").strip()
    teaser = (mention.get("content_teaser") or "").strip()
    if teaser and teaser.lower() != caption.lower():
        text = f"{caption} {teaser}".strip()
    else:
        text = caption
    text = (text or "No text available").replace("\n", " ")

    return (
        f"- Mention #{mention.get('id', 'N/A')} | {published_text} | "
        f"Topic: {topic_name} | Platform: {platform_name}\n"
        f"  Text: {text[:420]}"
    )


def _format_mentions_block(brand_name: str, mentions: List[Dict[str, Any]]) -> str:
    if not mentions:
        return f"{brand_name}: No mentions found in the selected period."

    rows = "\n".join(_format_mention_row(mention) for mention in mentions)
    return f"{brand_name} ({len(mentions)} mentions):\n{rows}"


async def _fetch_mentions_adaptive(
    crud: "SupabaseCRUD",
    brand_id: int,
    days_back: int,
    base_limit: int = 50,
    min_desired_mentions: int = 20,
) -> AdaptiveFetchResult:
    """Fetch mentions with adaptive expansion when context is sparse."""
    safe_days = max(1, int(days_back))
    safe_limit = max(10, int(base_limit))

    attempt_plan: List[tuple[int, int]] = [
        (safe_days, safe_limit),
        (safe_days, min(120, safe_limit * 2)),
        (min(180, safe_days * 2), min(200, safe_limit * 3)),
    ]

    best_mentions: List[Dict[str, Any]] = []
    effective_days = safe_days
    effective_limit = safe_limit

    for days_attempt, limit_attempt in attempt_plan:
        mentions = await crud.get_recent_mentions_for_brand_analysis(
            brand_id=brand_id,
            days_back=days_attempt,
            limit=limit_attempt,
        )

        if len(mentions) > len(best_mentions):
            best_mentions = mentions
            effective_days = days_attempt
            effective_limit = limit_attempt

        if len(mentions) >= min_desired_mentions:
            break

    return AdaptiveFetchResult(
        mentions=best_mentions,
        requested_days_back=safe_days,
        effective_days_back=effective_days,
        requested_limit=safe_limit,
        effective_limit=effective_limit,
    )


async def analyze_mentions(mentions: List[MentionContext]) -> str:
    """Analyze all recent mentions for patterns, sentiment, and trends."""
    if not mentions:
        return "No recent mentions to analyze"

    logger.info("Analyzing %s mentions", len(mentions))

    analysis = f"DETAILED MENTION ANALYSIS ({len(mentions)} mentions):\n\n"

    by_brand: Dict[str, List[MentionContext]] = {}
    for mention in mentions:
        brand_name = mention.brand.name if mention.brand else "Unknown"
        by_brand.setdefault(brand_name, []).append(mention)

    for brand, brand_mentions in by_brand.items():
        unread = sum(1 for mention in brand_mentions if not mention.read_status)
        analysis += f"Brand: {brand} ({len(brand_mentions)} mentions, {unread} unread)\n"

        by_topic: Dict[str, int] = {}
        by_platform: Dict[str, int] = {}

        for mention in brand_mentions:
            topic = mention.topic.name if mention.topic else "N/A"
            platform = mention.platform.name if mention.platform else "N/A"
            by_topic[topic] = by_topic.get(topic, 0) + 1
            by_platform[platform] = by_platform.get(platform, 0) + 1

        topic_summary = ", ".join(
            [f"{k} ({v})" for k, v in sorted(by_topic.items(), key=lambda x: x[1], reverse=True)]
        )
        platform_summary = ", ".join(
            [f"{k} ({v})" for k, v in sorted(by_platform.items(), key=lambda x: x[1], reverse=True)]
        )
        analysis += f"  Topics: {topic_summary}\n"
        analysis += f"  Platforms: {platform_summary}\n"

        analysis += "  Sample mentions:\n"
        for i, mention in enumerate(brand_mentions[:3], 1):
            topic = mention.topic.name if mention.topic else "N/A"
            platform = mention.platform.name if mention.platform else "N/A"
            date = mention.published_at.isoformat() if mention.published_at else "N/A"
            caption = (mention.caption or "")[:100]
            status = "read" if mention.read_status else "unread"
            analysis += f"    {i}. ({status}) [{topic}] {platform} ({date}): {caption}...\n"

        analysis += "\n"

    return analysis


async def compare_brands(
    crud: "SupabaseCRUD",
    brands: List[Dict[str, Any]],
    brand_a: str,
    brand_b: str,
    days_back: int = 7,
) -> str:
    """Fetch mentions for two brands and return a comparison prompt for the LLM."""
    try:
        params = BrandComparisonRequest(brand_a=brand_a, brand_b=brand_b, days_back=days_back)
    except ValidationError as e:
        return f"Invalid compare_brands input: {e}"

    brand_a_id = _resolve_brand_id(brands, params.brand_a)
    brand_b_id = _resolve_brand_id(brands, params.brand_b)
    available_brands = ", ".join(sorted(brand.get("name", "Unknown") for brand in brands))

    if not brand_a_id:
        return f"Brand '{params.brand_a}' not found. Available brands: {available_brands}"
    if not brand_b_id:
        return f"Brand '{params.brand_b}' not found. Available brands: {available_brands}"

    try:
        brand_a_data, brand_b_data = await asyncio.gather(
            _fetch_mentions_adaptive(
                crud=crud,
                brand_id=brand_a_id,
                days_back=params.days_back,
                base_limit=50,
            ),
            _fetch_mentions_adaptive(
                crud=crud,
                brand_id=brand_b_id,
                days_back=params.days_back,
                base_limit=50,
            ),
        )
    except Exception as e:
        logger.error("compare_brands database fetch failed: %s", e, exc_info=True)
        return f"Database error while fetching brand mentions: {e}"

    brand_a_mentions = brand_a_data.mentions
    brand_b_mentions = brand_b_data.mentions

    if not brand_a_mentions and not brand_b_mentions:
        return (
            f"No mentions found for '{params.brand_a}' and '{params.brand_b}' "
            f"in the last {params.days_back} days."
        )

    return (
        "ATLAS ANALYST TASK: Compare these brands based only on the mention text below.\n\n"
        "Required output:\n"
        "1. Volume comparison and relative share of attention.\n"
        "2. Sentiment comparison (positive/neutral/negative) inferred on-the-fly.\n"
        "3. Main themes driving sentiment for each brand.\n"
        "4. One concrete next action per brand.\n\n"
        f"Requested window: last {params.days_back} days.\n"
        f"Effective data window: {params.brand_a}={brand_a_data.effective_days_back}d/{brand_a_data.effective_limit} rows, "
        f"{params.brand_b}={brand_b_data.effective_days_back}d/{brand_b_data.effective_limit} rows.\n\n"
        f"{_format_mentions_block(params.brand_a, brand_a_mentions)}\n\n"
        f"{_format_mentions_block(params.brand_b, brand_b_mentions)}\n\n"
        "Important: Do not invent data. If confidence is low, say so explicitly."
    )


async def analyze_sentiment_trend(
    crud: "SupabaseCRUD",
    brands: List[Dict[str, Any]],
    brand_name: str,
    days_back: int = 14,
) -> str:
    """Fetch mentions for one brand and return a sentiment trend prompt for the LLM."""
    try:
        params = SentimentTrendRequest(brand_name=brand_name, days_back=days_back)
    except ValidationError as e:
        return f"Invalid analyze_sentiment_trend input: {e}"

    brand_id = _resolve_brand_id(brands, params.brand_name)
    available_brands = ", ".join(sorted(brand.get("name", "Unknown") for brand in brands))
    if not brand_id:
        return f"Brand '{params.brand_name}' not found. Available brands: {available_brands}"

    try:
        mention_data = await _fetch_mentions_adaptive(
            crud=crud,
            brand_id=brand_id,
            days_back=params.days_back,
            base_limit=50,
        )
    except Exception as e:
        logger.error("analyze_sentiment_trend database fetch failed: %s", e, exc_info=True)
        return f"Database error while fetching mentions: {e}"

    mentions = mention_data.mentions

    if not mentions:
        return f"No mentions found for '{params.brand_name}' in the last {params.days_back} days."

    return (
        "ATLAS ANALYST TASK: Analyze sentiment trend over time from the mention text.\n\n"
        "Required output:\n"
        "1. Trend direction (improving, declining, stable, or volatile).\n"
        "2. Estimated sentiment mix with evidence from the text.\n"
        "3. Key topics/events explaining changes.\n"
        "4. Early warning signals to track next.\n"
        "5. Two concrete next actions.\n\n"
        f"Brand: {params.brand_name}\n"
        f"Requested window: last {params.days_back} days.\n"
        f"Effective data window: {mention_data.effective_days_back} days, {mention_data.effective_limit} row limit.\n\n"
        f"{_format_mentions_block(params.brand_name, mentions)}\n\n"
        "Important: If evidence is weak, mark confidence as low."
    )
