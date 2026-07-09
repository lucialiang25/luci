"""Steps 5 & 7 — Persist the translated artifact and the push log locally.

Everything is written under ``runtime/`` (gitignored). Only the salted
fingerprint is stored — never the raw Message-ID.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

RUNTIME_DIR = Path("runtime")
TRANSLATED_DIR = RUNTIME_DIR / "translated_messages"
PUSH_LOG_PATH = RUNTIME_DIR / "push_log.jsonl"


def save_translation_artifact(translation: dict, fingerprint: str) -> Path:
    """Step 5 — Save the structured translation as a JSON artifact."""
    TRANSLATED_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "fingerprint": fingerprint,
        "translation": translation,
    }
    path = TRANSLATED_DIR / f"{fingerprint}.json"
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def append_push_log(
    fingerprint: str, rendered_markdown: str, artifact_path: Path
) -> None:
    """Step 7 — Append the rendered parent-facing message to the push log."""
    PUSH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "fingerprint": fingerprint,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "artifact_path": str(artifact_path),
        "message": rendered_markdown,
    }
    with PUSH_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
