"""Gmail OAuth 2.0 for IMAP XOAUTH2 login.

One-time authorization (opens a browser, run from repo root)::

    python -m app.gmail_oauth

This reads the Google OAuth *Desktop app* client file and saves the resulting
refresh token to the token file. Later IMAP sessions refresh the short-lived
access token automatically.

Config (``.env``)::

    GMAIL_OAUTH_CLIENT_FILE=.secrets/google_oauth_client.json
    GMAIL_OAUTH_TOKEN_FILE=.secrets/gmail_token.json

Tokens are stored as usable plaintext secrets (never hashed, see
:mod:`app.security`) and are never printed or written to ``runtime/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .security import load_dotenv_if_present

# IMAP access requires the full Gmail scope; gmail.readonly does not cover IMAP.
SCOPES = ["https://mail.google.com/"]

DEFAULT_CLIENT_FILE = Path(".secrets/google_oauth_client.json")
DEFAULT_TOKEN_FILE = Path(".secrets/gmail_token.json")

AUTHORIZE_HINT = "Run `python -m app.gmail_oauth` to authorize Gmail."


class GmailOAuthError(Exception):
    """Raised when OAuth credentials are missing, invalid, or cannot refresh."""


def _save_credentials(creds: Credentials, token_file: str | Path) -> None:
    path = Path(token_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    path.chmod(0o600)


def load_credentials(token_file: str | Path = DEFAULT_TOKEN_FILE) -> Credentials:
    """Load saved credentials, refreshing (and re-saving) the access token if needed."""
    path = Path(token_file)
    if not path.is_file():
        raise GmailOAuthError(f"Gmail OAuth token not found at {path}. {AUTHORIZE_HINT}")

    try:
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    except (ValueError, OSError) as exc:
        raise GmailOAuthError(f"Gmail OAuth token file is invalid. {AUTHORIZE_HINT}") from exc

    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise GmailOAuthError(f"Gmail OAuth token has no refresh token. {AUTHORIZE_HINT}")

    try:
        creds.refresh(Request())
    except RefreshError as exc:
        # Revoked, expired (7-day limit for apps in Google "Testing" status), or wrong client.
        raise GmailOAuthError(f"Gmail OAuth refresh was rejected. {AUTHORIZE_HINT}") from exc
    _save_credentials(creds, path)
    return creds


def get_access_token(token_file: str | Path = DEFAULT_TOKEN_FILE) -> str:
    """Return a currently valid Gmail access token."""
    return load_credentials(token_file).token


def build_xoauth2_string(address: str, access_token: str) -> str:
    """Return the SASL XOAUTH2 initial client response (before base64)."""
    return f"user={address}\x01auth=Bearer {access_token}\x01\x01"


def authorize(
    client_file: str | Path = DEFAULT_CLIENT_FILE,
    token_file: str | Path = DEFAULT_TOKEN_FILE,
    login_hint: str | None = None,
) -> Credentials:
    """Run the browser consent flow and save the refresh token."""
    client_path = Path(client_file)
    if not client_path.is_file():
        raise GmailOAuthError(
            f"Google OAuth client file not found at {client_path}. Download the "
            "Desktop app client JSON from Google Cloud Console and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    extra = {"prompt": "consent"}
    if login_hint:
        extra["login_hint"] = login_hint
    creds = flow.run_local_server(port=0, **extra)
    if not creds.refresh_token:
        raise GmailOAuthError("Google did not return a refresh token. Try authorizing again.")
    _save_credentials(creds, token_file)
    return creds


def main() -> int:
    load_dotenv_if_present()
    client_file = os.environ.get("GMAIL_OAUTH_CLIENT_FILE") or str(DEFAULT_CLIENT_FILE)
    token_file = os.environ.get("GMAIL_OAUTH_TOKEN_FILE") or str(DEFAULT_TOKEN_FILE)
    address = (os.environ.get("EMAIL_ADDRESS") or "").strip()
    login_hint = None if not address or address.startswith("your_email@") else address

    try:
        authorize(client_file, token_file, login_hint=login_hint)
    except GmailOAuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Gmail authorized. Refresh token saved to {token_file}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
