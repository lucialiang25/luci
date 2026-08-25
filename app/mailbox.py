"""Live IMAP mailbox connector for SchoolMail Bridge.

Reads Gmail (or any IMAP server) using an app password from ``.env``.
Fetched messages are normalized through :func:`app.sample_email_reader.read_eml_bytes`
so live mail and sample ``.eml`` files share the same email dict.

This module never logs the app password, OAuth tokens, or the raw Message-ID
store. Login failures are reported without echoing secrets.
"""

from __future__ import annotations

import imaplib
import os
from contextlib import contextmanager
from dataclasses import dataclass

from .sample_email_reader import read_eml_bytes
from .security import load_dotenv_if_present

DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_FOLDER = "INBOX"


class MailboxConfigError(Exception):
    """Raised when IMAP settings are missing from the environment."""


class MailboxError(Exception):
    """Raised when an IMAP command fails after a successful login."""


@dataclass(frozen=True)
class ImapConfig:
    address: str
    password: str
    host: str = DEFAULT_IMAP_HOST
    port: int = DEFAULT_IMAP_PORT
    folder: str = DEFAULT_FOLDER


def load_imap_config(env: dict[str, str] | None = None) -> ImapConfig:
    """Load IMAP settings. App-password spaces (Gmail's display form) are stripped."""
    if env is None:
        load_dotenv_if_present()
        env = os.environ

    address = (env.get("EMAIL_ADDRESS") or "").strip()
    password = (env.get("EMAIL_APP_PASSWORD") or "").replace(" ", "").strip()
    host = (env.get("IMAP_SERVER") or DEFAULT_IMAP_HOST).strip() or DEFAULT_IMAP_HOST
    folder = (env.get("IMAP_FOLDER") or DEFAULT_FOLDER).strip() or DEFAULT_FOLDER
    try:
        port = int((env.get("IMAP_PORT") or str(DEFAULT_IMAP_PORT)).strip())
    except ValueError as exc:
        raise MailboxConfigError("IMAP_PORT must be an integer.") from exc

    if not address or address.startswith("your_email@"):
        raise MailboxConfigError(
            "EMAIL_ADDRESS is missing. Set your Gmail address in the .env file."
        )
    if not password or password.startswith("replace_"):
        raise MailboxConfigError(
            "EMAIL_APP_PASSWORD is missing. Set a Gmail App Password in the .env file."
        )
    return ImapConfig(
        address=address,
        password=password,
        host=host,
        port=port,
        folder=folder,
    )


def extract_rfc822(data) -> bytes:
    """Pull the RFC822 payload out of an imaplib FETCH response list."""
    if not data:
        raise MailboxError("IMAP FETCH returned empty data")
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2:
            payload = item[1]
            if isinstance(payload, bytes):
                return payload
            if isinstance(payload, str):
                return payload.encode("utf-8")
    raise MailboxError("IMAP FETCH returned no message payload")


def connect(config: ImapConfig) -> imaplib.IMAP4_SSL:
    """Open an SSL IMAP session. Does not log credentials."""
    client = imaplib.IMAP4_SSL(config.host, config.port)
    try:
        client.login(config.address, config.password)
    except imaplib.IMAP4.error as exc:
        raise MailboxError(
            "IMAP login failed. Check EMAIL_ADDRESS, the Gmail App Password, "
            "and that IMAP is enabled in Gmail settings."
        ) from exc
    return client


@contextmanager
def imap_session(config: ImapConfig | None = None):
    """Yield ``(client, config)`` and always logout."""
    cfg = config or load_imap_config()
    client = connect(cfg)
    try:
        yield client, cfg
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _select_folder(client, folder: str) -> None:
    typ, _ = client.select(folder, readonly=True)
    if typ != "OK":
        raise MailboxError(f"Could not open folder {folder}")


def list_messages(client, folder: str = DEFAULT_FOLDER, limit: int = 20) -> list[dict]:
    """Return the newest *limit* messages as header-only dicts with ``uid``."""
    _select_folder(client, folder)
    typ, data = client.uid("SEARCH", None, "ALL")
    if typ != "OK":
        raise MailboxError("IMAP SEARCH failed")
    uids = data[0].split() if data and data[0] else []
    chosen = uids[-max(limit, 0) :][::-1]
    listed: list[dict] = []
    for uid in chosen:
        uid_s = uid.decode() if isinstance(uid, bytes) else str(uid)
        typ, fetched = client.uid("FETCH", uid, "(RFC822.HEADER)")
        if typ != "OK":
            raise MailboxError(f"IMAP FETCH failed for uid {uid_s}")
        parsed = read_eml_bytes(
            extract_rfc822(fetched),
            sourcepath=f"imap://{folder}/uid/{uid_s}",
        )
        listed.append(
            {
                "uid": uid_s,
                "message_id": parsed["message_id"],
                "sender": parsed["sender"],
                "subject": parsed["subject"],
                "date": parsed["date"],
            }
        )
    return listed


def fetch_message(client, uid: str, folder: str = DEFAULT_FOLDER) -> dict:
    """Fetch one message by IMAP UID and return the shared email dict."""
    _select_folder(client, folder)
    typ, fetched = client.uid("FETCH", str(uid), "(RFC822)")
    if typ != "OK":
        raise MailboxError(f"IMAP FETCH failed for uid {uid}")
    raw = extract_rfc822(fetched)
    return read_eml_bytes(raw, sourcepath=f"imap://{folder}/uid/{uid}")
