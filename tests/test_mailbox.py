"""Tests for the IMAP mailbox connector (no live network)."""

from pathlib import Path

import pytest

from app.mailbox import (
    MailboxConfigError,
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


def test_load_imap_config_requires_password():
    with pytest.raises(MailboxConfigError, match="EMAIL_APP_PASSWORD"):
        load_imap_config({"EMAIL_ADDRESS": "parent@gmail.com"})


def test_load_imap_config_strips_spaces_and_defaults_gmail():
    cfg = load_imap_config(
        {
            "EMAIL_ADDRESS": " parent@gmail.com ",
            "EMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",
        }
    )
    assert cfg.address == "parent@gmail.com"
    assert cfg.password == "abcdefghijklmnop"
    assert cfg.host == "imap.gmail.com"
    assert cfg.port == 993
    assert cfg.folder == "INBOX"


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
