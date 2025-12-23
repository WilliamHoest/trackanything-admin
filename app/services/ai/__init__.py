"""
AI Service Package using PydanticAI

Main exports for the AI service functionality.
"""

from typing import AsyncGenerator, List, Dict, Any
import logging
from .context import UserContext
from .personas import build_context_message
from .agent import get_agent_for_persona

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
        # Get agent for persona
        agent = get_agent_for_persona(persona)

        # Build system prompt with current context
        system_prompt = build_context_message(persona, context)

        # Convert conversation history to PydanticAI format (last 6 messages)
        messages = [
            {'role': msg['role'], 'content': msg['content']}
            for msg in conversation_history[-6:]
        ]

        logger.info(f"Streaming chat response for user {context.user_id} with persona {persona}")

        # Run agent with streaming
        async with agent.run_stream(
            message,
            message_history=messages,
            deps=context,
            model_settings={
                'temperature': 0.7,
                'max_tokens': 800,
            }
        ) as result:
            # Stream text chunks (deltas)
            async for chunk in result.stream_text(delta=True):
                if chunk:
                    yield chunk

    except Exception as e:
        logger.error(f"AI service error: {e}", exc_info=True)
        yield f"Error: {str(e)}"


__all__ = [
    'UserContext',
    'stream_chat_response',
]
