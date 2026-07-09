"""Step 2 — Salted HMAC duplicate fingerprinting.

The raw ``Message-ID`` is **never** persisted. Instead we store only its
salted HMAC-SHA256 digest, which is safe to write to runtime files and can be
compared across runs to detect duplicate emails.

The HMAC key and salt are generated once and stored locally under ``runtime/``
(which is gitignored), so the same email always produces the same fingerprint
across runs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path

RUNTIME_DIR = Path("runtime")
SECRET_PATH = RUNTIME_DIR / "fingerprint_secret.json"
PROCESSED_PATH = RUNTIME_DIR / "processed_fingerprints.jsonl"


def _load_or_create_secret() -> tuple[bytes, bytes]:
    """Return ``(key, salt)``, generating and persisting them on first use."""
    if SECRET_PATH.exists():
        data = json.loads(SECRET_PATH.read_text(encoding="utf-8"))
        return bytes.fromhex(data["key"]), bytes.fromhex(data["salt"])

    # First run ever: make a fresh secret and keep it locally.
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    salt = secrets.token_bytes(16)
    SECRET_PATH.write_text(
        json.dumps({"key": key.hex(), "salt": salt.hex()}, indent=2),
        encoding="utf-8",
    )
    return key, salt


def compute_fingerprint(content: str) -> str:
    """Return the hex salted HMAC-SHA256 digest of ``content``.

    The salt is prepended to the (normalized) content before HMAC, and the
    HMAC key is the locally generated secret. The digest is safe to store.
    """
    key, salt = _load_or_create_secret()
    normalized = content.strip().lower().encode("utf-8")
    return hmac.new(key, salt + normalized, hashlib.sha256).hexdigest()


def already_processed(fingerprint: str) -> bool:
    """True if ``fingerprint`` has already been recorded as processed."""
    if not PROCESSED_PATH.exists():
        return False
    with PROCESSED_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip malformed lines
            if entry.get("fingerprint") == fingerprint:
                return True
    return False


def mark_processed(fingerprint: str, *, meta: dict) -> None:
    """Append ``fingerprint`` to the processed store.

    Call this ONLY after the artifact and the push log have been written,
    so a half-finished run never looks "done".
    """
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"fingerprint": fingerprint, **meta}
    with PROCESSED_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
