"""
PydanticAI Agent Management

Handles agent creation, caching, and tool registration.
"""

import logging
from pydantic_ai import Agent, RunContext
from .context import UserContext
from .tools import web_search, fetch_page_content, analyze_mentions, fetch_mentions_for_report, save_report

logger = logging.getLogger(__name__)


def create_agent_with_prompt(persona: str, system_prompt: str) -> Agent:
    """Create a new PydanticAI agent with a specific system prompt

    Args:
        persona: The persona type (for logging)
        system_prompt: The complete system prompt string

    Returns:
        Configured Agent instance with tools registered
    """
    # Use OpenAI-compatible format for DeepSeek
    # Set env vars for OpenAI SDK to use DeepSeek endpoint
    import os
    os.environ['OPENAI_BASE_URL'] = 'https://api.deepseek.com'
    os.environ['OPENAI_API_KEY'] = os.getenv('DEEPSEEK_API_KEY', '')

    # Use openai: prefix which will use the OPENAI_BASE_URL env var
    agent = Agent(
        'openai:deepseek-chat',
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

    logger.info(f"✅ Created agent for persona: {persona} with 5 tools")
    return agent
