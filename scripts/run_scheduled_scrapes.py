#!/usr/bin/env python3
"""
Scheduled scraping script for TrackAnything.

This script is designed to run from cron (for example Railway cron jobs).
It fetches active brands, evaluates which are due based on scrape_frequency_hours,
and processes each due brand through the shared scraping pipeline.
"""

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Add parent directory to path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure environment variables are loaded
load_dotenv()

from app.core.supabase_client import get_supabase_admin
from app.crud.supabase_crud import SupabaseCRUD
from app.services.scraping.pipeline import BrandScrapeResult, process_brand_scrape


def setup_cron_logging() -> logging.Logger:
    """Configure logging for cron jobs (stdout only)."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger(__name__)


logger = setup_cron_logging()


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


def _brand_due_for_scrape(brand: Dict, now: datetime) -> bool:
    brand_name = brand.get("name", "unknown")
    scrape_frequency_hours = int(brand.get("scrape_frequency_hours") or 24)
    last_scraped_at = _parse_datetime(brand.get("last_scraped_at"))

    if not last_scraped_at:
        logger.info("'%s': never scraped before, scheduling now", brand_name)
        return True

    hours_since = (now - last_scraped_at).total_seconds() / 3600
    if hours_since >= scrape_frequency_hours:
        logger.info(
            "'%s': due for scrape (%.1fh since last, frequency=%sh)",
            brand_name,
            hours_since,
            scrape_frequency_hours,
        )
        return True

    logger.info(
        "'%s': not due yet (%.1fh/%sh)",
        brand_name,
        hours_since,
        scrape_frequency_hours,
    )
    return False


async def _scrape_due_brands(brands_to_scrape: List[Dict], crud: SupabaseCRUD) -> List[BrandScrapeResult]:
    results: List[BrandScrapeResult] = []

    for brand in brands_to_scrape:
        brand_id = int(brand["id"])
        run_id = f"cron-b{brand_id}-{uuid.uuid4().hex[:8]}"
        result = await process_brand_scrape(
            brand_id=brand_id,
            crud=crud,
            scrape_run_id=run_id,
            apply_relevance_filter=True,
            acquire_lock=True,
        )
        results.append(result)

        logger.info(
            "Brand '%s' finished with status=%s, mentions_found=%s, mentions_saved=%s",
            result.brand_name,
            result.status,
            result.mentions_found,
            result.mentions_saved,
        )
        if result.errors:
            logger.warning("Brand '%s' reported errors: %s", result.brand_name, result.errors)

    return results


async def main() -> None:
    logger.info("#" * 60)
    logger.info("# TrackAnything - Scheduled Scraper")
    logger.info("# Started at: %s", datetime.now(timezone.utc).isoformat())
    logger.info("#" * 60)

    try:
        admin_client = get_supabase_admin()
        crud = SupabaseCRUD(supabase_client=admin_client)
        logger.info("Connected to Supabase")

        brands = await crud.get_active_brands_for_scheduling()
        if not brands:
            logger.warning("No active brands found. Exiting.")
            return

        logger.info("Found %s active brand(s)", len(brands))

        now = datetime.now(timezone.utc)
        brands_to_scrape = [brand for brand in brands if _brand_due_for_scrape(brand, now)]

        if not brands_to_scrape:
            logger.info("No brands are due for scraping at this time.")
            return

        logger.info("Scraping %s brand(s)", len(brands_to_scrape))
        results = await _scrape_due_brands(brands_to_scrape, crud)

        successful = sum(1 for result in results if result.success)
        failed = sum(1 for result in results if result.status == "error")
        total_mentions_saved = sum(result.mentions_saved for result in results)

        logger.info("=" * 60)
        logger.info("FINAL SUMMARY")
        logger.info("=" * 60)
        logger.info("Successful: %s/%s", successful, len(results))
        logger.info("Failed: %s/%s", failed, len(results))
        logger.info("Total new mentions saved: %s", total_mentions_saved)

        if failed > 0:
            logger.warning("Failed brands:")
            for result in results:
                if result.status == "error":
                    logger.error("  %s: %s", result.brand_name, result.errors)

        logger.info("=" * 60)
        logger.info("Scraping complete at %s", datetime.now(timezone.utc).isoformat())
        logger.info("=" * 60)

        if failed > 0:
            sys.exit(1)

    except Exception as exc:
        logger.critical("FATAL ERROR: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
