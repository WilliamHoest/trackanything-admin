"""
AI Service Package using PydanticAI

Main exports for the AI service functionality.
"""

from typing import AsyncGenerator, List, Dict, Any
import logging
import asyncio
from .context import UserContext
from .personas import build_context_message

logger = logging.getLogger(__name__)


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

        logger.info(f"Streaming chat response for user {context.user_id} with persona {persona}")

        # DEBUG: Log that tools are registered
        logger.info(f"🔍 Agent has tools registered and ready")
        logger.info(f"🔍 Agent model: {agent.model}")
        logger.info(f"🔍 User message: {message}")

        # CRITICAL CHANGE: Use run() instead of run_stream() to properly execute tools
        # Then manually stream the result to the client
        logger.info(f"🔍 Running agent with tool execution (non-streaming)...")

        # Run agent and wait for complete result (including tool execution)
        result = await agent.run(
            message,
            message_history=messages,
            deps=context,
        )

        logger.info(f"🔍 Agent execution completed")

        # Get the final data after all tool calls
        # PydanticAI RunResult uses .output or .data depending on version
        if hasattr(result, 'output'):
            final_text = result.output
        elif hasattr(result, 'data'):
            final_text = result.data
        else:
            # Fallback: convert result to string directly
            final_text = str(result)

        logger.info(f"🔍 Final response ({len(str(final_text))} chars): {str(final_text)[:200]}...")

        # Manually stream the response character by character for smooth UX
        final_str = str(final_text)
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
]
