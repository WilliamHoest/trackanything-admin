"""
Content Fetch Tool using Tavily API

Extracts full content from specific web pages for detailed analysis.
"""

import asyncio
import logging
from .web_search import get_tavily_client

logger = logging.getLogger(__name__)


async def fetch_page_content(url: str) -> str:
    """Extract full content from a specific web page using Tavily.

    Use this to get detailed information from a specific URL,
    such as competitor announcements, policy documents, or news articles.

    Args:
        url: The complete URL to fetch (must be a valid web address)

    Returns:
        The extracted page content (truncated to 3000 chars if needed)
    """
    tavily = get_tavily_client()
    if not tavily:
        return "Content extraction unavailable (Tavily API key not configured)"

    try:
        logger.info(f"Fetching page content: {url}")

        # Run synchronous Tavily call in thread pool to avoid blocking
        response = await asyncio.to_thread(
            tavily.extract,
            urls=[url]
        )

        if not response or 'results' not in response or not response['results']:
            return f"No content extracted from: {url}"

        # Get first result
        content = response['results'][0].get('raw_content', '')
        if not content:
            return f"No content extracted from: {url}"

        # Limit content length to avoid token overflow
        max_length = 3000
        if len(content) > max_length:
            content = content[:max_length] + "... (content truncated)"

        return content

    except Exception as e:
        logger.error(f"Page fetch failed: {e}")
        return f"Fetch error: {str(e)}"
