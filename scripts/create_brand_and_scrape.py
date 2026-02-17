#!/usr/bin/env python3
"""
Create a brand with topics/keywords and immediately run scraping for it.

Usage examples:
  cd trackanything-admin

  # Fast path with hardcoded test data
  ./venv/bin/python scripts/create_brand_and_scrape.py \
    --preset usa_qa \
    --source-brand "USA" \
    --append-timestamp

  # Fully custom topics/keywords
  ./venv/bin/python scripts/create_brand_and_scrape.py \
    --source-brand "USA" \
    --brand-name "USA QA 2" \
    --lookback-days 30 \
    --topic "Donald Trump=Told,Grønland" \
    --topic "Elon Musk=Tesla,SpaceX"
"""

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

# Ensure `app` imports work when script is run as `python scripts/...`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@dataclass
class TopicSpec:
    name: str
    keywords: list[str]


@dataclass
class PresetSpec:
    brand_name: str
    description: str
    lookback_days: int
    frequency_hours: int
    topics: list[TopicSpec]


PRESETS: dict[str, PresetSpec] = {
    "usa_qa": PresetSpec(
        brand_name="USA QA Backend",
        description="Hardcoded backend test dataset for fast scraping checks",
        lookback_days=7,
        frequency_hours=24,
        topics=[
            TopicSpec(name="Donald Trump", keywords=["Told", "Grønland"]),
            TopicSpec(name="Elon Musk", keywords=["Tesla", "SpaceX"]),
        ],
    ),
    "energy_qa": PresetSpec(
        brand_name="Energy QA Backend",
        description="Hardcoded backend test dataset for energy-related scraping",
        lookback_days=30,
        frequency_hours=24,
        topics=[
            TopicSpec(name="Vindenergi", keywords=["havvind", "offshore wind"]),
            TopicSpec(name="Atomkraft", keywords=["atomkraft", "SMR"]),
        ],
    ),
}


def parse_topic_arg(raw: str) -> TopicSpec:
    if "=" not in raw:
        raise ValueError(
            f"Invalid --topic format: '{raw}'. Expected 'Topic Name=kw1,kw2'."
        )
    topic_name, keywords_str = raw.split("=", 1)
    topic_name = topic_name.strip()
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    if not topic_name:
        raise ValueError(f"Topic name is empty in '{raw}'.")
    if not keywords:
        raise ValueError(f"No keywords provided in '{raw}'.")
    return TopicSpec(name=topic_name, keywords=keywords)


