import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Dict, List, Optional, Tuple

from dateutil import parser as dateparser

from app.core.config import settings
from app.crud.supabase_crud import SupabaseCRUD
from app.services.scraping.core.deduplication import filter_mentions_against_historical
from app.services.scraping.core.metrics import observe_duplicates_removed, observe_scrape_run
from app.services.scraping.core.text_processing import sanitize_search_input
from app.services.scraping.orchestrator import fetch_and_filter_mentions

scraping_logger = logging.getLogger("scraping")


@dataclass
class BrandScrapeResult:
    message: str
    brand_id: int
    brand_name: str
    status: str
    keywords_used: List[str] = field(default_factory=list)
    mentions_found: int = 0
    mentions_saved: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status not in {"error", "not_found"}


def _log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    scraping_logger.log(level, "%s%s", prefix, message)


def build_search_query(topic: Dict, keyword_text: str, brand_name: str) -> str:
    topic_value = sanitize_search_input(topic.get("name", ""))
    keyword_value = sanitize_search_input(keyword_text)
    brand_value = sanitize_search_input(brand_name)

    template = topic.get("query_template")
    if template:
        return (
            template
            .replace("{{topic}}", topic_value)
            .replace("{{keyword}}", keyword_value)
            .replace("{{brand}}", brand_value)
            .strip()
        )
    return f"{topic_value} {keyword_value}".strip()


def score_topic_match(topic_keywords: List[Dict], title: str, teaser: str) -> Tuple[int, List[Dict]]:
    matches = []
    score = 0

    for keyword in topic_keywords:
        keyword_text = keyword.get("text", "").lower()
        if not keyword_text:
            continue

        in_title = keyword_text in title
        in_teaser = keyword_text in teaser
        if not (in_title or in_teaser):
            continue

        matched_in = "both" if in_title and in_teaser else "title" if in_title else "teaser"
        keyword_score = (2 if in_title else 0) + (1 if in_teaser else 0)
        if len(keyword_text) >= 8:
            keyword_score += 1

        matches.append(
            {
                "keyword": keyword,
                "matched_in": matched_in,
                "score": keyword_score,
            }
        )
        score += keyword_score

    return score, matches


def _normalize_last_scraped_at(last_scraped_at: object) -> Optional[datetime]:
    if isinstance(last_scraped_at, datetime):
        parsed = last_scraped_at
    elif isinstance(last_scraped_at, str):
        parsed = dateparser.parse(last_scraped_at)
    else:
        return None

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_published_datetime(mention: Dict) -> Optional[datetime]:
    published_parsed = mention.get("published_parsed")
    if published_parsed:
        try:
            if isinstance(published_parsed, (list, tuple)) and len(published_parsed) >= 6:
                return datetime(*published_parsed[:6], tzinfo=timezone.utc)
            return datetime(
                published_parsed.tm_year,
                published_parsed.tm_mon,
                published_parsed.tm_mday,
                published_parsed.tm_hour,
                published_parsed.tm_min,
                published_parsed.tm_sec,
                tzinfo=timezone.utc,
            )
        except Exception:
            return None

    published_at = mention.get("published_at")
    if isinstance(published_at, str):
        try:
            parsed = dateparser.parse(published_at)
            if parsed is None:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    return None


