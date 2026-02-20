"""
Mention Analysis Tool

Provides detailed analysis of user mentions beyond the system prompt summary.
"""

import logging
from typing import Dict, List

from app.schemas.mention import MentionContext

logger = logging.getLogger(__name__)


async def analyze_mentions(mentions: List[MentionContext]) -> str:
    """Analyze all recent mentions for patterns, sentiment, and trends.

    Use this to get detailed analysis of the monitoring data beyond
    the summary in the system prompt. Provides breakdown by brand, topic,
    and platform with key insights.

    Args:
        mentions: List of mention dictionaries from user context

    Returns:
        Formatted analysis of recent mentions with patterns and trends
    """
    if not mentions:
        return "No recent mentions to analyze"

    logger.info(f"Analyzing {len(mentions)} mentions")

    # Build detailed analysis
    analysis = f"DETAILED MENTION ANALYSIS ({len(mentions)} mentions):\n\n"

    # Group by brand
    by_brand: Dict[str, List[MentionContext]] = {}
    for mention in mentions:
        brand_name = mention.brand.name if mention.brand else "Unknown"
        by_brand.setdefault(brand_name, []).append(mention)

    for brand, brand_mentions in by_brand.items():
        unread = sum(1 for mention in brand_mentions if not mention.read_status)
        analysis += f"📊 Brand: {brand} ({len(brand_mentions)} mentions, {unread} unread)\n"

        # Group by topic within brand
        by_topic: Dict[str, int] = {}
        by_platform: Dict[str, int] = {}

        for mention in brand_mentions:
            topic = mention.topic.name if mention.topic else "N/A"
            platform = mention.platform.name if mention.platform else "N/A"
            by_topic[topic] = by_topic.get(topic, 0) + 1
            by_platform[platform] = by_platform.get(platform, 0) + 1

        # Show topic breakdown
        analysis += f"  Topics: {', '.join([f'{k} ({v})' for k, v in sorted(by_topic.items(), key=lambda x: x[1], reverse=True)])}\n"
        analysis += f"  Platforms: {', '.join([f'{k} ({v})' for k, v in sorted(by_platform.items(), key=lambda x: x[1], reverse=True)])}\n"

        # Show sample mentions (top 3)
        analysis += f"  Sample mentions:\n"
        for i, mention in enumerate(brand_mentions[:3], 1):
            topic = mention.topic.name if mention.topic else "N/A"
            platform = mention.platform.name if mention.platform else "N/A"
            date = mention.published_at.isoformat() if mention.published_at else "N/A"
            caption = (mention.caption or "")[:100]
            status = "✓" if mention.read_status else "○"
            analysis += f"    {status} [{topic}] {platform} ({date}): {caption}...\n"

        analysis += "\n"

    return analysis