def ensure_keyword(admin, keyword_text: str) -> int:
    existing = (
        admin.table("keywords")
        .select("id")
        .eq("text", keyword_text)
        .limit(1)
        .execute()
    )
    if existing.data:
        return int(existing.data[0]["id"])

    created = (
        admin.table("keywords")
        .insert(
            {
                "text": keyword_text,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .execute()
    )
    return int(created.data[0]["id"])


def get_profile_id_from_source_brand(admin, source_brand_name: str) -> str:
    result = (
        admin.table("brands")
        .select("id, profile_id, name, created_at")
        .eq("name", source_brand_name)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise RuntimeError(
            f"No brand found with name '{source_brand_name}'. "
            "Use an existing brand name with your own profile."
        )
    row = result.data[0]
    return str(row["profile_id"])


def build_topic_specs(args: argparse.Namespace) -> list[TopicSpec]:
    if args.topic:
        return [parse_topic_arg(t) for t in args.topic]

    if args.preset:
        return PRESETS[args.preset].topics

    raise ValueError(
        "No topics provided. Use --topic or choose --preset."
    )


def resolve_profile_id(args: argparse.Namespace, admin) -> str:
    if args.profile_id:
        return args.profile_id
    if args.source_brand:
        return get_profile_id_from_source_brand(admin, args.source_brand)
    raise ValueError(
        "Missing profile context. Use --profile-id or --source-brand."
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        help="Use hardcoded test dataset for brand/topics/keywords",
    )
    parser.add_argument(
        "--source-brand",
        help="Existing brand name used to infer profile_id",
    )
    parser.add_argument(
        "--profile-id",
        help="Profile UUID (overrides --source-brand lookup)",
    )
    parser.add_argument("--brand-name", help="New brand name")
    parser.add_argument("--description", default="", help="Optional brand description")
    parser.add_argument("--lookback-days", type=int, default=30, help="Initial lookback in days")
    parser.add_argument("--frequency-hours", type=int, default=24, help="Scrape frequency in hours")
    parser.add_argument(
        "--topic",
        action="append",
        help="Topic + keywords format: 'Topic Name=kw1,kw2,kw3'",
    )
    parser.add_argument(
        "--append-timestamp",
        action="store_true",
        help="Append UTC timestamp to brand name to avoid duplicates",
    )
    args = parser.parse_args()

    from app.api.endpoints.scraping_supabase import scrape_brand
    from app.core.supabase_client import get_supabase_admin
    from app.crud.supabase_crud import SupabaseCRUD

    preset = PRESETS.get(args.preset) if args.preset else None
    topic_specs = build_topic_specs(args)
    admin = get_supabase_admin()

    profile_id = resolve_profile_id(args, admin)

    brand_name = args.brand_name or (preset.brand_name if preset else None)
    if not brand_name:
        raise ValueError(
            "Missing --brand-name. Provide it directly or use --preset."
        )

    if args.append_timestamp:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        brand_name = f"{brand_name} {stamp}"

    description = args.description
    if not description and preset:
        description = preset.description

    lookback_days = args.lookback_days
    if args.lookback_days == 30 and preset:
        lookback_days = preset.lookback_days

    frequency_hours = args.frequency_hours
    if args.frequency_hours == 24 and preset:
        frequency_hours = preset.frequency_hours

    print(f"Using profile_id: {profile_id}")
    if args.preset:
        print(f"Using preset: {args.preset}")
    print(f"Brand name: {brand_name}")
    print(f"Topics: {[t.name for t in topic_specs]}")

    brand_result = (
        admin.table("brands")
        .insert(
            {
                "profile_id": profile_id,
                "name": brand_name,
                "description": description or None,
                "scrape_frequency_hours": frequency_hours,
                "initial_lookback_days": lookback_days,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .execute()
    )
    if not brand_result.data:
        raise RuntimeError("Failed creating brand.")
    brand = brand_result.data[0]
    brand_id = int(brand["id"])
    print(f"Created brand: {brand_id} ({brand['name']})")

    for spec in topic_specs:
        topic_result = (
            admin.table("topics")
            .insert(
                {
                    "brand_id": brand_id,
                    "name": spec.name,
                    "query_template": None,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .execute()
        )
        if not topic_result.data:
            raise RuntimeError(f"Failed creating topic '{spec.name}'.")
        topic_id = int(topic_result.data[0]["id"])
        print(f"  Created topic: {topic_id} ({spec.name})")

        for kw in spec.keywords:
            keyword_id = ensure_keyword(admin, kw)
            admin.table("topic_keywords").upsert(
                {"topic_id": topic_id, "keyword_id": keyword_id},
                on_conflict="topic_id,keyword_id",
            ).execute()
            print(f"    Linked keyword: {kw} (id={keyword_id})")

    crud = SupabaseCRUD()
    crud.supabase = admin
    fake_user = SimpleNamespace(id=uuid.UUID(profile_id))
    scrape_result = await scrape_brand(
        brand_id=brand_id,
        crud=crud,
        current_user=fake_user,
    )

    print("\nScrape result:")
    print(f"  message: {scrape_result.message}")
    print(f"  mentions_found: {scrape_result.mentions_found}")
    print(f"  mentions_saved: {scrape_result.mentions_saved}")
    if scrape_result.errors:
        print(f"  errors: {scrape_result.errors}")
    print(f"\nDone. Brand ID: {brand_id}")


if __name__ == "__main__":
    asyncio.run(main())
