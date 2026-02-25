import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging_config import get_logs_dir
from app.services.scraping.core.date_utils import parse_mention_date
from app.services.scraping.core.text_processing import normalize_url

logger = logging.getLogger("scraping")
_RUN_DIR_CACHE: Dict[str, Path] = {}


def _run_log(scrape_run_id: Optional[str], message: str, level: int = logging.INFO) -> None:
    prefix = f"[run:{scrape_run_id}] " if scrape_run_id else ""
    logger.log(level, "%s%s", prefix, message)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _slugify_label(label: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (label or "").strip())
    safe = safe.strip("_")
    return safe or "unknown_brand"


def _artifact_dir(scrape_run_id: str, artifact_label: Optional[str] = None) -> Path:
    cached = _RUN_DIR_CACHE.get(scrape_run_id)
    if cached is not None:
        cached.mkdir(parents=True, exist_ok=True)
        return cached

    project_root = get_logs_dir().parent
    if artifact_label:
        json_root = project_root / "json"
        json_root.mkdir(parents=True, exist_ok=True)
        base_slug = _slugify_label(artifact_label)
        pattern = re.compile(rf"^{re.escape(base_slug)}(\d+)$", re.IGNORECASE)
        max_idx = 0

        for child in json_root.iterdir():
            if not child.is_dir():
                continue
            match = pattern.match(child.name)
            if not match:
                continue
            idx = int(match.group(1))
            if idx > max_idx:
                max_idx = idx

        run_dir = json_root / f"{base_slug}{max_idx + 1}"
    else:
        run_dir = project_root / "json" / f"scrapedrun_{scrape_run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _RUN_DIR_CACHE[scrape_run_id] = run_dir
    return run_dir


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _serialize_mention(mention: Dict[str, Any]) -> Dict[str, Any]:
    raw_date = (
        mention.get("published_parsed")
        or mention.get("published_at")
        or mention.get("date")
    )
    parsed_date = parse_mention_date(raw_date)
    link = mention.get("link", "")

    serialized = {
        "source_provider": mention.get("source_provider"),
        "source_label": mention.get("source_label"),
        "platform": mention.get("platform"),
        "title": mention.get("title"),
        "content": mention.get("content"),
        "content_teaser": mention.get("content_teaser"),
        "link": link,
        "normalized_link": normalize_url(link) if link else None,
        "published_at": parsed_date.isoformat() if parsed_date else None,
        "published_raw": _jsonable(raw_date),
    }

    extra = {
        key: _jsonable(value)
        for key, value in mention.items()
        if key not in serialized and key != "published_parsed"
    }
    if extra:
        serialized["extra"] = extra

    return serialized


def write_run_metadata(
    scrape_run_id: Optional[str],
    metadata: Dict[str, Any],
    artifact_label: Optional[str] = None,
) -> None:
    if not settings.scraping_run_artifacts_enabled or not scrape_run_id:
        return

    try:
        path = _artifact_dir(scrape_run_id, artifact_label=artifact_label) / "run_metadata.json"
        _write_json(path, _jsonable(metadata))
    except Exception as exc:  # pragma: no cover - debug output must not break flow
        _run_log(scrape_run_id, f"Failed to write run metadata artifact: {exc}", logging.WARNING)


def write_mentions_snapshot(
    scrape_run_id: Optional[str],
    stage: str,
    mentions: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    artifact_label: Optional[str] = None,
) -> None:
    if not settings.scraping_run_artifacts_enabled or not scrape_run_id:
        return

    safe_stage = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in stage).strip("_")
    safe_stage = safe_stage or "stage"
    max_mentions = max(1, int(settings.scraping_run_artifacts_max_mentions))
    exported_mentions = mentions[:max_mentions]

    payload = {
        "run_id": scrape_run_id,
        "stage": safe_stage,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_mentions": len(mentions),
            "exported_mentions": len(exported_mentions),
            "truncated": len(mentions) > len(exported_mentions),
            "max_mentions": max_mentions,
        },
        "metadata": _jsonable(metadata or {}),
        "mentions": [_serialize_mention(mention) for mention in exported_mentions],
    }

    try:
        path = _artifact_dir(scrape_run_id, artifact_label=artifact_label) / f"mentions_{safe_stage}.json"
        _write_json(path, payload)
    except Exception as exc:  # pragma: no cover - debug output must not break flow
        _run_log(scrape_run_id, f"Failed to write mentions snapshot '{safe_stage}': {exc}", logging.WARNING)
