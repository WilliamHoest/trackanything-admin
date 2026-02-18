#!/usr/bin/env python3
"""
Reset scraping test state.

What it does:
1) Deletes mention-keyword links
2) Deletes mentions
3) Resets brand scrape state so next run is treated as "first scrape"

Default scope is all brands. You can limit to one profile with --profile-id.

Examples:
  cd trackanything-admin
  python scripts/reset_scraping_test_state.py --dry-run
  python scripts/reset_scraping_test_state.py --confirm
  python scripts/reset_scraping_test_state.py --profile-id <uuid> --confirm
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Iterable, List

# Ensure `app` imports work when script is run as `python scripts/...`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.supabase_client import get_supabase_admin


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_brand_ids(admin, profile_id: str | None) -> List[int]:
    query = admin.table("brands").select("id")
    if profile_id:
        query = query.eq("profile_id", profile_id)
    result = query.execute()
    return [int(row["id"]) for row in (result.data or [])]


def _chunked(values: List[int], size: int = 500) -> Iterable[List[int]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _count_mention_keywords(admin, mention_ids: List[int]) -> int:
    if not mention_ids:
        return 0
    result = (
        admin.table("mention_keywords")
        .select("mention_id", count="exact")
        .in_("mention_id", mention_ids)
        .execute()
    )
    return int(result.count or 0)


def _fetch_mention_ids(admin, brand_ids: List[int]) -> List[int]:
    if not brand_ids:
        return []
    result = (
        admin.table("mentions")
        .select("id")
        .in_("brand_id", brand_ids)
        .execute()
    )
    return [int(row["id"]) for row in (result.data or [])]


def _reset_brands(admin, profile_id: str | None) -> int:
    payload = {
        "last_scraped_at": None,
        "scrape_in_progress": False,
        "scrape_started_at": None,
    }

    query = admin.table("brands").update(payload)
    if profile_id:
        query = query.eq("profile_id", profile_id)
    result = query.neq("id", 0).execute()
    return len(result.data or [])


def _delete_mention_keywords(admin, mention_ids: List[int]) -> int:
    if not mention_ids:
        return 0
    deleted_chunks = 0
    for chunk in _chunked(mention_ids):
        admin.table("mention_keywords").delete().in_("mention_id", chunk).execute()
        deleted_chunks += 1
    return deleted_chunks


def _delete_mentions(admin, brand_ids: List[int]) -> int:
    if not brand_ids:
        return 0
    deleted = 0
    for chunk in _chunked(brand_ids):
        result = (
            admin.table("mentions")
            .select("id")
            .in_("brand_id", chunk)
            .execute()
        )
        mention_ids = [int(row["id"]) for row in (result.data or [])]
        if mention_ids:
            admin.table("mentions").delete().in_("id", mention_ids).execute()
            deleted += len(mention_ids)
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset scraping test state")
    parser.add_argument(
        "--profile-id",
        help="Optional: limit reset to one profile UUID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without deleting/updating",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually perform deletion/reset",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        parser.error("Use either --dry-run or --confirm.")

    admin = get_supabase_admin()
    started = _now_iso()

    print(f"Started: {started}")
    if args.profile_id:
        print(f"Scope: profile_id={args.profile_id}")
    else:
        print("Scope: ALL profiles/brands")

    brand_ids = _fetch_brand_ids(admin, args.profile_id)
    mention_ids = _fetch_mention_ids(admin, brand_ids)
    mention_count = len(mention_ids)
    mention_keyword_count = _count_mention_keywords(admin, mention_ids)

    print(f"Brands in scope: {len(brand_ids)}")
    print(f"Mentions in scope: {mention_count}")
    print(f"Mention keywords in scope: {mention_keyword_count}")

    if args.dry_run:
        print("Dry run complete. No changes made.")
        return

    if not brand_ids:
        print("Nothing to reset. No brands found in scope.")
        return

    print("Deleting mention_keywords...")
    mk_chunks = _delete_mention_keywords(admin, mention_ids)
    print(
        "Deleted mention_keywords rows (expected): "
        f"{mention_keyword_count} across {mk_chunks} chunk(s)"
    )

    print("Deleting mentions...")
    deleted_mentions = _delete_mentions(admin, brand_ids)
    print(f"Deleted mentions rows: {deleted_mentions}")

    print("Resetting brand scrape state...")
    try:
        updated_brands = _reset_brands(admin, args.profile_id)
        print(f"Reset brands: {updated_brands}")
    except Exception as e:
        # Backward-compatible if lock columns are missing.
        message = str(e).lower()
        if "scrape_in_progress" in message or "scrape_started_at" in message:
            payload = {"last_scraped_at": None}
            query = admin.table("brands").update(payload)
            if args.profile_id:
                query = query.eq("profile_id", args.profile_id)
            result = query.neq("id", 0).execute()
            updated_brands = len(result.data or [])
            print(
                "Lock columns missing; reset only last_scraped_at. "
                f"Updated brands: {updated_brands}"
            )
        else:
            raise

    print("Done.")


if __name__ == "__main__":
    main()
