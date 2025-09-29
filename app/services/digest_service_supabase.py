from typing import Dict, List
import requests
from collections import defaultdict
from app.crud.supabase_crud import SupabaseCRUD

async def create_and_send_digest_supabase(crud: SupabaseCRUD, brand_id: int) -> Dict:
    """
    Creates and sends a digest of new mentions for a brand to its webhook using Supabase
    
    Args:
        crud: Supabase CRUD instance
        brand_id: ID of the brand to send digest for
        
    Returns:
        Dict with result information
    """
    
    # Get brand to verify it exists and get profile_id
    brand = await crud.get_brand(brand_id)
    if not brand:
        raise ValueError(f"Brand with ID {brand_id} not found")
    
    # Get webhook URL from integration_configs
    webhook_config = await crud.get_webhook_config_by_profile(brand["profile_id"])
    if not webhook_config or not webhook_config.get("webhook_url"):
        raise ValueError(f"No webhook configuration found for brand {brand_id}")
    
    # Get all unsent mentions for this brand
    unsent_mentions = await crud.get_unsent_mentions_by_brand(brand_id)
    
    if not unsent_mentions:
        return {
            "success": True,
            "message": "No new mentions to send",
            "mentions_sent": 0
        }
    
    # Group mentions by topic
    mentions_by_topic = defaultdict(list)
    for mention in unsent_mentions:
        topic_name = mention.get("topics", {}).get("name", "Uncategorized") if mention.get("topics") else "Uncategorized"
        mentions_by_topic[topic_name].append(mention)
    
    # Format the Slack message
    message_blocks = []
    total_mentions = len(unsent_mentions)
    
    # Header
    message_blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🔔 *New Media Mentions for {brand['name']}*\n_{total_mentions} new mentions found_"
        }
    })
    
    message_blocks.append({"type": "divider"})
    
    # Group mentions by topic
    for topic_name, mentions in mentions_by_topic.items():
        # Topic header
        message_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📂 {topic_name}* ({len(mentions)} mentions)"
            }
        })
        
        # List mentions under this topic
        mention_text = ""
        for mention in mentions:
            platform = mention.get("platforms", {}).get("name", "Unknown") if mention.get("platforms") else "Unknown"
            title = mention.get("caption", "No title")
            link = mention.get("post_link", "")
            
            if link:
                mention_text += f"• <{link}|{title}> ({platform})\n"
            else:
                mention_text += f"• {title} ({platform})\n"
        
        if mention_text:
            message_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": mention_text.strip()
                }
            })
        
        message_blocks.append({"type": "divider"})
    
    # Footer
    message_blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "🤖 Automated digest from TrackAnything"
            }
        ]
    })
    
    # Prepare Slack message
    slack_message = {
        "blocks": message_blocks
    }
    
    try:
        # Send to webhook
        response = requests.post(
            webhook_config["webhook_url"],
            json=slack_message,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            # Mark mentions as sent
            mention_ids = [mention["id"] for mention in unsent_mentions]
            await crud.mark_mentions_as_sent(mention_ids)
            
            return {
                "success": True,
                "message": f"Digest sent successfully for {brand['name']}",
                "mentions_sent": total_mentions,
                "mentions_updated": len(mention_ids),
                "webhook_url": webhook_config["webhook_url"]
            }
        else:
            return {
                "success": False,
                "message": f"Failed to send digest. Webhook returned status: {response.status_code}",
                "mentions_sent": 0,
                "webhook_url": webhook_config["webhook_url"]
            }
            
    except requests.RequestException as e:
        return {
            "success": False,
            "message": f"Failed to send digest: {str(e)}",
            "mentions_sent": 0,
            "webhook_url": webhook_config["webhook_url"]
        }