#!/usr/bin/env python3
"""
Script til at rydde op i admin profiler og oprette nye test brands.
Kør med: python scripts/cleanup_and_seed.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from app.core.config import settings
from datetime import datetime

def get_admin_client():
    """Get Supabase client with service role key (bypasses RLS)"""
    return create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key
    )

def main():
    client = get_admin_client()

    # 1. Find alle profiler
    print("\n📋 Finder profiler...")
    profiles_result = client.table("profiles").select("*").execute()
    profiles = profiles_result.data or []

    if not profiles:
        print("❌ Ingen profiler fundet!")
        return

    print(f"Fandt {len(profiles)} profiler:")
    for p in profiles:
        print(f"  - {p.get('contact_email') or p.get('email')} (ID: {p['id']})")

    # 2. Find target profil (madsrunge@hotmail.dk)
    target_profile = None
    for p in profiles:
        email = p.get('contact_email') or p.get('email')
        if email and 'madsrunge@hotmail.dk' in email.lower():
            target_profile = p
            break

    if not target_profile:
        print("❌ Kunne ikke finde profil med madsrunge@hotmail.dk")
        return

    print(f"\n🎯 Target profil: {target_profile.get('contact_email')} (ID: {target_profile['id']})")

    # 3. Slet alle brands for ALLE profiler (cascades til topics, mentions, topic_keywords)
    print("\n🗑️  Sletter alle brands (cascades til topics, mentions, keywords)...")

    for p in profiles:
        profile_id = p['id']
        email = p.get('contact_email') or p.get('email') or 'Unknown'

        # Hent antal brands/mentions før sletning
        brands_before = client.table("brands").select("id").eq("profile_id", profile_id).execute()
        brand_ids = [b['id'] for b in (brands_before.data or [])]

        mention_count = 0
        if brand_ids:
            mentions_before = client.table("mentions").select("id", count="exact").in_("brand_id", brand_ids).execute()
            mention_count = mentions_before.count or len(mentions_before.data or [])

        # Slet brands (cascades automatisk)
        if brand_ids:
            client.table("brands").delete().eq("profile_id", profile_id).execute()
            print(f"  ✅ {email}: Slettet {len(brand_ids)} brands, {mention_count} mentions")
        else:
            print(f"  ⏭️  {email}: Ingen brands at slette")

    # 4. Opret nye brands for target profil
    print(f"\n🏗️  Opretter nye brands for {target_profile.get('contact_email')}...")

    now = datetime.utcnow().isoformat()
    profile_id = target_profile['id']

    # Brand 1: Konkurrentovervågning
    brand1_data = {
        "name": "Konkurrentovervågning",
        "description": "Overvåg konkurrenters aktiviteter og nyheder i markedet",
        "profile_id": profile_id,
        "scrape_frequency_hours": 4,
        "is_active": True,
        "created_at": now
    }
    brand1_result = client.table("brands").insert(brand1_data).execute()
    brand1 = brand1_result.data[0]
    print(f"  ✅ Brand oprettet: {brand1['name']} (ID: {brand1['id']})")

    # Brand 1 Topics
    brand1_topics = [
        {
            "name": "Prisændringer",
            "keywords": ["prisstigning", "prisnedsættelse", "rabat", "tilbud", "udsalg"]
        },
        {
            "name": "Produktlanceringer",
            "keywords": ["ny model", "lancering", "produktnyhed", "præsenterer", "introducerer"]
        },
        {
            "name": "Virksomhedsnyheder",
            "keywords": ["CEO", "direktør", "kvartalsregnskab", "omsætning", "fusion", "opkøb"]
        }
    ]

    for topic_data in brand1_topics:
        # Opret topic
        topic_result = client.table("topics").insert({
            "name": topic_data["name"],
            "brand_id": brand1["id"],
            "is_active": True,
            "created_at": now
        }).execute()
        topic = topic_result.data[0]

        # Opret keywords og link til topic
        for kw_text in topic_data["keywords"]:
            # Check om keyword eksisterer
            existing = client.table("keywords").select("*").eq("text", kw_text).execute()
            if existing.data:
                kw_id = existing.data[0]["id"]
            else:
                kw_result = client.table("keywords").insert({
                    "text": kw_text,
                    "created_at": now
                }).execute()
                kw_id = kw_result.data[0]["id"]

            # Link keyword til topic
            client.table("topic_keywords").insert({
                "topic_id": topic["id"],
                "keyword_id": kw_id
            }).execute()

        print(f"    📁 Topic: {topic_data['name']} ({len(topic_data['keywords'])} keywords)")

    # Brand 2: AI & Teknologi Trends
    brand2_data = {
        "name": "AI & Teknologi Trends",
        "description": "Hold øje med de seneste trends inden for AI og teknologi i Danmark",
        "profile_id": profile_id,
        "scrape_frequency_hours": 6,
        "is_active": True,
        "created_at": now
    }
    brand2_result = client.table("brands").insert(brand2_data).execute()
    brand2 = brand2_result.data[0]
    print(f"  ✅ Brand oprettet: {brand2['name']} (ID: {brand2['id']})")

    # Brand 2 Topics
    brand2_topics = [
        {
            "name": "Kunstig Intelligens",
            "keywords": ["kunstig intelligens", "AI", "ChatGPT", "maskinlæring", "deep learning", "LLM"]
        },
        {
            "name": "Danske Startups",
            "keywords": ["startup", "iværksætter", "venture", "investering", "dansk tech"]
        },
        {
            "name": "Digital Transformation",
            "keywords": ["digitalisering", "automatisering", "cloud", "digital omstilling"]
        }
    ]

    for topic_data in brand2_topics:
        topic_result = client.table("topics").insert({
            "name": topic_data["name"],
            "brand_id": brand2["id"],
            "is_active": True,
            "created_at": now
        }).execute()
        topic = topic_result.data[0]

        for kw_text in topic_data["keywords"]:
            existing = client.table("keywords").select("*").eq("text", kw_text).execute()
            if existing.data:
                kw_id = existing.data[0]["id"]
            else:
                kw_result = client.table("keywords").insert({
                    "text": kw_text,
                    "created_at": now
                }).execute()
                kw_id = kw_result.data[0]["id"]

            client.table("topic_keywords").insert({
                "topic_id": topic["id"],
                "keyword_id": kw_id
            }).execute()

        print(f"    📁 Topic: {topic_data['name']} ({len(topic_data['keywords'])} keywords)")

    # Summary
    print("\n" + "="*50)
    print("✅ FÆRDIG!")
    print("="*50)
    print(f"\nOprettet for {target_profile.get('contact_email')}:")
    print(f"  • 2 brands")
    print(f"  • 6 topics")
    print(f"  • 21 keywords")
    print("\nBrands:")
    print(f"  1. {brand1['name']} (scrape hver {brand1_data['scrape_frequency_hours']}. time)")
    print(f"  2. {brand2['name']} (scrape hver {brand2_data['scrape_frequency_hours']}. time)")

if __name__ == "__main__":
    main()
