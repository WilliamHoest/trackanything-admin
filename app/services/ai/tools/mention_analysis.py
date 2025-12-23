"""
Mention Analysis Tool

Provides detailed analysis of user mentions beyond the system prompt summary.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


async def analyze_mentions(mentions: List[Dict]) -> str:
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
    by_brand: Dict[str, List[Dict]] = {}
    for m in mentions:
        brand_name = m.get('brands', {}).get('name', 'Unknown') if m.get('brands') else 'Unknown'
        by_brand.setdefault(brand_name, []).append(m)

    for brand, brand_mentions in by_brand.items():
        unread = sum(1 for m in brand_mentions if not m.get('read_status'))
        analysis += f"📊 Brand: {brand} ({len(brand_mentions)} mentions, {unread} unread)\n"

        # Group by topic within brand
        by_topic: Dict[str, int] = {}
        by_platform: Dict[str, int] = {}

        for m in brand_mentions:
            topic = m.get('topics', {}).get('name', 'N/A') if m.get('topics') else 'N/A'
            platform = m.get('platforms', {}).get('name', 'N/A') if m.get('platforms') else 'N/A'
            by_topic[topic] = by_topic.get(topic, 0) + 1
            by_platform[platform] = by_platform.get(platform, 0) + 1

        # Show topic breakdown
        analysis += f"  Topics: {', '.join([f'{k} ({v})' for k, v in sorted(by_topic.items(), key=lambda x: x[1], reverse=True)])}\n"
        analysis += f"  Platforms: {', '.join([f'{k} ({v})' for k, v in sorted(by_platform.items(), key=lambda x: x[1], reverse=True)])}\n"

        # Show sample mentions (top 3)
        analysis += f"  Sample mentions:\n"
        for i, m in enumerate(brand_mentions[:3], 1):
            topic = m.get('topics', {}).get('name', 'N/A') if m.get('topics') else 'N/A'
            platform = m.get('platforms', {}).get('name', 'N/A') if m.get('platforms') else 'N/A'
            date = m.get('published_at', 'N/A')
            caption = m.get('caption', '')[:100]
            status = "✓" if m.get('read_status') else "○"
            analysis += f"    {status} [{topic}] {platform} ({date}): {caption}...\n"

        analysis += "\n"

    return analysis
