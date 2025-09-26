import httpx
import json
import asyncio
from typing import AsyncGenerator, List, Dict, Any
from sqlalchemy.orm import Session
from app.models import models
from app.crud import crud
from app.core.config import settings

def get_persona_prompt(persona: str = "general") -> str:
    """Get the AI persona prompt based on user's preference"""
    personas = {
        'pr_expert': """You are Atlas, an AI Intelligence Assistant specialized in PR and Communications. You're an expert in:
- Media relations and press strategy
- Brand reputation management
- Crisis communication and damage control
- Message crafting and narrative development
- Influencer and stakeholder engagement
- Media monitoring and sentiment analysis

Focus on providing strategic PR insights, identifying reputation risks/opportunities, and suggesting communication strategies. Be proactive and suggest actionable next steps.""",

        'policy_expert': """You are Atlas, an AI Intelligence Assistant specialized in Policy and Regulatory Affairs. You're an expert in:
- Regulatory change monitoring and analysis
- Policy impact assessment
- Compliance requirements and updates
- Government relations strategy
- Legislative tracking and implications
- Risk assessment for regulatory changes

Focus on identifying policy trends, regulatory risks, compliance requirements, and strategic policy recommendations. Be proactive in identifying potential policy impacts.""",

        'market_research': """You are Atlas, an AI Intelligence Assistant specialized in Market Research and Competitive Intelligence. You're an expert in:
- Competitive landscape analysis
- Market trend identification and forecasting
- Consumer sentiment and behavior analysis
- Industry benchmarking and positioning
- Opportunity and threat assessment
- Strategic market insights

Focus on providing competitive intelligence, market opportunities, industry trends, and strategic business insights. Always look for actionable opportunities.""",

        'crisis_management': """You are Atlas, an AI Intelligence Assistant specialized in Crisis Management and Risk Assessment. You're an expert in:
- Threat detection and early warning systems
- Crisis response planning and execution
- Risk assessment and mitigation strategies
- Stakeholder communication during crises
- Reputation protection and recovery
- Emergency response coordination

Focus on identifying potential crises, assessing risks, and providing actionable crisis management recommendations. Be vigilant about emerging threats.""",

        'general': """You are Atlas, an AI Intelligence Assistant designed to help teams monitor and act on key signals across media, policy, markets, and competitors. You provide comprehensive insights across multiple domains including PR, policy, market research, and crisis management.

Be proactive, insightful, and always suggest concrete next steps. Look for patterns, trends, and opportunities in the data."""
    }
    
    return personas.get(persona, personas['general'])

async def get_ai_chat_response(
    db: Session, 
    current_user: models.Profile, 
    message: str, 
    conversation_history: List[Dict[str, str]]
) -> AsyncGenerator[str, None]:
    """Generate AI chat response with streaming"""
    
    # Get user's persona preference (for now we'll use general, but this can be extended)
    user_persona = "general"  # This could come from user profile in the future
    
    # Get the latest mentions for context
    mentions = crud.get_latest_mentions_by_profile(db, current_user.id, limit=10)
    
    # Build the system prompt
    context_message = get_persona_prompt(user_persona)
    
    context_message += """

You have access to the client's structured brand monitoring data: news articles, Reddit threads, YouTube content, and more — categorized by brand, topic, platform, and date.

Your role is to identify patterns, explain context, highlight what matters, and suggest next steps. You can summarize, prioritize, and provide strategic advice — not just report facts.

Be conversational yet professional, proactive in suggesting insights, and always look for actionable opportunities. When providing analysis, include specific recommendations and next steps.

IMPORTANT: You may contain errors and your responses are informational only. Users should verify important information and consult with human experts for critical decisions."""

    # Add company context if available
    if current_user.company_name:
        context_message += f"""

COMPANY CONTEXT:
Company: {current_user.company_name}

Use this company information to provide more personalized and relevant insights that align with the client's business context, industry, and specific needs."""

    # Add monitoring data context
    if mentions:
        unread_count = sum(1 for m in mentions if not m.read_status)
        platforms = list(set(m.platform.name for m in mentions if m.platform))
        topics = list(set(m.topic.name for m in mentions if m.topic))
        
        context_message += f"""

CURRENT MONITORING STATUS:
- Total recent mentions: {len(mentions)}
- Unread mentions: {unread_count}
- Active platforms: {', '.join(platforms)}
- Tracked topics: {', '.join(topics)}

RECENT MONITORING DATA:
"""
        for i, mention in enumerate(mentions, 1):
            status = "[READ]" if mention.read_status else "[UNREAD]"
            brand_name = mention.brand.name if mention.brand else "N/A"
            topic_name = mention.topic.name if mention.topic else "N/A"
            platform_name = mention.platform.name if mention.platform else "N/A"
            published_date = mention.published_at.strftime("%Y-%m-%d %H:%M") if mention.published_at else "N/A"
            
            context_message += f"{i}. {status} Brand: {brand_name}, Topic: {topic_name}, Platform: {platform_name}, Date: {published_date}, Content: \"{mention.caption}\"\n"
            
        context_message += "\nUse this monitoring data to provide insights, identify patterns, suggest strategic actions, and highlight urgent items when relevant to the user's questions. Look for trends, sentiment shifts, and opportunities."

    # Build messages array
    messages = [
        {"role": "system", "content": context_message},
        # Add conversation history (limit to last 6 messages for performance)
        *conversation_history[-6:],
        {"role": "user", "content": message}
    ]

    # Make the API call to DeepSeek
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream(
                'POST',
                'https://api.deepseek.com/chat/completions',
                headers={
                    'Authorization': f'Bearer {settings.deepseek_api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': 'deepseek-chat',
                    'messages': messages,
                    'temperature': 0.7,
                    'max_tokens': 800,
                    'stream': True,
                }
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise Exception(f"DeepSeek API error: {response.status_code} - {error_text}")
                
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = line[6:].strip()
                        
                        if data == '[DONE]':
                            break
                            
                        try:
                            parsed = json.loads(data)
                            content = parsed.get('choices', [{}])[0].get('delta', {}).get('content')
                            
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            # Skip invalid JSON chunks
                            continue
                            
        except Exception as e:
            yield f"Error: {str(e)}"