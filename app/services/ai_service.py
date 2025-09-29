import httpx
import json
import asyncio
from typing import AsyncGenerator, List, Dict, Any
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
    message: str, 
    conversation_history: List[Dict[str, str]],
    context: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Generate AI chat response with streaming using Supabase context"""
    
    # Get user's persona preference (for now we'll use general, but this can be extended)
    user_persona = "general"  # This could come from user profile in the future
    
    # Extract mentions from context
    mentions = context.get("recent_mentions", [])
    
    # Build the system prompt
    context_message = get_persona_prompt(user_persona)
    
    context_message += """

You have access to the client's structured brand monitoring data: news articles, Reddit threads, YouTube content, and more — categorized by brand, topic, platform, and date.

Your role is to identify patterns, explain context, highlight what matters, and suggest next steps. You can summarize, prioritize, and provide strategic advice — not just report facts.

Be conversational yet professional, proactive in suggesting insights, and always look for actionable opportunities. When providing analysis, include specific recommendations and next steps.

IMPORTANT: You may contain errors and your responses are informational only. Users should verify important information and consult with human experts for critical decisions."""

    # Add company context if available
    user_profile = context.get("user_profile", {})
    if user_profile.get("company_name"):
        context_message += f"""

COMPANY CONTEXT:
Company: {user_profile['company_name']}

Use this company information to provide more personalized and relevant insights that align with the client's business context, industry, and specific needs."""

    # Add monitoring data context
    if mentions:
        unread_count = sum(1 for m in mentions if not m.get("read_status", False))
        brands = context.get("brands", [])
        
        context_message += f"""

CURRENT MONITORING STATUS:
- Total recent mentions: {len(mentions)}
- Unread mentions: {unread_count}
- Monitored brands: {', '.join([b['name'] for b in brands])}

RECENT MONITORING DATA:
"""
        for i, mention in enumerate(mentions, 1):
            status = "[READ]" if mention.get("read_status") else "[UNREAD]"
            brand_name = mention.get("brands", {}).get("name", "N/A") if mention.get("brands") else "N/A"
            topic_name = mention.get("topics", {}).get("name", "N/A") if mention.get("topics") else "N/A"
            platform_name = mention.get("platforms", {}).get("name", "N/A") if mention.get("platforms") else "N/A"
            published_date = mention.get("published_at", "N/A")
            
            context_message += f"{i}. {status} Brand: {brand_name}, Topic: {topic_name}, Platform: {platform_name}, Date: {published_date}, Content: \"{mention.get('caption', '')}\"\n"
            
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