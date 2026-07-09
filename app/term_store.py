"""Load and manage the terminology index (``config/terms.json``).

The index is a JSON array of objects, each with the fields::

    term        str   English label, used as the match key
    zh          str   Chinese translation shown to parents
    explanation str   Short Chinese explanation
    category    str   Grouping, e.g. "grades", "testing"
    priority    int   1 = most important

``TermStore`` reads the file once, validates that every entry has all the
required fields, and exposes the list for the detector. It can also write the
list back to disk.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_TERMS_PATH = Path("config/terms.json")

# Every term object must carry these keys to be usable.
REQUIRED_FIELDS = ("term", "zh", "explanation", "category", "priority")


class TermStore:
    """A small read-mostly store around the terms.json index."""

    def __init__(self, path: str | Path = DEFAULT_TERMS_PATH) -> None:
        self.path = Path(path)
        self._terms: list[dict] = []

    def load(self) -> list[dict]:
        """Load terms from disk, keeping only entries with all required fields.

        Raises ``ValueError`` if the file does not contain a JSON array.
        """
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(
                f"{self.path}: expected a JSON array of term objects"
            )
        terms: list[dict] = []
        for entry in data:
            if isinstance(entry, dict) and all(field in entry for field in REQUIRED_FIELDS):
                terms.append(entry)
        self._terms = terms
        return terms

    @property
    def terms(self) -> list[dict]:
        """Return the loaded terms, loading lazily on first access."""
        if not self._terms:
            self.load()
        return self._terms

    def save(self, terms: list[dict]) -> None:
        """Write *terms* back to disk (pretty-printed, UTF-8)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(terms, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._terms = list(terms)

    def find(self, term: str) -> dict | None:
        """Return the term object whose ``term`` matches *term*, or ``None``."""
        for entry in self.terms:
            if entry.get("term") == term:
                return entry
        return None


def load_terms(path: str | Path = DEFAULT_TERMS_PATH) -> list[dict]:
    """Convenience helper: load and return the validated term list from *path*."""
    return TermStore(path).load()
