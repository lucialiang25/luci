"""Step 3 — Terminology detection driven by ``config/terms.json``.

``terms.json`` is a JSON **array** of objects, each shaped like::

    {
      "term": "Progress Report",
      "zh": "进度报告",
      "explanation": "...",
      "category": "grades",
      "priority": 1
    }
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TERMS_PATH = Path("config/terms.json")


def load_terms(path: Path = TERMS_PATH) -> list[dict]:
    """Load and return the terminology index (a list of term objects)."""
    return json.loads(path.read_text(encoding="utf-8"))


def detect_terms(text: str, terms: list[dict]) -> list[dict]:
    """Return term objects whose ``term`` appears in ``text`` as a whole word.

    Matching is case-insensitive and uses word boundaries (``\\b``) so short
    acronyms do not fire inside unrelated words — e.g. ``ACT`` will NOT match
    "cont**act**". An optional trailing "s" is allowed so plurals such as
    "Progress Reports" still match. Hits are de-duplicated by term and sorted
    by ``priority`` (1 = most important) then alphabetically.
    """
    seen: set[str] = set()
    hits: list[dict] = []
    for entry in terms:
        term = entry.get("term", "")
        if not term or term in seen:
            continue
        # \b ... s? \b  → whole-word/phrase, optionally plural, case-insensitive.
        pattern = r"\b" + re.escape(term) + r"s?\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            seen.add(term)
            hits.append(entry)
    hits.sort(key=lambda e: (e.get("priority", 99), e.get("term", "").lower()))
    return hits
