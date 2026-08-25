"""Tests for shared .eml / RFC822 parsing."""

from pathlib import Path

from app.sample_email_reader import read_eml, read_eml_bytes

SAMPLE = Path("data/sample_emails/progress_report.eml")


def test_read_eml_bytes_matches_file_reader():
    raw = SAMPLE.read_bytes()
    from_file = read_eml(SAMPLE)
    from_bytes = read_eml_bytes(raw, sourcepath="imap://INBOX/uid/42")

    assert from_bytes["message_id"] == from_file["message_id"]
    assert from_bytes["sender"] == from_file["sender"]
    assert from_bytes["subject"] == from_file["subject"]
    assert from_bytes["date"] == from_file["date"]
    assert from_bytes["bodytext"] == from_file["bodytext"]
    assert from_bytes["sourcepath"] == "imap://INBOX/uid/42"
    assert "Progress Report" in from_bytes["subject"]
    assert "PowerSchool" in from_bytes["bodytext"]
