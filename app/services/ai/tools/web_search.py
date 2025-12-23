"""
Web Search Tool using Tavily API

Provides real-time web search capability for the AI agent.
"""

import asyncio
import logging
from typing import Optional
from tavily import TavilyClient
from app.core.config import settings

logger = logging.getLogger(__name__)

# Singleton Tavily client
_tavily_client: Optional[TavilyClient] = None


def get_tavily_client() -> Optional[TavilyClient]:
    """Get or create Tavily client (singleton)

    Returns:
        TavilyClient instance or None if API key not configured
    """
    global _tavily_client
    if _tavily_client is None and settings.tavily_api_key:
        try:
            _tavily_client = TavilyClient(api_key=settings.tavily_api_key)
            logger.info("Tavily client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Tavily client: {e}")
            return None
    return _tavily_client


async def web_search(query: str) -> str:
    """Search the web for current information using Tavily.

    Use this when you need recent information not in the monitoring data,
    such as current events, competitor news, industry developments, or fact-checking.

    Args:
        query: The search query (be specific and focused)

    Returns:
        Formatted search results with titles, URLs, and content snippets
    """
    tavily = get_tavily_client()
    if not tavily:
        return "Web search unavailable (Tavily API key not configured)"

    try:
        logger.info(f"Executing web search: {query}")

        # Run synchronous Tavily call in thread pool to avoid blocking
        response = await asyncio.to_thread(
            tavily.search,
            query,
            max_results=5
        )

        results = []
        for r in response.get('results', []):
            results.append(
                f"Title: {r.get('title', 'N/A')}\n"
                f"Source: {r.get('url', 'N/A')}\n"
                f"Content: {r.get('content', 'N/A')}\n"
            )

        if not results:
            return f"No results found for: {query}"

        return "\n---\n".join(results)

    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"Search error: {str(e)}"
