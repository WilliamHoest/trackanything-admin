"""
AI Service Package using PydanticAI

Main exports for the AI service functionality.
"""

from typing import AsyncGenerator, List, Dict, Any, Tuple
import logging
import asyncio
from .context import UserContext
from .personas import build_context_message

logger = logging.getLogger(__name__)


def _extract_tools_used(result: Any) -> List[str]:
    """Extract unique tool names used during an agent run."""
    try:
        messages = result.all_messages()
    except Exception:
        return []

    tools_used: List[str] = []
    seen: set[str] = set()

    for message in messages:
        for part in getattr(message, "parts", []) or []:
            tool_name = getattr(part, "tool_name", None)
            if not tool_name:
                continue
            if tool_name in seen:
                continue
            seen.add(tool_name)
            tools_used.append(tool_name)

    return tools_used


async def run_chat_once(
    message: str,
    conversation_history: List[Dict[str, str]],
    context: UserContext,
    persona: str = "general",
) -> Tuple[str, List[str]]:
    """Run the AI agent once and return final text + tools used."""
    # Build system prompt with current context FIRST
    system_prompt = build_context_message(persona, context)
    logger.info(f"📋 Built system prompt: {len(system_prompt)} chars")

    # Create agent with this specific system prompt (no caching due to user-specific context)
    from .agent import create_agent_with_prompt
    agent = create_agent_with_prompt(persona, system_prompt)

    # Convert conversation history to PydanticAI format (last 6 messages)
    messages = [
        {'role': msg['role'], 'content': msg['content']}
        for msg in conversation_history[-6:]
    ]

    logger.info(f"Running chat response for user {context.user_id} with persona {persona}")
    logger.info("🔍 Agent has tools registered and ready")
    logger.info(f"🔍 Agent model: {agent.model}")
    logger.info(f"🔍 User message: {message}")

    result = await agent.run(
        message,
        message_history=messages,
        deps=context,
    )

    if hasattr(result, 'output'):
        final_text = result.output
    elif hasattr(result, 'data'):
        final_text = result.data
    else:
        final_text = str(result)

    final_str = str(final_text)
    tools_used = _extract_tools_used(result)
    logger.info(f"🔧 Tools used in run: {tools_used}")

    return final_str, tools_used


async def stream_chat_response(
    message: str,
    conversation_history: List[Dict[str, str]],
    context: UserContext,
    persona: str = "general"
) -> AsyncGenerator[str, None]:
    """Stream AI chat response using PydanticAI

    Args:
        message: User's current message
        conversation_history: Previous messages (list of {role, content})
        context: User context data (UserContext model)
        persona: AI persona to use (default: "general")

    Yields:
        Text chunks (plain strings) for streaming to client
    """
    try:
        final_str, tools_used = await run_chat_once(
            message=message,
            conversation_history=conversation_history,
            context=context,
            persona=persona,
        )
        logger.info(f"🔍 Final response ({len(final_str)} chars): {final_str[:200]}...")
        logger.info(f"🔧 Tools used for streamed response: {tools_used}")

        chunk_size = 10  # Characters per chunk

        for i in range(0, len(final_str), chunk_size):
            chunk = final_str[i:i+chunk_size]
            yield chunk
            # Small delay for smooth streaming effect
            await asyncio.sleep(0.01)

        logger.info(f"🔍 Streaming completed")

    except Exception as e:
        logger.error(f"AI service error: {e}", exc_info=True)
        yield f"Error: {str(e)}"


__all__ = [
    'UserContext',
    'stream_chat_response',
    'run_chat_once',
]
