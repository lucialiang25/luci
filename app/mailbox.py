"""Live IMAP mailbox connector for SchoolMail Bridge.

Logs in to Gmail with OAuth 2.0 (IMAP ``XOAUTH2``) by default; set
``EMAIL_AUTH_METHOD=app_password`` to use a Gmail App Password instead.
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

from .gmail_oauth import (
    DEFAULT_TOKEN_FILE,
    GmailOAuthError,
    build_xoauth2_string,
    get_access_token,
)
from .sample_email_reader import read_eml_bytes
from .security import load_dotenv_if_present

DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_FOLDER = "INBOX"

AUTH_OAUTH2 = "oauth2"
AUTH_APP_PASSWORD = "app_password"
AUTH_METHODS = (AUTH_OAUTH2, AUTH_APP_PASSWORD)


class MailboxConfigError(Exception):
    """Raised when IMAP settings are missing from the environment."""


class MailboxError(Exception):
    """Raised when an IMAP command fails after a successful login."""


@dataclass(frozen=True)
class ImapConfig:
    address: str
    password: str = ""
    host: str = DEFAULT_IMAP_HOST
    port: int = DEFAULT_IMAP_PORT
    folder: str = DEFAULT_FOLDER
    auth_method: str = AUTH_OAUTH2
    oauth_token_file: str = str(DEFAULT_TOKEN_FILE)


def load_imap_config(env: dict[str, str] | None = None) -> ImapConfig:
    """Load IMAP settings. App-password spaces (Gmail's display form) are stripped."""
    if env is None:
        load_dotenv_if_present()
        env = os.environ

    address = (env.get("EMAIL_ADDRESS") or "").strip()
    auth_method = (env.get("EMAIL_AUTH_METHOD") or AUTH_OAUTH2).strip().lower() or AUTH_OAUTH2
    token_file = (
        (env.get("GMAIL_OAUTH_TOKEN_FILE") or "").strip() or str(DEFAULT_TOKEN_FILE)
    )
    password = (env.get("EMAIL_APP_PASSWORD") or "").replace(" ", "").strip()
    host = (env.get("IMAP_SERVER") or DEFAULT_IMAP_HOST).strip() or DEFAULT_IMAP_HOST
    folder = (env.get("IMAP_FOLDER") or DEFAULT_FOLDER).strip() or DEFAULT_FOLDER
    try:
        port = int((env.get("IMAP_PORT") or str(DEFAULT_IMAP_PORT)).strip())
    except ValueError as exc:
        raise MailboxConfigError("IMAP_PORT must be an integer.") from exc

    if auth_method not in AUTH_METHODS:
        raise MailboxConfigError(
            f"EMAIL_AUTH_METHOD must be one of: {', '.join(AUTH_METHODS)}."
        )
    if not address or address.startswith("your_email@"):
        raise MailboxConfigError(
            "EMAIL_ADDRESS is missing. Set your Gmail address in the .env file."
        )
    if auth_method == AUTH_APP_PASSWORD and (not password or password.startswith("replace_")):
        raise MailboxConfigError(
            "EMAIL_APP_PASSWORD is missing. Set a Gmail App Password in the .env file."
        )
    return ImapConfig(
        address=address,
        password=password if auth_method == AUTH_APP_PASSWORD else "",
        host=host,
        port=port,
        folder=folder,
        auth_method=auth_method,
        oauth_token_file=token_file,
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
    if config.auth_method == AUTH_OAUTH2:
        try:
            access_token = get_access_token(config.oauth_token_file)
        except GmailOAuthError as exc:
            raise MailboxConfigError(str(exc)) from exc
        auth_string = build_xoauth2_string(config.address, access_token).encode("utf-8")

    client = imaplib.IMAP4_SSL(config.host, config.port)
    try:
        if config.auth_method == AUTH_OAUTH2:
            client.authenticate("XOAUTH2", lambda _challenge: auth_string)
        else:
            client.login(config.address, config.password)
    except imaplib.IMAP4.error as exc:
        try:
            client.shutdown()
        except Exception:
            pass
        if config.auth_method == AUTH_OAUTH2:
            raise MailboxError(
                "IMAP XOAUTH2 login failed. Check that EMAIL_ADDRESS is the Google "
                "account you authorized and that IMAP is enabled in Gmail settings."
            ) from exc
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
