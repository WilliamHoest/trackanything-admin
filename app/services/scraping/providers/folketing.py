import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import httpx

from app.services.scraping.core.date_utils import parse_mention_date
from app.services.scraping.core.http_client import TIMEOUT_SECONDS

logger = logging.getLogger("scraping")

FOLKETING_BASE = "https://oda.ft.dk/api"
AKTØRTYPE_UDVALG = 3
RATE_DELAY = 1.0  # seconds between requests (conservative, no documented limit)

# Fixed legislative keywords per udvalg — matched regardless of user keywords.
# These represent the core fond-legislation tracked by each committee.
UDVALG_CONFIG = [
    {
        "navn": "Erhvervsudvalget",
        "label": "ERU",
        "keywords": [
            "erhvervsfondsloven",
            "lov om erhvervsdrivende fonde",
            "erhvervsdrivende fonde",
            "anbefalinger for god fondsledelse",
            "erhvervsfond",
        ],
    },
    {
        "navn": "Retsudvalget",
        "label": "REU",
        "keywords": [
            "fondsloven",
            "fonde og visse foreninger",
            "fondsudvalget",
            "fondslov",
        ],
    },
    {
        "navn": "Skatteudvalget",
        "label": "SAU",
        "keywords": [
            "fondsbeskatningsloven",
            "uddelingsfradrag",
            "konsolideringsfradrag",
            "fondsbeskatning",
        ],
    },
]

# Fallback period → samling code mapping (derived from Folketing API periods)
_PERIOD_SAMLING_FALLBACK: Dict[int, str] = {
    163: "20241",  # 2024-25
    165: "20251",  # 2025-26 (1. samling)
    167: "20252",  # 2025-26 (2. samling)
}

_FT_TYPE_PATH: Dict[str, str] = {
    "l": "lovforslag",
    "b": "beslutningsforslag",
    "s": "spoergsmaal",
    "f": "forslag",
}


def _samling_code(titel: str) -> str:
    """Parse samling code from period title. '2025-26 (2. samling)' → '20252'"""
    m = re.search(r"(\d{4})-\d{2}\s*\((\d+)\.\s*samling\)", titel)
    if m:
        return m.group(1) + m.group(2)
    m = re.search(r"(\d{4})-\d{2}", titel)
    if m:
        return m.group(1) + "1"
    return ""


def _ft_url(sag: dict, samling: str) -> str:
    """Build ft.dk URL for a sag, falling back to ODA API URL."""
    prefix = (sag.get("nummerprefix") or "").strip().lower()
    nummer = (sag.get("nummernumerisk") or "").strip()
    type_path = _FT_TYPE_PATH.get(prefix)
    if not samling or not nummer or not type_path:
        return f"https://oda.ft.dk/api/Sag({sag['id']})"
    return f"https://www.ft.dk/samling/{samling}/{type_path}/{prefix}{nummer}/index.htm"


