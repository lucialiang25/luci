"""Tests for the IMAP mailbox connector (no live network)."""

import imaplib
from pathlib import Path

import pytest

from app import mailbox
from app.gmail_oauth import GmailOAuthError
from app.mailbox import (
    MailboxConfigError,
    MailboxError,
    connect,
    extract_rfc822,
    fetch_message,
    list_messages,
    load_imap_config,
)

SAMPLE = Path("data/sample_emails/progress_report.eml").read_bytes()
CLUB = Path("data/sample_emails/club_activity.eml").read_bytes()


class FakeIMAP:
    """Minimal imaplib-shaped client used by the mailbox helpers."""

    def __init__(self, messages: dict[str, bytes]) -> None:
        self.messages = messages
        self.selected: str | None = None

    def select(self, folder: str, readonly: bool = True):
        self.selected = folder
        return "OK", [str(len(self.messages)).encode()]

    def uid(self, command: str, *args):
        cmd = command.upper()
        if cmd == "SEARCH":
            joined = b" ".join(uid.encode() for uid in self.messages)
            return "OK", [joined]
        if cmd == "FETCH":
            uid = args[0]
            if isinstance(uid, bytes):
                uid = uid.decode()
            raw = self.messages[str(uid)]
            header = f"{uid} (UID {uid} RFC822 {{{len(raw)}}}".encode()
            return "OK", [(header, raw), b")"]
        raise AssertionError(f"unexpected IMAP uid command: {command!r}")


def test_load_imap_config_requires_address():
    with pytest.raises(MailboxConfigError, match="EMAIL_ADDRESS"):
        load_imap_config({"EMAIL_APP_PASSWORD": "x" * 16})


def test_load_imap_config_defaults_to_oauth2_without_password():
    cfg = load_imap_config({"EMAIL_ADDRESS": " parent@gmail.com "})
    assert cfg.address == "parent@gmail.com"
    assert cfg.auth_method == "oauth2"
    assert cfg.password == ""
    assert cfg.oauth_token_file == ".secrets/gmail_token.json"
    assert cfg.host == "imap.gmail.com"
    assert cfg.port == 993
    assert cfg.folder == "INBOX"


def test_load_imap_config_rejects_unknown_auth_method():
    with pytest.raises(MailboxConfigError, match="EMAIL_AUTH_METHOD"):
        load_imap_config({"EMAIL_ADDRESS": "parent@gmail.com", "EMAIL_AUTH_METHOD": "basic"})


def test_load_imap_config_app_password_requires_password():
    with pytest.raises(MailboxConfigError, match="EMAIL_APP_PASSWORD"):
        load_imap_config(
            {"EMAIL_ADDRESS": "parent@gmail.com", "EMAIL_AUTH_METHOD": "app_password"}
        )


def test_load_imap_config_app_password_strips_spaces():
    cfg = load_imap_config(
        {
            "EMAIL_ADDRESS": "parent@gmail.com",
            "EMAIL_AUTH_METHOD": "app_password",
            "EMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",
        }
    )
    assert cfg.auth_method == "app_password"
    assert cfg.password == "abcdefghijklmnop"


class FakeSSL:
    """Records how connect() authenticates instead of opening a socket."""

    def __init__(self, host, port, fail=False):
        self.host, self.port, self.fail = host, port, fail
        self.auth = None
        self.closed = False

    def authenticate(self, mechanism, authobject):
        self.auth = (mechanism, authobject(b""))
        if self.fail:
            raise imaplib.IMAP4.error("AUTHENTICATE failed")
        return "OK", [b"Success"]

    def login(self, user, password):
        self.auth = ("LOGIN", user, password)
        return "OK", [b"Success"]

    def shutdown(self):
        self.closed = True


def test_connect_oauth2_uses_xoauth2(monkeypatch):
    created = []
    monkeypatch.setattr(
        mailbox.imaplib, "IMAP4_SSL", lambda h, p: created.append(FakeSSL(h, p)) or created[-1]
    )
    monkeypatch.setattr(mailbox, "get_access_token", lambda token_file: "ya29.test")

    client = connect(load_imap_config({"EMAIL_ADDRESS": "parent@gmail.com"}))

    assert client is created[0]
    assert client.auth == (
        "XOAUTH2",
        b"user=parent@gmail.com\x01auth=Bearer ya29.test\x01\x01",
    )


def test_connect_oauth2_missing_token_is_config_error(monkeypatch):
    def no_token(token_file):
        raise GmailOAuthError("Gmail OAuth token not found. Run `python -m app.gmail_oauth`.")

    monkeypatch.setattr(mailbox, "get_access_token", no_token)
    monkeypatch.setattr(
        mailbox.imaplib, "IMAP4_SSL", lambda h, p: pytest.fail("must not open a socket")
    )
    with pytest.raises(MailboxConfigError, match="app.gmail_oauth"):
        connect(load_imap_config({"EMAIL_ADDRESS": "parent@gmail.com"}))


def test_connect_oauth2_rejected_closes_socket(monkeypatch):
    created = []
    monkeypatch.setattr(
        mailbox.imaplib,
        "IMAP4_SSL",
        lambda h, p: created.append(FakeSSL(h, p, fail=True)) or created[-1],
    )
    monkeypatch.setattr(mailbox, "get_access_token", lambda token_file: "ya29.test")

    with pytest.raises(MailboxError, match="XOAUTH2") as excinfo:
        connect(load_imap_config({"EMAIL_ADDRESS": "parent@gmail.com"}))
    assert created[0].closed
    assert "ya29.test" not in str(excinfo.value)


def test_extract_rfc822_from_imaplib_fetch_tuple():
    payload = extract_rfc822(
        [(b"12 (UID 12 RFC822 {24}", b"From: a@b.com\r\n\r\nHi"), b")"]
    )
    assert payload == b"From: a@b.com\r\n\r\nHi"


def test_list_messages_newest_first_with_limit():
    client = FakeIMAP({"1": SAMPLE, "2": CLUB})
    listed = list_messages(client, limit=1)
    assert len(listed) == 1
    assert listed[0]["uid"] == "2"
    assert "Club" in listed[0]["subject"]
    assert "bodytext" not in listed[0]


def test_fetch_message_normalizes_to_shared_email_dict():
    client = FakeIMAP({"42": SAMPLE})
    email = fetch_message(client, "42")
    assert email["sourcepath"] == "imap://INBOX/uid/42"
    assert email["subject"] == "Progress Report Available on PowerSchool"
    assert "PowerSchool" in email["bodytext"]
    assert email["sender"].startswith("Academic Office")
