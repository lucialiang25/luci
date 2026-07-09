"""Build a stable identity for an email and its HMAC fingerprint.

Identity rule (requirements #2 and #3):
  * use the ``Message-ID`` when present;
  * otherwise fall back to ``sender + subject + date``.

The identity is then HMAC-SHA256'd with ``EMAIL_FINGERPRINT_SECRET`` (via
:mod:`app.security`) to produce a fingerprint that is safe to persist. The raw
``Message-ID`` is never stored anywhere (requirement #6).
"""

from __future__ import annotations

from .security import hmac_sha256


def build_identity(
    message_id: str | None,
    sender: str | None,
    subject: str | None,
    date: str | None,
) -> str:
    """Return a normalized identity string for the email.

    Requirement #2: Message-ID wins when present (surrounding ``< >`` and
    surrounding whitespace are stripped, and comparison is lower-cased).
    Requirement #3: otherwise combine sender + subject + date.
    """
    mid = (message_id or "").strip().strip("<>").strip()
    if mid:
        return f"mid:{mid.lower()}"

    parts = [
        (sender or "").strip().lower(),
        (subject or "").strip().lower(),
        (date or "").strip().lower(),
    ]
    return "fallback:" + "|".join(parts)


def compute_fingerprint(
    message_id: str | None,
    sender: str | None,
    subject: str | None,
    date: str | None,
    secret: str,
) -> str:
    """Return the HMAC-SHA256 fingerprint of the email identity (requirement #4)."""
    identity = build_identity(message_id, sender, subject, date)
    return hmac_sha256(secret, identity)


def compute_fingerprint_from_email(email: dict, secret: str) -> str:
    """Convenience: compute the fingerprint from a sample_email_reader dict."""
    return compute_fingerprint(
        message_id=email.get("message_id"),
        sender=email.get("sender"),
        subject=email.get("subject"),
        date=email.get("date"),
        secret=secret,
    )
