"""Detect school terminology in normalized email dictionaries.

Works against the output of ``app.sample_email_reader.read_eml`` (dicts with
``subject`` and ``bodytext``). Matching is:

* searched across **both** subject and body,
* **case-insensitive**,
* **whole-word** (using regex word boundaries), so a short acronym like ``AP``
  does NOT fire inside unrelated words such as "application",
* **de-duplicated** by term,
* returns the **complete** term objects (term/zh/explanation/category/priority).

No LLM is used in this step — it is pure string/regex matching.
"""

from __future__ import annotations

import re

from .term_store import TermStore, load_terms


def _term_matches(term: str, text: str) -> bool:
    """True if *term* appears in *text* as a whole word/phrase.

    An optional trailing ``s`` is allowed so plurals such as
    "Progress Reports" still match. Words in a multi-word term may be separated
    by any whitespace, since email bodies are often hard-wrapped mid-phrase.
    """
    phrase = r"\s+".join(re.escape(word) for word in term.split())
    pattern = r"\b" + phrase + r"s?\b"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def detect_terms(subject: str, bodytext: str, terms) -> list[dict]:
    """Return the full term objects matched in *subject* and/or *bodytext*.

    *terms* may be a :class:`TermStore` or a plain list of term dicts. Results
    keep the index order and are de-duplicated by ``term``.
    """
    # Accept either a TermStore or a raw list of term dicts.
    term_list = terms.terms if isinstance(terms, TermStore) else terms

    haystack = f"{subject or ''}\n{bodytext or ''}"
    seen: set[str] = set()
    hits: list[dict] = []
    for entry in term_list:
        term = entry.get("term", "")
        if not term or term in seen:
            continue
        if _term_matches(term, haystack):
            seen.add(term)
            hits.append(entry)
    return hits


def detect_from_email(email: dict, terms) -> list[dict]:
    """Convenience wrapper: detect terms from a normalized email dict."""
    return detect_terms(
        subject=email.get("subject") or "",
        bodytext=email.get("bodytext") or "",
        terms=terms,
    )


if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="app.term_detector",
        description="Detect terminology in a normalized .eml via sample_email_reader.",
    )
    parser.add_argument("input", help="Path to a .eml file.")
    parser.add_argument(
        "--terms", default=str("config/terms.json"), help="Path to terms.json."
    )
    args = parser.parse_args()

    from .sample_email_reader import read_eml

    store = TermStore(args.terms)
    email = read_eml(Path(args.input))
    matched = detect_from_email(email, store)
    print(json.dumps(matched, ensure_ascii=False, indent=2))
    print(f"({len(matched)} term(s) matched)", file=sys.stderr)
