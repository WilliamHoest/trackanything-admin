"""
Reporting Tool for AI Agent

Allows the agent to fetch mentions within a date range to generate reports.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional, Sequence
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from .content_fetch import fetch_page_content

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.crud.supabase_crud import SupabaseCRUD
else:
    SupabaseCRUD = Any


class DraftResponseRequest(BaseModel):
    """Validated input for drafting a response from a mention."""

    mention_id: int = Field(gt=0)
    format: Literal["linkedin", "email", "press_release"]
    tone: Literal["professional", "urgent", "casual"]
    include_full_context: bool = False


class MentionContextRequest(BaseModel):
    """Validated input for mention context retrieval."""

    mention_id: int = Field(gt=0)
    include_full_page: bool = False


def _render_draft_style_instructions(format_name: str, tone: str) -> str:
    if format_name == "linkedin":
        return (
            f"Write as a {tone} LinkedIn post.\n"
            "- Start with a clear hook sentence.\n"
            "- Use short paragraphs.\n"
            "- End with one CTA and max 3 hashtags."
        )
    if format_name == "email":
        return (
            f"Write as a {tone} email.\n"
            "- Include Subject line.\n"
            "- Include greeting, core message, and explicit next step.\n"
            "- Keep it concise and clear."
        )
    return (
        f"Write as a {tone} press release draft.\n"
        "- Include headline and short lead paragraph.\n"
        "- Include a quote placeholder from spokesperson.\n"
        "- Include a factual boilerplate ending."
    )


async def fetch_mentions_for_report(
    crud: "SupabaseCRUD",
    user_id: str,
    brand_name: str,
    days_back: int,
    brands: list[Dict[str, Any]],
) -> str:
    """Fetch mentions for a specific brand within a date range for report generation.

    This tool allows the agent to retrieve all mentions for a brand within a
    specified time period. Use this when generating weekly reports, crisis reports,
    or custom analysis that requires specific date ranges.

    Args:
        crud: SupabaseCRUD instance from context
        user_id: The user's ID
        brand_name: Name of the brand to fetch mentions for
        days_back: Number of days back from today to fetch mentions
        brands: List of user's brands from context

    Returns:
        Formatted string with mention data ready for report generation
    """
    try:
        # Find brand ID by name
        brand_id = None
        for brand in brands:
            if brand.get("name", "").lower() == brand_name.lower():
                brand_id = brand.get("id")
                break

        if not brand_id:
            return f"❌ Brand '{brand_name}' not found. Available brands: {', '.join([b.get('name', 'Unknown') for b in brands])}"

        # Calculate date range
        to_date = datetime.utcnow()
        from_date = to_date - timedelta(days=days_back)

        logger.info(f"Fetching mentions for brand '{brand_name}' (ID: {brand_id}) from {from_date} to {to_date}")

        # Fetch mentions with date filtering
        mentions = await crud.get_mentions_by_profile(
            profile_id=UUID(user_id),
            brand_id=brand_id,
            from_date=from_date,
            to_date=to_date,
            limit=500  # Increase limit for comprehensive reports
        )

        if not mentions:
            return f"ℹ️ No mentions found for brand '{brand_name}' in the last {days_back} days."

        # Format mentions for the agent to analyze
        report_data = f"📊 MENTIONS FOR REPORT GENERATION\n\n"
        report_data += f"Brand: {brand_name}\n"
        report_data += f"Period: {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')} ({days_back} days)\n"
        report_data += f"Total Mentions: {len(mentions)}\n\n"

        # Group by topic
        by_topic: Dict[str, list] = {}
        by_platform: Dict[str, int] = {}
        by_date: Dict[str, int] = {}

        for m in mentions:
            # Topic grouping
            topic_name = m.get('topic', {}).get('name', 'N/A') if m.get('topic') else 'N/A'
            by_topic.setdefault(topic_name, []).append(m)

            # Platform distribution
            platform_name = m.get('platform', {}).get('name', 'N/A') if m.get('platform') else 'N/A'
            by_platform[platform_name] = by_platform.get(platform_name, 0) + 1

            # Daily distribution
            pub_date = m.get('published_at', '')
            if pub_date:
                date_key = pub_date.split('T')[0]  # Extract date part
                by_date[date_key] = by_date.get(date_key, 0) + 1

        # Add summary statistics
        report_data += "TOPIC BREAKDOWN:\n"
        for topic, topic_mentions in sorted(by_topic.items(), key=lambda x: len(x[1]), reverse=True):
            unread = sum(1 for m in topic_mentions if not m.get('read_status', False))
            report_data += f"  • {topic}: {len(topic_mentions)} mentions ({unread} unread)\n"

        report_data += "\nPLATFORM DISTRIBUTION:\n"
        for platform, count in sorted(by_platform.items(), key=lambda x: x[1], reverse=True):
            report_data += f"  • {platform}: {count} mentions\n"

        report_data += "\nDAILY ACTIVITY (last 7 days):\n"
        recent_dates = sorted(by_date.items(), reverse=True)[:7]
        for date, count in recent_dates:
            report_data += f"  • {date}: {count} mentions\n"

        # Add detailed mention samples (limited to avoid token overflow)
        report_data += "\nSAMPLE MENTIONS (showing top 15):\n"
        sample_count = min(15, len(mentions))
        for i, m in enumerate(mentions[:sample_count], 1):
            topic = m.get('topic', {}).get('name', 'N/A') if m.get('topic') else 'N/A'
            platform = m.get('platform', {}).get('name', 'N/A') if m.get('platform') else 'N/A'
            date = m.get('published_at', 'N/A')
            caption = m.get('caption', '')[:150]  # Truncate long captions
            link = m.get('post_link', 'N/A')
            report_data += f"\n{i}. [{topic}] {platform} - {date}\n"
            report_data += f"   {caption}...\n"
            report_data += f"   Link: {link}\n"

        logger.info(f"✅ Fetched {len(mentions)} mentions for report generation")
        return report_data

    except Exception as e:
        logger.error(f"Error fetching mentions for report: {e}")
        return f"❌ Error fetching mentions: {str(e)}"


async def save_report(
    crud: "SupabaseCRUD",
    user_id: str,
    title: str,
    content: str,
    brand_name: str,
    report_type: str,
    brands: list[Dict[str, Any]],
) -> str:
    """Save a generated report to the database.

    After you've analyzed the mention data and written a comprehensive report,
    use this tool to save it to the database so the user can access it later
    in the Report Archive.

    Args:
        crud: SupabaseCRUD instance from context
        user_id: The user's ID
        title: Report title (e.g., "Weekly Report - Week 42")
        content: The full report content in Markdown format
        brand_name: Name of the brand this report is for
        report_type: Type of report (weekly, crisis, summary, custom)
        brands: List of user's brands from context

    Returns:
        Success or error message
    """
    try:
        # Find brand ID by name
        brand_id = None
        for brand in brands:
            if brand.get("name", "").lower() == brand_name.lower():
                brand_id = brand.get("id")
                break

        if not brand_id:
            return f"❌ Brand '{brand_name}' not found. Cannot save report."

        # Validate report_type
        valid_types = ['weekly', 'crisis', 'summary', 'custom']
        if report_type not in valid_types:
            return f"❌ Invalid report_type '{report_type}'. Must be one of: {', '.join(valid_types)}"

        # Save report
        logger.info(f"Saving report '{title}' for brand '{brand_name}'")

        report = await crud.create_report(
            user_id=UUID(user_id),
            title=title,
            content=content,
            report_type=report_type,
            brand_id=brand_id
        )

        if report:
            logger.info(f"✅ Report saved successfully with ID: {report.get('id')}")
            return f"✅ Report '{title}' saved successfully! The user can now view it in the Report Archive."
        else:
            logger.error("Failed to save report - no data returned")
            return "❌ Failed to save report. Please try again."

    except Exception as e:
        logger.error(f"Error saving report: {e}")
        return f"❌ Error saving report: {str(e)}"


async def draft_response(
    crud: "SupabaseCRUD",
    mention_id: int,
    format: str,
    tone: str,
    include_full_context: bool = False,
    allowed_brand_ids: Optional[Sequence[int]] = None,
) -> str:
    """Fetch one mention and return drafting instructions for the LLM."""
    try:
        params = DraftResponseRequest(
            mention_id=mention_id,
            format=format,
            tone=tone,
            include_full_context=include_full_context,
        )
    except ValidationError as e:
        return f"❌ Invalid draft_response input: {e}"

    try:
        mention = await crud.get_mention_by_id(params.mention_id)
    except Exception as e:
        logger.error("draft_response database fetch failed: %s", e, exc_info=True)
        return f"❌ Database error while fetching mention: {e}"

    if not mention:
        return f"❌ Mention with id {params.mention_id} was not found."

    if allowed_brand_ids is not None and mention.get("brand_id") not in set(allowed_brand_ids):
        return "❌ Mention access denied for this user."

    brand_name = mention.get("brand", {}).get("name", "N/A") if isinstance(mention.get("brand"), dict) else "N/A"
    topic_name = mention.get("topic", {}).get("name", "N/A") if isinstance(mention.get("topic"), dict) else "N/A"
    platform_name = (
        mention.get("platform", {}).get("name", "N/A")
        if isinstance(mention.get("platform"), dict)
        else "N/A"
    )
    published_at = mention.get("published_at") or mention.get("created_at") or "N/A"
    caption = (mention.get("caption") or "").strip()
    teaser = (mention.get("content_teaser") or "").strip()
    source_text = f"{caption} {teaser}".strip() or "No mention text available."
    source_link = mention.get("post_link") or "N/A"
    full_context_block = ""

    if params.include_full_context and source_link.startswith(("http://", "https://")):
        extracted = await fetch_page_content(source_link)
        full_context_block = (
            "\n\nExtended source context (fetched from URL):\n"
            f"{extracted[:4000]}"
        )

    style_guide = _render_draft_style_instructions(params.format, params.tone)

    return (
        "ATLAS EDITOR TASK: Draft a response based strictly on this mention.\n\n"
        f"Target format: {params.format}\n"
        f"Tone: {params.tone}\n"
        f"{style_guide}\n\n"
        "Source mention:\n"
        f"- Mention ID: {params.mention_id}\n"
        f"- Brand: {brand_name}\n"
        f"- Topic: {topic_name}\n"
        f"- Platform: {platform_name}\n"
        f"- Published at: {published_at}\n"
        f"- Link: {source_link}\n"
        f"- Text: {source_text}"
        f"{full_context_block}\n\n"
        "Output requirements:\n"
        "1. Keep factual alignment with the source text.\n"
        "2. Do not invent claims that are not present in the mention.\n"
        "3. If context is missing, use neutral placeholder wording."
    )


async def fetch_mention_context(
    crud: "SupabaseCRUD",
    mention_id: int,
    include_full_page: bool = False,
    allowed_brand_ids: Optional[Sequence[int]] = None,
) -> str:
    """Fetch structured mention context and optionally full page content from mention URL."""
    try:
        params = MentionContextRequest(
            mention_id=mention_id,
            include_full_page=include_full_page,
        )
    except ValidationError as e:
        return f"❌ Invalid fetch_mention_context input: {e}"

    try:
        mention = await crud.get_mention_by_id(params.mention_id)
    except Exception as e:
        logger.error("fetch_mention_context database fetch failed: %s", e, exc_info=True)
        return f"❌ Database error while fetching mention: {e}"

    if not mention:
        return f"❌ Mention with id {params.mention_id} was not found."

    if allowed_brand_ids is not None and mention.get("brand_id") not in set(allowed_brand_ids):
        return "❌ Mention access denied for this user."

    brand_name = mention.get("brand", {}).get("name", "N/A") if isinstance(mention.get("brand"), dict) else "N/A"
    topic_name = mention.get("topic", {}).get("name", "N/A") if isinstance(mention.get("topic"), dict) else "N/A"
    platform_name = (
        mention.get("platform", {}).get("name", "N/A")
        if isinstance(mention.get("platform"), dict)
        else "N/A"
    )
    published_at = mention.get("published_at") or mention.get("created_at") or "N/A"
    caption = (mention.get("caption") or "").strip()
    teaser = (mention.get("content_teaser") or "").strip()
    source_link = mention.get("post_link") or "N/A"

    result = (
        f"Mention context\n"
        f"- Mention ID: {params.mention_id}\n"
        f"- Brand: {brand_name}\n"
        f"- Topic: {topic_name}\n"
        f"- Platform: {platform_name}\n"
        f"- Published at: {published_at}\n"
        f"- Link: {source_link}\n"
        f"- Caption: {caption or 'N/A'}\n"
        f"- Teaser: {teaser or 'N/A'}"
    )

    if params.include_full_page and source_link.startswith(("http://", "https://")):
        extracted = await fetch_page_content(source_link)
        result += f"\n\nExtended source context (URL extraction):\n{extracted[:4000]}"

    return result
