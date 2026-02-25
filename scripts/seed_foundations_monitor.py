#!/usr/bin/env python3
"""
Seed "Fonde Monitor" brand for a profile email (default: madsrunge@hotmail.dk).

Dækker danske og norske fondsomtaler for en potentiel kunde i fondssektoren.

What it does:
1) Finds profile by contact_email/email
2) Creates or reuses the brand (with allowed_languages=["da","no"])
3) Creates or updates topics
4) Creates missing keywords and links them to topics (idempotent)

Usage:
  python scripts/seed_foundations_monitor.py
  python scripts/seed_foundations_monitor.py --email kunde@example.dk
  python scripts/seed_foundations_monitor.py --brand-name "Fonde Monitor" --frequency-hours 8
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Ensure `app` imports work when script is run as `python scripts/...`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.supabase_client import get_supabase_admin


@dataclass(frozen=True)
class TopicSeed:
    name: str
    keywords: List[str]


TOPICS: List[TopicSeed] = [
    TopicSeed(
        name="Store danske fonde",
        keywords=[
            "Novo Nordisk Fonden",
            "A P Møller Fonden",
            "Lundbeckfonden",
            "Lego Fonden",
            "Skovsgaards Fond",
            "Direktør K. W. Bruuns Fond",
            "Gl. Holtegaard",
        ],
    ),
    TopicSeed(
        name="Fondsbranchens organisationer",
        keywords=[
            "Fondenes Videnscenter",
            "Danske Fonde",
            "Philea",
        ],
    ),
    TopicSeed(
        name="Regulering & lovgivning",
        keywords=[
            "Fondslov",
            "Fondstilsyn",
            "Fondsmyndighed",
            "Fondsret",
        ],
    ),
    TopicSeed(
        name="Uddeling & filantropi",
        keywords=[
            "Filantropi",
            "Uddelinger",
            "Donationer",
            "Fondsmidler",
            "Bevillinger",
        ],
    ),
    TopicSeed(
        name="Fondsledelse",
        keywords=[
            "Fondsdirektør",
            "Fondsbestyrelse",
        ],
    ),
]

ALLOWED_LANGUAGES = ["da", "no"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def find_profile_by_email(admin, email: str) -> Dict:
    email_norm = normalize_email(email)
    profiles = admin.table("profiles").select("id,contact_email,email").execute().data or []
    for profile in profiles:
        contact_email = normalize_email(profile.get("contact_email", ""))
        fallback_email = normalize_email(profile.get("email", ""))
        if contact_email == email_norm or fallback_email == email_norm:
            return profile
    raise RuntimeError(f"No profile found for email '{email}'.")


def find_or_create_brand(
    admin,
    profile_id: str,
    brand_name: str,
    description: str,
    frequency_hours: int,
    lookback_days: int,
    allowed_languages: List[str],
) -> Dict:
    existing = (
        admin.table("brands")
        .select("id,name,profile_id")
        .eq("profile_id", profile_id)
        .eq("name", brand_name)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if existing.data:
        brand = existing.data[0]
        admin.table("brands").update(
            {
                "description": description,
                "scrape_frequency_hours": frequency_hours,
                "initial_lookback_days": lookback_days,
                "is_active": True,
                "allowed_languages": allowed_languages,
            }
        ).eq("id", brand["id"]).execute()
        refreshed = (
            admin.table("brands")
            .select("id,name,profile_id,scrape_frequency_hours,initial_lookback_days,allowed_languages")
            .eq("id", brand["id"])
            .limit(1)
            .execute()
        )
        return refreshed.data[0]

    created = (
        admin.table("brands")
        .insert(
            {
                "profile_id": profile_id,
                "name": brand_name,
                "description": description or None,
                "scrape_frequency_hours": frequency_hours,
                "initial_lookback_days": lookback_days,
                "is_active": True,
                "allowed_languages": allowed_languages,
                "created_at": now_iso(),
            }
        )
        .execute()
    )
    if not created.data:
        raise RuntimeError("Failed to create brand.")
    return created.data[0]


def find_or_create_keyword(admin, text: str) -> int:
    existing = (
        admin.table("keywords")
        .select("id")
        .eq("text", text)
        .limit(1)
        .execute()
    )
    if existing.data:
        return int(existing.data[0]["id"])

    created = (
        admin.table("keywords")
        .insert({"text": text, "created_at": now_iso()})
        .execute()
    )
    if not created.data:
        raise RuntimeError(f"Failed creating keyword '{text}'.")
    return int(created.data[0]["id"])


def find_or_create_topic(admin, brand_id: int, topic_name: str) -> int:
    existing = (
        admin.table("topics")
        .select("id")
        .eq("brand_id", brand_id)
        .eq("name", topic_name)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if existing.data:
        topic_id = int(existing.data[0]["id"])
        admin.table("topics").update(
            {
                "query_template": "{{keyword}}",
                "is_active": True,
            }
        ).eq("id", topic_id).execute()
        return topic_id

    created = (
        admin.table("topics")
        .insert(
            {
                "brand_id": brand_id,
                "name": topic_name,
                "query_template": "{{keyword}}",
                "is_active": True,
                "created_at": now_iso(),
            }
        )
        .execute()
    )
    if not created.data:
        raise RuntimeError(f"Failed creating topic '{topic_name}'.")
    return int(created.data[0]["id"])


def link_topic_keyword(admin, topic_id: int, keyword_id: int) -> None:
    admin.table("topic_keywords").upsert(
        {"topic_id": topic_id, "keyword_id": keyword_id},
        on_conflict="topic_id,keyword_id",
    ).execute()


def seed_foundations(
    email: str,
    brand_name: str,
    frequency_hours: int,
    lookback_days: int,
    description: Optional[str] = None,
) -> None:
    admin = get_supabase_admin()
    profile = find_profile_by_email(admin, email)
    profile_id = str(profile["id"])
    description_value = description or "Overvågning af danske og norske fonde, uddelinger og fondspolitik"

    print(f"Profile: {email} (id={profile_id})")
    brand = find_or_create_brand(
        admin=admin,
        profile_id=profile_id,
        brand_name=brand_name,
        description=description_value,
        frequency_hours=frequency_hours,
        lookback_days=lookback_days,
        allowed_languages=ALLOWED_LANGUAGES,
    )
    brand_id = int(brand["id"])
    print(f"Brand ready: {brand['name']} (id={brand_id}, allowed_languages={brand.get('allowed_languages')})")

    topic_count = 0
    keyword_links = 0
    for seed in TOPICS:
        topic_id = find_or_create_topic(admin, brand_id=brand_id, topic_name=seed.name)
        print(f"  Topic: {seed.name} (id={topic_id})")
        topic_count += 1

        for keyword_text in seed.keywords:
            keyword_id = find_or_create_keyword(admin, keyword_text)
            link_topic_keyword(admin, topic_id=topic_id, keyword_id=keyword_id)
            keyword_links += 1
            print(f"    Keyword linked: {keyword_text} (id={keyword_id})")

    print("")
    print("Seed complete.")
    print(f"Brand ID: {brand_id}")
    print(f"Topics processed: {topic_count}")
    print(f"Topic-keyword links processed: {keyword_links}")
    print(f"Language filter: {ALLOWED_LANGUAGES}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed foundations monitor brand/topics/keywords")
    parser.add_argument(
        "--email",
        default="madsrunge@hotmail.dk",
        help="Profile email in profiles.contact_email or profiles.email",
    )
    parser.add_argument(
        "--brand-name",
        default="Fonde Monitor",
        help="Brand name to create or update",
    )
    parser.add_argument(
        "--frequency-hours",
        type=int,
        default=8,
        help="Scrape frequency in hours",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Initial lookback days for first scrape",
    )
    parser.add_argument(
        "--description",
        default="",
        help="Optional brand description",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_foundations(
        email=args.email,
        brand_name=args.brand_name,
        frequency_hours=max(1, int(args.frequency_hours)),
        lookback_days=max(1, int(args.lookback_days)),
        description=args.description or None,
    )


if __name__ == "__main__":
    main()
