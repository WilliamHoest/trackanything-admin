from sqlalchemy.orm import Session
from typing import Dict, List
import requests
from collections import defaultdict
from app.crud import crud
from app.models.models import Mention, Topic

def create_and_send_digest(db: Session, brand_id: int) -> Dict:
    """
    Creates and sends a digest of new mentions for a brand to its webhook
    
    Args:
        db: Database session
        brand_id: ID of the brand to send digest for
        
    Returns:
        Dict with result information
    """
    
    # Get brand to verify it exists and get profile_id
    brand = crud.get_brand(db, brand_id)
    if not brand:
        raise ValueError(f"Brand with ID {brand_id} not found")
    
    # Get webhook URL from integration_configs
    webhook_config = crud.get_webhook_config_by_profile(db, brand.profile_id)
    if not webhook_config or not webhook_config.webhook_url:
        raise ValueError(f"No webhook configuration found for brand {brand_id}")
    
    # Get all unsent mentions for this brand
    unsent_mentions = crud.get_unsent_mentions_by_brand(db, brand_id)
    
    if not unsent_mentions:
        return {
            "success": True,
            "message": "No new mentions to send",
            "mentions_sent": 0
        }
    
    # Group mentions by topic
    mentions_by_topic = defaultdict(list)
    for mention in unsent_mentions:
        topic_name = mention.topic.name if mention.topic else "Uncategorized"
        mentions_by_topic[topic_name].append(mention)
    
    # Format the Slack message
    message_blocks = []
    total_mentions = len(unsent_mentions)
    
    # Header
    message_blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🔔 *New Media Mentions for {brand.name}*\n_{total_mentions} new mentions found_"
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
            title = mention.caption[:100] + "..." if len(mention.caption) > 100 else mention.caption
            platform_name = mention.platform.name if mention.platform else "Unknown"
            mention_text += f"• <{mention.post_link}|{title}> ({platform_name})\n"
        
        message_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": mention_text
            }
        })
        
        message_blocks.append({"type": "divider"})
    
    # Prepare Slack payload
    slack_payload = {
        "blocks": message_blocks
    }
    
    try:
        # Send to webhook
        response = requests.post(
            webhook_config.webhook_url,
            json=slack_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        
        # Update notified status for all sent mentions
        mentions_updated = 0
        for mention in unsent_mentions:
            success = crud.update_mention_notified_status(db, mention.id, True)
            if success:
                mentions_updated += 1
        
        return {
            "success": True,
            "message": f"Digest sent successfully to webhook",
            "mentions_sent": total_mentions,
            "mentions_updated": mentions_updated,
            "webhook_url": webhook_config.webhook_url
        }
        
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to send webhook: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error during digest creation: {str(e)}")