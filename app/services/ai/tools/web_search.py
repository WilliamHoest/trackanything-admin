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


async def search_brand_web(
    brand_name: str,
    focus: str = "",
    days_back: int = 7,
    max_results: int = 8,
) -> str:
    """Run brand-focused external web search using Tavily."""
    clean_brand = brand_name.strip()
    clean_focus = focus.strip()
    safe_days_back = max(1, min(int(days_back), 60))
    safe_max_results = max(1, min(int(max_results), 10))

    if not clean_brand:
        return "Brand name is required for brand web search."

    query_parts = [clean_brand, "news", f"last {safe_days_back} days"]
    if clean_focus:
        query_parts.append(clean_focus)
    query = " ".join(query_parts)

    tavily = get_tavily_client()
    if not tavily:
        return "Web search unavailable (Tavily API key not configured)"

    try:
        logger.info(
            "Executing brand web search: brand=%s, focus=%s, days_back=%s, max_results=%s",
            clean_brand,
            clean_focus,
            safe_days_back,
            safe_max_results,
        )
        response = await asyncio.to_thread(
            tavily.search,
            query,
            max_results=safe_max_results,
        )

        results = response.get('results', []) or []
        if not results:
            return (
                f"No external web results found for brand '{clean_brand}' "
                f"(focus='{clean_focus or 'general'}')."
            )

        lines = [
            f"External web results for brand '{clean_brand}' "
            f"(focus='{clean_focus or 'general'}', window={safe_days_back} days):"
        ]
        for i, row in enumerate(results, 1):
            lines.append(
                f"\n{i}. {row.get('title', 'N/A')}\n"
                f"   URL: {row.get('url', 'N/A')}\n"
                f"   Snippet: {row.get('content', 'N/A')}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error("Brand web search failed: %s", e, exc_info=True)
        return f"Brand web search error: {e}"
