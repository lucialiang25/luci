"""Persistent record of processed emails for duplicate prevention.

Storage file: ``runtime/processed_emails.json`` (a JSON array).

Each record stores **only** (requirement #5):
  * ``fingerprint``   — the HMAC-SHA256 digest
  * ``processed_at``  — ISO-8601 timestamp
  * ``artifact_path`` — optional path to the saved artifact

The raw ``Message-ID`` is **never** written here (requirement #6) — only the
fingerprint is stored.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

DEFAULT_STORE_PATH = Path("runtime/processed_emails.json")


def _load(path: str | Path = DEFAULT_STORE_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _save(path: str | Path, records: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def all_records(path: str | Path = DEFAULT_STORE_PATH) -> list[dict]:
    """Return every stored record."""
    return _load(path)


def is_processed(fingerprint: str, path: str | Path = DEFAULT_STORE_PATH) -> bool:
    """True if *fingerprint* is already recorded as processed."""
    return any(record.get("fingerprint") == fingerprint for record in _load(path))


def mark_processed(
    fingerprint: str,
    artifact_path: str | None = None,
    *,
    path: str | Path = DEFAULT_STORE_PATH,
) -> dict:
    """Append a processed record and return it.

    Call this **only after** the artifact and any local log have been written,
    so a half-finished run is never marked done.
    """
    records = _load(path)
    record = {
        "fingerprint": fingerprint,
        "processed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "artifact_path": artifact_path,
    }
    records.append(record)
    _save(path, records)
    return record
