"""Security helpers for email duplicate prevention.

Scope: this module handles **email fingerprinting only** — loading the
``EMAIL_FINGERPRINT_SECRET`` and computing an HMAC-SHA256 digest of an email's
identity so the same message is recognised across runs.

Out of scope: OAuth / access / refresh tokens are **never** hashed or salted
here. Those tokens must remain usable (plaintext) and are stored separately as
secrets — see requirement #7. Do not add token-handling code to this module.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

# Environment variable names we accept. The snake_case form is canonical
# (requirement #4); the no-underscore form is accepted as an alias
# (requirement #1) so either spelling in .env works.
SECRET_ENV_VARS = ("EMAIL_FINGERPRINT_SECRET", "EMAILFINGERPRINTSECRET")

# Minimum secret length (256-bit-ish). Requirement #8.
MIN_SECRET_LENGTH = 32


class SecurityConfigError(Exception):
    """Raised when the fingerprint secret is missing or too short."""


def load_dotenv_if_present(path: str | Path = ".env") -> None:
    """Load variables from a ``.env`` file into ``os.environ``.

    No-op if the file is absent or python-dotenv is not installed.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if Path(path).exists():
        load_dotenv(str(path), override=False)


def get_fingerprint_secret(env: dict[str, str] | None = None) -> str:
    """Return the email fingerprint secret.

    Reads from *env* when given (useful for tests); otherwise loads ``.env``
    and reads ``os.environ``. Accepts either :data:`SECRET_ENV_VARS` spelling.

    Raises :class:`SecurityConfigError` if the secret is absent or shorter
    than :data:`MIN_SECRET_LENGTH` characters (requirement #8).
    """
    if env is None:
        load_dotenv_if_present()
        env = os.environ

    secret: str | None = None
    for name in SECRET_ENV_VARS:
        value = env.get(name)
        if value:
            secret = value.strip()
            break

    if not secret:
        raise SecurityConfigError(
            "Email fingerprint secret not found. Set "
            f"{SECRET_ENV_VARS[0]} (>= {MIN_SECRET_LENGTH} characters) in your "
            ".env file or environment."
        )
    if len(secret) < MIN_SECRET_LENGTH:
        raise SecurityConfigError(
            f"{SECRET_ENV_VARS[0]} is too short: must be >= {MIN_SECRET_LENGTH} "
            f"characters, got {len(secret)}. Generate a long random string."
        )
    return secret


def hmac_sha256(secret: str, message: str | bytes) -> str:
    """Return the hex HMAC-SHA256 digest of *message* keyed by *secret*.

    This is for **email identity** strings only — never pass OAuth/access/
    refresh tokens here (requirement #7).
    """
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    msg = message.encode("utf-8") if isinstance(message, str) else message
    return hmac.new(key, msg, hashlib.sha256).hexdigest()
