"""Step 1 — Parse a local ``.eml`` email file into a small dict."""

from __future__ import annotations

import email
from email import policy
from pathlib import Path


def _part_text(part) -> str:
    """Best-effort extraction of text from a single email part."""
    try:
        return part.get_content()
    except Exception:
        # Fallback for unusual charsets: decode the raw payload manually.
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")


def parse_email(eml_path: Path) -> dict:
    """Read ``eml_path`` and return its key fields.

    Returns a dict with ``message_id``, ``subject``, ``from`` and ``body``.
    ``policy.default`` decodes headers and returns the body as a ``str``.
    """
    with eml_path.open("rb") as handle:
        message = email.message_from_binary_file(handle, policy=policy.default)

    # Headers may be absent — default to empty strings.
    subject = (message.get("Subject") or "").strip()
    message_id = (message.get("Message-ID") or "").strip()
    sender = (message.get("From") or "").strip()

    # Use the first text/plain part as the readable body.
    body = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                body = _part_text(part)
                break
    else:
        body = _part_text(message)
    body = body.strip()

    return {
        "message_id": message_id,
        "subject": subject,
        "from": sender,
        "body": body,
    }