def _log(scrape_run_id: Optional[str], msg: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s[FOLKETING] %s", prefix, msg)


async def _get(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    try:
        resp = await client.get(url, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("[FOLKETING] request failed %s: %s", url, exc)
        return None


async def scrape_folketing(
    keywords: List[str],
    from_date: Optional[datetime] = None,
    scrape_run_id: Optional[str] = None,
    allowed_languages: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Fetch Folketing legislative cases from ERU, REU, and SAU committees.

    Unlike other providers, this one tracks fixed legislative keywords relevant
    to Danish foundations in addition to any user-provided keywords.
    Platform field is set to "Folketing - {LABEL}" per committee.
    """
    since = from_date or (datetime.now(timezone.utc) - timedelta(days=7))
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    from_str = since.strftime("%Y-%m-%dT%H:%M:%S")

    _log(scrape_run_id, f"Starting since={since.isoformat()}, user_keywords={len(keywords)}")

    period_samling: Dict[int, str] = dict(_PERIOD_SAMLING_FALLBACK)
    mentions: List[Dict] = []
    seen_sag_ids: set = set()

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        # Step 1: Refresh period → samling code mapping and find recent legislative periods
        periods_url = (
            f"{FOLKETING_BASE}/Periode"
            f"?%24select=id,titel,startdato"
            f"&%24orderby=startdato%20desc"
            f"&%24top=20"
        )
        periods_data = await _get(client, periods_url)
        await asyncio.sleep(RATE_DELAY)

        legislative_period_ids: List[int] = []
        if periods_data:
            for p in periods_data.get("value", []):
                pid = p.get("id")
                titel = p.get("titel", "")
                code = _samling_code(titel)
                if pid and code:
                    period_samling[pid] = code
                if "samling" in titel.lower() and pid:
                    legislative_period_ids.append(pid)
                if len(legislative_period_ids) >= 2:
                    break

        if not legislative_period_ids:
            _log(scrape_run_id, "Period lookup failed; using fallback IDs [165, 167]", logging.WARNING)
            legislative_period_ids = [165, 167]

        _log(scrape_run_id, f"Using period IDs: {legislative_period_ids}", logging.DEBUG)

        # Step 2: For each udvalg, find aktørid(s) then fetch recent sager
        for udvalg_cfg in UDVALG_CONFIG:
            navn = udvalg_cfg["navn"]
            label = udvalg_cfg["label"]
            fixed_kws = [kw.lower() for kw in udvalg_cfg["keywords"]]
            user_kws = [kw.lower() for kw in keywords]
            all_kws = fixed_kws + user_kws

            udvalg_ids: List[int] = []
            for period_id in legislative_period_ids:
                aktør_url = (
                    f"{FOLKETING_BASE}/Akt%C3%B8r"
                    f"?%24filter=typeid%20eq%20{AKTØRTYPE_UDVALG}"
                    f"%20and%20periodeid%20eq%20{period_id}"
                    f"&%24select=id,navn"
                    f"&%24top=100"
                )
                aktør_data = await _get(client, aktør_url)
                await asyncio.sleep(RATE_DELAY)
                if not aktør_data:
                    continue
                for item in aktør_data.get("value", []):
                    if item.get("navn", "").strip().lower() == navn.lower():
                        udvalg_ids.append(item["id"])
                        break

            if not udvalg_ids:
                _log(scrape_run_id, f"{label}: udvalg '{navn}' not found in any period", logging.WARNING)
                continue

            _log(scrape_run_id, f"{label}: aktørid(s)={udvalg_ids}", logging.DEBUG)

            # Step 3: Fetch SagAktør with Sag expanded, filtered by date
            for aktørid in udvalg_ids:
                sag_url = (
                    f"{FOLKETING_BASE}/SagAkt%C3%B8r"
                    f"?%24filter=akt%C3%B8rid%20eq%20{aktørid}"
                    f"%20and%20opdateringsdato%20ge%20datetime'{from_str}'"
                    f"&%24expand=Sag"
                    f"&%24top=100"
                    f"&%24orderby=opdateringsdato%20desc"
                )
                sag_data = await _get(client, sag_url)
                await asyncio.sleep(RATE_DELAY)
                if not sag_data:
                    continue

                kept = 0
                for item in sag_data.get("value", []):
                    sag = item.get("Sag")
                    if not sag or not isinstance(sag, dict):
                        continue
                    sag_id = sag.get("id")
                    if not sag_id or sag_id in seen_sag_ids:
                        continue

                    # Match against legislative or user keywords in title + resume
                    text = (
                        (sag.get("titel") or "")
                        + " "
                        + (sag.get("resume") or "")
                    ).lower()
                    if not any(kw in text for kw in all_kws):
                        continue

                    seen_sag_ids.add(sag_id)

                    periodeid = sag.get("periodeid")
                    samling = period_samling.get(periodeid, "")
                    link = _ft_url(sag, samling)

                    published_dt = parse_mention_date(sag.get("opdateringsdato"))
                    titel_str = (sag.get("titel") or sag.get("titelkort") or "").strip()
                    resume_str = (sag.get("resume") or "").strip()
                    nummer = (sag.get("nummer") or "").strip()
                    title_str = f"[{nummer}] {titel_str}" if nummer else titel_str

                    mentions.append({
                        "title": title_str,
                        "link": link,
                        "content_teaser": resume_str[:300] if resume_str else f"Sag behandlet i {navn}",
                        "platform": f"Folketing - {label}",
                        "published_parsed": published_dt.timetuple() if published_dt else None,
                    })
                    kept += 1

                _log(scrape_run_id, f"{label}(aktørid={aktørid}): kept {kept} sager")

    _log(scrape_run_id, f"Total: {len(mentions)} Folketing mentions")
    return mentions
