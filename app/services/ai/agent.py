"""
PydanticAI Agent Management

Handles agent creation, caching, and tool registration.
"""

import logging
from typing import Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.deepseek import DeepSeekProvider

from app.core.config import settings

from .context import UserContext
from .tools import (
    web_search,
    fetch_page_content,
    analyze_mentions,
    compare_brands as compare_brands_tool,
    analyze_sentiment_trend as analyze_sentiment_trend_tool,
    fetch_mentions_for_report,
    save_report,
    draft_response as draft_response_tool,
)

logger = logging.getLogger(__name__)


def _create_deepseek_model() -> OpenAIModel:
    """Build a DeepSeek model instance without mutating global environment variables."""
    provider = DeepSeekProvider(api_key=settings.deepseek_api_key)
    return OpenAIModel(settings.deepseek_model, provider=provider)


def create_agent_with_prompt(persona: str, system_prompt: str) -> Agent:
    """Create a new PydanticAI agent with a specific system prompt

    Args:
        persona: The persona type (for logging)
        system_prompt: The complete system prompt string

    Returns:
        Configured Agent instance with tools registered
    """
    agent = Agent(
        _create_deepseek_model(),
        deps_type=UserContext,
        system_prompt=system_prompt,  # Static string!
        model_settings={
            'temperature': 0.7,
            'tool_choice': 'auto',  # Explicitly enable tool calling
            # No max_tokens limit - let DeepSeek use what it needs for tool calls
        },
        retries=2  # Retry on tool call failures
    )

    # Enable debug logging for HTTP requests
    logging.getLogger('httpx').setLevel(logging.DEBUG)
    logging.getLogger('pydantic_ai').setLevel(logging.DEBUG)

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
        logger.info("🔧 TOOL CALLED: analyze_user_mentions")
        return await analyze_mentions(ctx.deps.recent_mentions)

    @agent.tool
    async def compare_brands(
        ctx: RunContext[UserContext],
        brand_a: str,
        brand_b: str,
        days_back: int = 7,
    ) -> str:
        """Compare mention volume and sentiment between two brands."""
        logger.info(
            "🔧 TOOL CALLED: compare_brands(brand_a=%s, brand_b=%s, days_back=%s)",
            brand_a,
            brand_b,
            days_back,
        )
        if not ctx.deps.crud:
            return "❌ Error: Database access not available"

        return await compare_brands_tool(
            crud=ctx.deps.crud,
            brands=ctx.deps.brands,
            brand_a=brand_a,
            brand_b=brand_b,
            days_back=days_back,
        )

    @agent.tool
    async def analyze_sentiment_trend(
        ctx: RunContext[UserContext],
        brand_name: str,
        days_back: int = 14,
    ) -> str:
        """Analyze sentiment trend for one brand over a time window."""
        logger.info(
            "🔧 TOOL CALLED: analyze_sentiment_trend(brand_name=%s, days_back=%s)",
            brand_name,
            days_back,
        )
        if not ctx.deps.crud:
            return "❌ Error: Database access not available"

        return await analyze_sentiment_trend_tool(
            crud=ctx.deps.crud,
            brands=ctx.deps.brands,
            brand_name=brand_name,
            days_back=days_back,
        )

    # Register tool: fetch_mentions_for_report
    @agent.tool
    async def generate_report_data(ctx: RunContext[UserContext], brand_name: str, days_back: int) -> str:
        """Fetch mentions for a specific brand and time period to generate a comprehensive report.

        Use this when the user asks you to create a weekly report, crisis report,
        or any custom analysis for a specific brand over a date range.

        Args:
            brand_name: The name of the brand to analyze (must match exactly)
            days_back: Number of days back from today (e.g., 7 for weekly, 30 for monthly)

        Returns:
            Formatted mention data with statistics and samples ready for report generation
        """
        logger.info(f"🔧 TOOL CALLED: generate_report_data(brand_name={brand_name}, days_back={days_back})")
        if not ctx.deps.crud:
            return "❌ Error: Database access not available"

        return await fetch_mentions_for_report(
            crud=ctx.deps.crud,
            user_id=ctx.deps.user_id,
            brand_name=brand_name,
            days_back=days_back,
            brands=ctx.deps.brands
        )

    # Register tool: save_report
    @agent.tool
    async def save_generated_report(
        ctx: RunContext[UserContext],
        title: str,
        content: str,
        brand_name: str,
        report_type: str
    ) -> str:
        """Save a generated report to the database for the user to access later.

        After you've analyzed mention data and written a comprehensive Markdown report,
        use this tool to save it. The user will be able to view it in the Report Archive.

        Args:
            title: Short descriptive title (e.g., "Weekly Report - Week 42, 2024")
            content: Full report content in Markdown format with headings, lists, and formatting
            brand_name: Name of the brand this report analyzes
            report_type: Type of report - must be one of: "weekly", "crisis", "summary", or "custom"

        Returns:
            Success or error message
        """
        logger.info(f"🔧 TOOL CALLED: save_generated_report(title={title}, brand={brand_name}, type={report_type})")
        if not ctx.deps.crud:
            return "❌ Error: Database access not available"

        return await save_report(
            crud=ctx.deps.crud,
            user_id=ctx.deps.user_id,
            title=title,
            content=content,
            brand_name=brand_name,
            report_type=report_type,
            brands=ctx.deps.brands
        )

    @agent.tool
    async def draft_response(
        ctx: RunContext[UserContext],
        mention_id: int,
        format: Literal["linkedin", "email", "press_release"],
        tone: Literal["professional", "urgent", "casual"],
    ) -> str:
        """Draft a LinkedIn/email/press-release response from one mention."""
        logger.info(
            "🔧 TOOL CALLED: draft_response(mention_id=%s, format=%s, tone=%s)",
            mention_id,
            format,
            tone,
        )
        if not ctx.deps.crud:
            return "❌ Error: Database access not available"

        allowed_brand_ids = [
            brand["id"]
            for brand in ctx.deps.brands
            if isinstance(brand.get("id"), int)
        ]
        return await draft_response_tool(
            crud=ctx.deps.crud,
            mention_id=mention_id,
            format=format,
            tone=tone,
            allowed_brand_ids=allowed_brand_ids,
        )

    # Debug: Inspect agent's registered tools
    try:
        import inspect
        # Get all tool functions
        tool_funcs = [
            name for name, method in inspect.getmembers(agent)
            if 'tool' in name.lower() or callable(method)
        ]
        logger.info(f"🔍 Agent methods: {tool_funcs[:10]}")  # First 10 to avoid spam

        # Try to access the agent's internal function tools
        if hasattr(agent, '_function_tools'):
            logger.info(f"🔍 _function_tools: {len(agent._function_tools)} tools")
        if hasattr(agent, 'functions'):
            logger.info(f"🔍 functions: {agent.functions}")

    except Exception as e:
        logger.error(f"Error inspecting agent: {e}")

    logger.info(f"✅ Created agent for persona: {persona} with 8 tools")
    return agent
