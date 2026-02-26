#!/usr/bin/env python3
"""
Bootstrap source_configs with AI analysis in controlled chunks.

Workflow:
1) Optional reset: delete all existing source_configs.
2) Analyze sources in chunks (default: 3 at a time).
3) Verify each domain was saved in source_configs.

This script uses backend service logic directly (SourceConfigService),
which is the same AI generation path used by admin source config endpoints.

Usage examples:
  python scripts/bootstrap_source_configs_ai.py --reset-first --max-domains 6
  python scripts/bootstrap_source_configs_ai.py --reset-first
  python scripts/bootstrap_source_configs_ai.py --domains dr.dk,tv2.dk,politiken.dk
  python scripts/bootstrap_source_configs_ai.py --domains-file my_domains.txt --chunk-size 3
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

# Ensure `app` imports work when script is run as `python scripts/...`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.supabase_client import get_supabase_admin
from app.crud.supabase_crud import SupabaseCRUD
from app.services.source_configuration.service import SourceConfigService


DEFAULT_DK_DOMAINS: List[str] = [
    "dr.dk",
    "tv2.dk",
    "politiken.dk",
    "jp.dk",
    "ekstrabladet.dk",
    "berlingske.dk",
    "bt.dk",
    "information.dk",
    "kristeligt-dagblad.dk",
    "weekendavisen.dk",
    "borsen.dk",
    "finans.dk",
    "altinget.dk",
    "zetland.dk",
    "avisen.dk",
    "nordjyske.dk",
    "sn.dk",
    "jv.dk",
    "fyens.dk",
    "faa.dk",
    "stiften.dk",
    "hsfo.dk",
    "vafo.dk",
    "mja.dk",
    "viborg-folkeblad.dk",
    "herningfolkeblad.dk",
    "folketidende.dk",
    "bornholmstidende.dk",
    "ing.dk",
    "version2.dk",
    "computerworld.dk",
    "watchmedier.dk",
    "euroinvestor.dk",
    "danwatch.dk",
    "cphpost.dk",
]

DEFAULT_SE_DOMAINS: List[str] = [
    "aftonbladet.se",
    "expressen.se",
    "svt.se",
    "sverigesradio.se",
    "tv4.se",
    "dn.se",
    "svd.se",
    "di.se",
    "gp.se",
    "sydsvenskan.se",
    "hd.se",
    "unt.se",
    "na.se",
    "norran.se",
    "vk.se",
    "nt.se",
    "corren.se",
    "op.se",
    "vlt.se",
    "arbetarbladet.se",
    "allehanda.se",
    "hn.se",
    "hallandsposten.se",
    "bt.se",
    "skd.se",
    "ttela.se",
    "folkbladet.nu",
    "nyteknik.se",
    "dagenssamhalle.se",
    "etc.se",
    "breakit.se",
    "omni.se",
    "dagensps.se",
    "smp.se",
    "barometern.se",
]

DEFAULT_NO_DOMAINS: List[str] = [
    "vg.no",
    "dagbladet.no",
    "nrk.no",
    "tv2.no",
    "aftenposten.no",
    "nettavisen.no",
    "e24.no",
    "dn.no",
    "abcnyheter.no",
    "bt.no",
    "adressa.no",
    "aftenbladet.no",
    "klassekampen.no",
    "finansavisen.no",
    "dagsavisen.no",
    "morgenbladet.no",
    "nationen.no",
    "fvn.no",
    "itromso.no",
    "nordlys.no",
    "ba.no",
    "rb.no",
    "dt.no",
    "sa.no",
    "tb.no",
    "varden.no",
    "amta.no",
    "oa.no",
    "gd.no",
    "ifinnmark.no",
    "smp.no",
    "tu.no",
    "digi.no",
    "kode24.no",
    "forskning.no",
]

MARKET_PRESETS = {
    "dk": DEFAULT_DK_DOMAINS,
    "se": DEFAULT_SE_DOMAINS,
    "no": DEFAULT_NO_DOMAINS,
    "nordics": DEFAULT_DK_DOMAINS + DEFAULT_SE_DOMAINS + DEFAULT_NO_DOMAINS,
}


@dataclass
class DomainResult:
    domain: str
    confidence: str
    message: str
    saved: bool
    has_title_selector: bool
    has_content_selector: bool
    has_date_selector: bool
    has_search_url_pattern: bool
    error: Optional[str] = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_domain(value: str) -> str:
    domain = (value or "").strip().lower()
    if domain.startswith("http://"):
        domain = domain[7:]
    if domain.startswith("https://"):
        domain = domain[8:]
    domain = domain.rstrip("/")
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def chunked(items: List[str], chunk_size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def load_domains(args: argparse.Namespace) -> List[str]:
    raw_domains: List[str] = []

    if args.domains:
        raw_domains.extend([d.strip() for d in args.domains.split(",") if d.strip()])
    elif args.domains_file:
        content = Path(args.domains_file).read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            raw_domains.append(line)
    else:
        raw_domains.extend(MARKET_PRESETS[args.market])

    normalized: List[str] = []
    seen = set()
    for d in raw_domains:
        domain = normalize_domain(d)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        normalized.append(domain)

    if args.max_domains and args.max_domains > 0:
        normalized = normalized[: args.max_domains]

    return normalized


def reset_all_source_configs() -> int:
    admin = get_supabase_admin()
    existing = admin.table("source_configs").select("domain").execute().data or []
    domains = [normalize_domain(row.get("domain", "")) for row in existing if row.get("domain")]

    deleted = 0
    for domain in domains:
        admin.table("source_configs").delete().eq("domain", domain).execute()
        deleted += 1

    return deleted


async def analyze_domain(domain: str, service: SourceConfigService) -> DomainResult:
    try:
        result = await service.refresh_config_from_homepage(domain)
        saved_config = await service.get_config_for_domain(domain)

        has_title = bool(saved_config and saved_config.get("title_selector"))
        has_content = bool(saved_config and saved_config.get("content_selector"))
        has_date = bool(saved_config and saved_config.get("date_selector"))
        has_search_pattern = bool(saved_config and saved_config.get("search_url_pattern"))

        saved = bool(saved_config)
        return DomainResult(
            domain=domain,
            confidence=result.confidence,
            message=result.message,
            saved=saved,
            has_title_selector=has_title,
            has_content_selector=has_content,
            has_date_selector=has_date,
            has_search_url_pattern=has_search_pattern,
        )
    except Exception as exc:
        return DomainResult(
            domain=domain,
            confidence="low",
            message="Exception during analysis",
            saved=False,
            has_title_selector=False,
            has_content_selector=False,
            has_date_selector=False,
            has_search_url_pattern=False,
            error=f"{type(exc).__name__}: {exc}",
        )


async def run(args: argparse.Namespace) -> int:
    domains = load_domains(args)
    if not domains:
        print("No domains selected. Exiting.")
        return 1

    print(f"Selected domains: {len(domains)}")
    for idx, domain in enumerate(domains, start=1):
        print(f"  {idx:02d}. {domain}")

    if args.reset_first:
        print("\nResetting source_configs...")
        deleted = reset_all_source_configs()
        print(f"Deleted source_configs: {deleted}")
        if args.reset_only:
            print("Reset-only mode enabled. Exiting after cleanup.")
            return 0

    crud = SupabaseCRUD()
    service = SourceConfigService(crud)
    all_results: List[DomainResult] = []

    print(f"\nStarting AI source-config generation (chunk_size={args.chunk_size})...")
    for chunk_index, chunk in enumerate(chunked(domains, args.chunk_size), start=1):
        print(f"\nChunk {chunk_index}: {', '.join(chunk)}")
        for domain in chunk:
            print(f"  -> analyzing {domain} ...")
            domain_result = await analyze_domain(domain, service)
            all_results.append(domain_result)
            status = "OK" if domain_result.saved else "FAILED"
            print(
                "     "
                f"[{status}] confidence={domain_result.confidence}, "
                f"title={domain_result.has_title_selector}, "
                f"content={domain_result.has_content_selector}, "
                f"date={domain_result.has_date_selector}, "
                f"search_pattern={domain_result.has_search_url_pattern}"
            )
            if domain_result.error:
                print(f"     error: {domain_result.error}")
            if domain_result.message:
                print(f"     message: {domain_result.message}")

        if args.pause_between_chunks > 0:
            await asyncio.sleep(args.pause_between_chunks)

    succeeded = [r for r in all_results if r.saved]
    failed = [r for r in all_results if not r.saved]

    report = {
        "generated_at": now_iso(),
        "total_domains": len(all_results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "results": [asdict(r) for r in all_results],
    }

    report_dir = Path(PROJECT_ROOT) / "logs" / "source_config_bootstrap"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"bootstrap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nSummary")
    print(f"  Total: {len(all_results)}")
    print(f"  Succeeded: {len(succeeded)}")
    print(f"  Failed: {len(failed)}")
    print(f"  Report: {report_path}")

    if failed:
        print("\nFailed domains:")
        for r in failed:
            print(f"  - {r.domain}: {r.error or r.message}")

    return 0 if not failed else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset and bootstrap source_configs using AI analysis in chunks.",
    )
    parser.add_argument(
        "--reset-first",
        action="store_true",
        help="Delete all existing rows in source_configs before generating new ones.",
    )
    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="Only reset source_configs and exit (requires --reset-first).",
    )
    parser.add_argument(
        "--domains",
        type=str,
        default="",
        help="Comma-separated domains to process. Overrides --market presets.",
    )
    parser.add_argument(
        "--market",
        type=str,
        choices=["dk", "se", "no", "nordics"],
        default="dk",
        help="Preset domain market when --domains/--domains-file are not provided (default: dk).",
    )
    parser.add_argument(
        "--domains-file",
        type=str,
        default="",
        help="Path to file with one domain per line.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=3,
        help="How many domains to process per chunk (default: 3).",
    )
    parser.add_argument(
        "--pause-between-chunks",
        type=float,
        default=1.5,
        help="Seconds to wait between chunks (default: 1.5).",
    )
    parser.add_argument(
        "--max-domains",
        type=int,
        default=0,
        help="Optional cap for test runs (e.g. --max-domains 6).",
    )
    args = parser.parse_args()
    if args.reset_only and not args.reset_first:
        parser.error("--reset-only requires --reset-first")
    args.chunk_size = max(1, args.chunk_size)
    return args


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
