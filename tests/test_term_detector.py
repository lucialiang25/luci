"""Tests for terminology detection against config/terms.json."""

from app.term_detector import detect_terms
from app.term_store import TermStore


def _detected(subject: str, body: str) -> list[str]:
    return [t["term"] for t in detect_terms(subject, body, TermStore())]


def test_detects_athletics_terms_in_team_schedule():
    found = _detected(
        "September 28–October 3",
        "Our Varsity game has been rescheduled.\n"
        "JV Practice: 3:45–5:15 p.m.\n"
        "Duty Roster: Water: Lucia\n"
        "We still need items for the concession stand. Go Wildcats! Field Hockey",
    )
    for term in ("Varsity", "JV", "Duty Roster", "Concession Stand", "Field Hockey"):
        assert term in found


def test_multi_word_terms_match_across_line_wraps():
    found = _detected(
        "Reminder",
        "Please remember that we still need the following items for the concession\r\n"
        "stand. Your Progress\nReport is ready.",
    )
    assert "Concession Stand" in found
    assert "Progress Report" in found


def test_short_acronyms_do_not_match_inside_words():
    found = _detected("Adjustment", "Our juvenile application deadline")
    assert "JV" not in found
    assert "AP" not in found
