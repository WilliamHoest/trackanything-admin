"""
PydanticAI Agent Management

Handles agent creation, caching, and tool registration.
"""

import logging
from typing import Dict
from pydantic_ai import Agent, RunContext
from .context import UserContext
from .personas import build_context_message
from .tools import web_search, fetch_page_content, analyze_mentions

logger = logging.getLogger(__name__)

# Agent cache (one per persona)
_agent_cache: Dict[str, Agent] = {}


def create_agent(persona: str) -> Agent:
    """Create a new PydanticAI agent for a specific persona

    Args:
        persona: The persona type (general, pr_expert, etc.)

    Returns:
        Configured Agent instance with tools registered
    """
    # Create agent with DeepSeek model
    agent = Agent(
        'deepseek:deepseek-chat',
        deps_type=UserContext,
        model_settings={
            'temperature': 0.7,
            'max_tokens': 800,
        }
    )

    # Register tool: web_search
    @agent.tool
    async def search_web(ctx: RunContext[UserContext], query: str) -> str:
        """Search the web for current information.

        Use this when you need recent information not in the monitoring data,
        such as current events, competitor news, industry developments, or fact-checking.

        Args:
            query: The search query (be specific and focused)

        Returns:
            Formatted search results with titles, URLs, and content snippets
        """
        return await web_search(query)

    # Register tool: fetch_page_content
    @agent.tool
    async def fetch_content(ctx: RunContext[UserContext], url: str) -> str:
        """Extract full content from a specific web page.

        Use this to get detailed information from a specific URL,
        such as competitor announcements, policy documents, or news articles.

        Args:
            url: The complete URL to fetch (must be a valid web address)

        Returns:
            The extracted page content
        """
        return await fetch_page_content(url)

    # Register tool: analyze_mentions
    @agent.tool
    async def analyze_user_mentions(ctx: RunContext[UserContext]) -> str:
        """Analyze all recent mentions for patterns, sentiment, and trends.

        Use this to get detailed analysis of the monitoring data beyond
        the summary in the system prompt. Provides breakdown by brand, topic,
        and platform with key insights.

        Returns:
            Formatted analysis of recent mentions with patterns and trends
        """
        return await analyze_mentions(ctx.deps.recent_mentions)

    logger.info(f"Created new agent for persona: {persona}")
    return agent


def get_agent_for_persona(persona: str = "general") -> Agent:
    """Get or create cached agent for specific persona

    Args:
        persona: The persona type

    Returns:
        Cached or newly created Agent instance
    """
    if persona not in _agent_cache:
        _agent_cache[persona] = create_agent(persona)
    return _agent_cache[persona]