async def process_brand_scrape(
    brand_id: int,
    crud: SupabaseCRUD,
    scrape_run_id: Optional[str] = None,
    apply_relevance_filter: bool = True,
    acquire_lock: bool = True,
) -> BrandScrapeResult:
    scrape_run_id = scrape_run_id or f"b{brand_id}-{uuid.uuid4().hex[:8]}"
    run_started_at = datetime.now(timezone.utc)
    run_started_perf = perf_counter()
    run_status = "error"
    lock_acquired = False

    brand = await crud.get_brand(brand_id)
    if not brand:
        run_status = "not_found"
        observe_scrape_run(scope="brand", status=run_status, duration_seconds=perf_counter() - run_started_perf)
        return BrandScrapeResult(
            message=f"Brand {brand_id} not found",
            brand_id=brand_id,
            brand_name=f"brand-{brand_id}",
            status=run_status,
            errors=["Brand not found"],
        )

    brand_name = brand.get("name", f"brand-{brand_id}")
    errors: List[str] = []

    try:
        if acquire_lock:
            lock_acquired = await crud.try_acquire_brand_scrape_lock(brand_id)
            if not lock_acquired:
                run_status = "locked"
                return BrandScrapeResult(
                    message=f"Scrape already in progress for brand '{brand_name}'",
                    brand_id=brand_id,
                    brand_name=brand_name,
                    status=run_status,
                    errors=["Another scrape run is active for this brand"],
                )

        _log(scrape_run_id, f"Starting scrape for brand '{brand_name}' ({brand_id})")
        topics = await crud.get_topics_by_brand(brand_id)
        active_topics = [topic for topic in topics if topic.get("is_active", True)]

        if not active_topics:
            run_status = "no_topics"
            return BrandScrapeResult(
                message=f"No active topics found for brand '{brand_name}'",
                brand_id=brand_id,
                brand_name=brand_name,
                status=run_status,
                errors=["No active topics found for this brand"],
            )

        search_queries = set()
        topic_keywords_cache: Dict[int, List[Dict]] = {}
        for topic in active_topics:
            topic_keywords = topic.get("keywords", []) or []
            topic_keywords_cache[topic["id"]] = topic_keywords

            for keyword in topic_keywords:
                query = build_search_query(topic, keyword.get("text", ""), brand_name)
                if query:
                    search_queries.add(query)

        query_list = list(search_queries)
        if not query_list:
            run_status = "no_keywords"
            return BrandScrapeResult(
                message=f"No keywords found for brand '{brand_name}'",
                brand_id=brand_id,
                brand_name=brand_name,
                status=run_status,
                errors=["No keywords configured for this brand"],
            )

        last_scraped_at = _normalize_last_scraped_at(brand.get("last_scraped_at"))
        if last_scraped_at:
            from_date = last_scraped_at
            _log(scrape_run_id, f"Subsequent scrape - using last_scraped_at: {from_date.isoformat()}")
        else:
            lookback_days = int(brand.get("initial_lookback_days", 1) or 1)
            from_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
            _log(scrape_run_id, f"First scrape - looking back {lookback_days} day(s) to {from_date.isoformat()}")

        mentions = await fetch_and_filter_mentions(
            query_list,
            apply_relevance_filter=apply_relevance_filter,
            from_date=from_date,
            scrape_run_id=scrape_run_id,
        )

        if settings.scraping_historical_dedup_enabled and mentions:
            historical_days = max(1, int(settings.scraping_historical_dedup_days))
            historical_limit = max(1, int(settings.scraping_historical_dedup_limit))
            recent_mentions = await crud.get_recent_mentions_for_brand(
                brand_id=brand_id,
                days_back=historical_days,
                limit=historical_limit,
            )

            if recent_mentions:
                mentions, historical_duplicates_removed = filter_mentions_against_historical(
                    mentions,
                    recent_mentions,
                    threshold=settings.scraping_fuzzy_dedup_threshold,
                    day_window=settings.scraping_fuzzy_dedup_day_window,
                )
                observe_duplicates_removed(stage="historical_fuzzy", count=historical_duplicates_removed)
                if historical_duplicates_removed > 0:
                    _log(
                        scrape_run_id,
                        (
                            "Historical near-dedupe removed "
                            f"{historical_duplicates_removed} mentions for brand '{brand_name}'"
                        ),
                    )

        if not mentions:
            await crud.update_brand_last_scraped(brand_id, run_started_at)
            run_status = "no_mentions"
            return BrandScrapeResult(
                message=f"No mentions found for brand '{brand_name}'",
                brand_id=brand_id,
                brand_name=brand_name,
                status=run_status,
                keywords_used=query_list,
            )

        unique_platforms = {(m.get("platform") or "Unknown") for m in mentions}
        platform_cache: Dict[str, Dict] = {}
        for platform_name in unique_platforms:
            platform = await crud.get_platform_by_name(platform_name)
            if not platform:
                platform = await crud.create_platform(platform_name)
                if platform:
                    _log(scrape_run_id, f"Created platform '{platform_name}' with ID {platform['id']}")
                else:
                    _log(scrape_run_id, f"Failed to create platform '{platform_name}'", logging.ERROR)

            if platform:
                platform_cache[platform_name] = platform

        mentions_to_insert = []
        mention_keyword_matches: Dict[Tuple[str, int], List[Dict]] = {}

        for mention in mentions:
            try:
                published_date = _extract_published_datetime(mention)
                platform_name = mention.get("platform") or "Unknown"
                platform = platform_cache.get(platform_name)
                if not platform:
                    errors.append(f"Platform not found for mention: {mention.get('title', 'Unknown')}")
                    continue

                best_topic = None
                best_topic_score = -1
                best_topic_matches: List[Dict] = []
                title = (mention.get("title") or "").lower()
                teaser = (mention.get("content_teaser") or "").lower()

                for topic in active_topics:
                    topic_keywords = topic_keywords_cache.get(topic["id"], [])
                    topic_score, topic_matches = score_topic_match(topic_keywords, title, teaser)
                    if topic_score > best_topic_score:
                        best_topic_score = topic_score
                        best_topic = topic
                        best_topic_matches = topic_matches

                if not best_topic:
                    best_topic = active_topics[0]
                    best_topic_matches = []

                primary_keyword_id = None
                if best_topic_matches:
                    best_match = sorted(
                        best_topic_matches,
                        key=lambda match: (match["score"], len(match["keyword"].get("text", ""))),
                        reverse=True,
                    )[0]
                    primary_keyword_id = best_match["keyword"].get("id")

                mention_data = {
                    "caption": mention.get("title", ""),
                    "post_link": mention.get("link", ""),
                    "published_at": published_date.isoformat() if published_date else None,
                    "content_teaser": mention.get("content_teaser"),
                    "platform_id": platform["id"],
                    "brand_id": brand_id,
                    "topic_id": best_topic["id"],
                    "primary_keyword_id": primary_keyword_id,
                    "read_status": False,
                    "notified_status": False,
                }
                mentions_to_insert.append(mention_data)

                if best_topic_matches and mention_data["post_link"]:
                    mention_key = (mention_data["post_link"], mention_data["topic_id"])
                    mention_keyword_matches[mention_key] = [
                        {
                            "keyword_id": match["keyword"]["id"],
                            "matched_in": match["matched_in"],
                            "score": match["score"],
                        }
                        for match in best_topic_matches
                    ]

            except Exception as exc:
                error_msg = f"Error preparing mention '{mention.get('title', 'Unknown')}': {exc}"
                errors.append(error_msg)
                _log(scrape_run_id, error_msg, logging.ERROR)

        mentions_saved = 0
        if mentions_to_insert:
            mentions_saved, batch_errors = await crud.batch_create_mentions(mentions_to_insert)
            errors.extend(batch_errors)
            _log(scrape_run_id, f"Batch saved {mentions_saved} mentions for '{brand_name}'")

        if mention_keyword_matches:
            mention_id_map = await crud.get_mentions_by_keys(brand_id, list(mention_keyword_matches.keys()))
            mention_keyword_rows = []
            for mention_key, matches in mention_keyword_matches.items():
                mention_id = mention_id_map.get(mention_key)
                if not mention_id:
                    continue
                for match in matches:
                    mention_keyword_rows.append(
                        {
                            "mention_id": mention_id,
                            **match,
                        }
                    )

            if mention_keyword_rows:
                match_errors = await crud.batch_create_mention_keywords(mention_keyword_rows)
                errors.extend(match_errors)

        await crud.update_brand_last_scraped(brand_id, run_started_at)
        run_status = "success"
        return BrandScrapeResult(
            message=f"Scraping completed for brand '{brand_name}'",
            brand_id=brand_id,
            brand_name=brand_name,
            status=run_status,
            keywords_used=query_list,
            mentions_found=len(mentions),
            mentions_saved=mentions_saved,
            errors=errors,
        )

    except Exception as exc:
        run_status = "error"
        _log(scrape_run_id, f"Critical scrape error for brand '{brand_name}': {exc}", logging.ERROR)
        return BrandScrapeResult(
            message=f"Scraping failed for brand '{brand_name}'",
            brand_id=brand_id,
            brand_name=brand_name,
            status=run_status,
            errors=[f"Critical error: {exc}"],
        )
    finally:
        observe_scrape_run(
            scope="brand",
            status=run_status,
            duration_seconds=perf_counter() - run_started_perf,
        )
        if acquire_lock and lock_acquired:
            released = await crud.release_brand_scrape_lock(brand_id)
            if not released:
                _log(scrape_run_id, f"Failed to release scrape lock for brand {brand_id}", logging.WARNING)
