from datetime import datetime, timedelta, timezone
import logging
from time import perf_counter
from typing import Dict, List, Optional
import requests
from collections import defaultdict
from openai import AsyncOpenAI
from app.crud.supabase_crud import SupabaseCRUD
from app.core.config import settings

logger = logging.getLogger(__name__)


def _parse_datetime(value: Optional[object]) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_latest_digest_window(brand: Dict) -> tuple[datetime, datetime]:
    """
    Infer the latest scrape window from brand scheduling fields.

    There is currently no persisted scrape_runs table, so the latest cron run is
    approximated as [last_scraped_at - scrape_frequency_hours, last_scraped_at].
    """
    window_end = _parse_datetime(brand.get("last_scraped_at")) or datetime.now(timezone.utc)
    frequency_hours = int(brand.get("scrape_frequency_hours") or 24)
    window_start = window_end - timedelta(hours=max(1, frequency_hours))
    return window_start, window_end


def get_mention_batch_window(created_at: object) -> tuple[datetime, datetime]:
    """Group mentions saved together into minute-sized batches."""
    parsed = _parse_datetime(created_at) or datetime.now(timezone.utc)
    window_start = parsed.replace(second=0, microsecond=0)
    window_end = window_start + timedelta(minutes=1)
    return window_start, window_end


async def _resolve_mention_ids_for_window(
    crud: SupabaseCRUD,
    brand_id: int,
    window_start: datetime,
) -> List[int]:
    """Resolve mention IDs for the same minute batch shown by the jobs endpoint."""
    rows = await crud.get_recent_mention_batch_timestamps(brand_id=brand_id, limit=1000)
    target_start = window_start.astimezone(timezone.utc).replace(second=0, microsecond=0)
    mention_ids: List[int] = []
    for row in rows:
        row_start, _ = get_mention_batch_window(row.get("created_at"))
        if row_start == target_start:
            mention_ids.append(int(row["id"]))
    return mention_ids


def _format_mention_for_prompt(mention: Dict, index: int) -> str:
    topic = mention.get("topics") or {}
    platform = mention.get("platforms") or {}
    title = mention.get("caption") or "Uden titel"
    teaser = mention.get("content_teaser") or ""
    published_at = mention.get("published_at") or "ukendt dato"
    link = mention.get("post_link") or ""
    topic_name = topic.get("name") or "Ukategoriseret"
    platform_name = platform.get("name") or "Ukendt kilde"

    return (
        f"{index}. Titel: {title}\n"
        f"   Kilde: {platform_name}\n"
        f"   Emne: {topic_name}\n"
        f"   Publiceret: {published_at}\n"
        f"   Link: {link}\n"
        f"   Uddrag: {teaser[:700]}"
    )


async def generate_digest_text_supabase(
    crud: SupabaseCRUD,
    brand_id: int,
    user_id,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
    mention_ids: Optional[List[int]] = None,
    save_report: bool = True,
) -> Dict:
    """Generate a mail-ready digest text for the latest scrape window."""
    started_at = perf_counter()
    brand = await crud.get_brand(brand_id)
    if not brand:
        raise ValueError(f"Brand with ID {brand_id} not found")

    profile = await crud.get_profile(user_id)
    is_admin = profile and profile.get("role") == "admin"
    if brand.get("profile_id") != str(user_id) and not is_admin:
        raise PermissionError("Brand not found")

    inferred_start, inferred_end = get_latest_digest_window(brand)
    effective_start = window_start or inferred_start
    effective_end = window_end or inferred_end

    resolved_mention_ids = mention_ids or []
    if not resolved_mention_ids and window_start:
        resolved_mention_ids = await _resolve_mention_ids_for_window(
            crud=crud,
            brand_id=brand_id,
            window_start=effective_start,
        )

    if resolved_mention_ids:
        mentions = await crud.get_mentions_by_ids_for_digest(
            brand_id=brand_id,
            mention_ids=resolved_mention_ids,
            limit=120,
        )
    else:
        mentions = await crud.get_mentions_for_digest_window(
            brand_id=brand_id,
            window_start=effective_start,
            window_end=effective_end,
            limit=120,
        )

    if not mentions and window_start:
        fallback_ids = await _resolve_mention_ids_for_window(
            crud=crud,
            brand_id=brand_id,
            window_start=effective_start,
        )
        if fallback_ids:
            mentions = await crud.get_mentions_by_ids_for_digest(
                brand_id=brand_id,
                mention_ids=fallback_ids,
                limit=120,
            )
    logger.info(
        "Digest generation fetched mentions | brand_id=%s | requested_ids=%s | mention_count=%s | elapsed=%.2fs",
        brand_id,
        len(resolved_mention_ids),
        len(mentions),
        perf_counter() - started_at,
    )

    if not mentions:
        return {
            "success": True,
            "message": "No mentions found for digest window",
            "brand_id": brand_id,
            "brand_name": brand.get("name", "Unknown"),
            "window_start": effective_start.isoformat(),
            "window_end": effective_end.isoformat(),
            "mention_count": 0,
            "digest_text": "",
            "report_id": None,
        }

    mention_block = "\n\n".join(
        _format_mention_for_prompt(mention, index)
        for index, mention in enumerate(mentions, start=1)
    )

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key.get_secret_value(),
        base_url="https://api.deepseek.com",
    )

    system_prompt = """Du skriver korte, professionelle mail-digests til kunder baseret på medieomtaler.
Skriv på dansk. Output skal kunne indsættes direkte i en email.
Struktur:
1. Kort emnelinje
2. Executive summary på 4-6 linjer
3. Vigtigste tendenser i bullets
4. Udvalgte omtaler med titel, kilde og link
5. Anbefalet næste skridt
Vær konkret, undgå hallucinationer, og brug kun de omtaler der er givet."""

    user_prompt = (
        f"Brand/kunde: {brand.get('name')}\n"
        f"Periode: {effective_start.isoformat()} til {effective_end.isoformat()}\n"
        f"Antal omtaler: {len(mentions)}\n\n"
        f"Omtaler:\n{mention_block}"
    )

    response = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1100,
    )
    digest_text = (response.choices[0].message.content or "").strip()
    logger.info(
        "Digest generation completed DeepSeek call | brand_id=%s | chars=%s | elapsed=%.2fs",
        brand_id,
        len(digest_text),
        perf_counter() - started_at,
    )

    report = None
    if save_report and digest_text:
        title = f"Digest: {brand.get('name')} ({effective_end.date().isoformat()})"
        report = await crud.create_report(
            user_id=user_id,
            title=title,
            content=digest_text,
            report_type="summary",
            brand_id=brand_id,
        )
        logger.info(
            "Digest generation saved report | brand_id=%s | report_id=%s | elapsed=%.2fs",
            brand_id,
            report.get("id") if report else None,
            perf_counter() - started_at,
        )

    return {
        "success": True,
        "message": f"Digest generated for {brand.get('name')}",
        "brand_id": brand_id,
        "brand_name": brand.get("name", "Unknown"),
        "window_start": effective_start.isoformat(),
        "window_end": effective_end.isoformat(),
        "mention_count": len(mentions),
        "digest_text": digest_text,
        "report_id": report.get("id") if report else None,
    }

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
