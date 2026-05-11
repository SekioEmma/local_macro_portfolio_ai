from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def save_json_cache(path: str, data: dict) -> None:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(data)
    payload.setdefault("cached_at", _utc_now())

    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_json_cache(path: str, max_age_seconds: int) -> dict | None:
    cache_path = Path(path)
    if not cache_path.exists() or not cache_path.is_file():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict):
        return None

    modified_at = datetime.fromtimestamp(
        cache_path.stat().st_mtime,
        tz=timezone.utc,
    )
    cached_at = _parse_datetime(payload.get("cached_at")) or modified_at
    age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
    if age_seconds > max_age_seconds:
        return None

    payload.setdefault("cached_at", cached_at.isoformat())
    return payload


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
