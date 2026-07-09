"""Read a local ``.eml`` file and extract its key fields as a dict.

Offline only — this module never opens a network connection. It uses the
standard-library :mod:`email` package to parse the message, prefers a
``text/plain`` body, and falls back to converting an HTML-only body into
readable plain text using a small standard-library HTML parser.

Public API::

    read_eml(path) -> dict

The returned dict has the keys ``message_id``, ``sender``, ``subject``,
``date``, ``bodytext`` and ``sourcepath``.
"""

from __future__ import annotations

import email
import logging
import re
from email import policy
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path

log = logging.getLogger(__name__)

# Block-level tags that should introduce a line break in the plain-text output.
_BLOCK_TAGS = {
    "p", "br", "div", "tr", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "blockquote", "section", "article", "ul", "ol", "table",
}


class _HTMLToText(HTMLParser):
    """Minimal offline HTML -> plain-text converter (stdlib only).

    Tags are dropped; a newline is inserted around block-level elements so
    paragraphs stay separate; runs of whitespace are collapsed. With
    ``convert_charrefs=True`` (the default) HTML entities such as ``&amp;``
    are turned into their characters inside :meth:`handle_data`.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_data(self, data: str) -> None:
        self._pieces.append(data)

    def get_text(self) -> str:
        raw = "".join(self._pieces)
        # Normalise each line, then collapse repeated blank lines into one.
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        cleaned: list[str] = []
        prev_blank = False
        for line in lines:
            if line == "":
                if not prev_blank:
                    cleaned.append("")
                prev_blank = True
            else:
                cleaned.append(line)
                prev_blank = False
        return "\n".join(cleaned).strip()


def _html_to_text(html: str) -> str:
    """Convert an HTML string into readable plain text (offline)."""
    parser = _HTMLToText()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def _part_text(part: Message) -> str:
    """Safely extract a ``str`` from a text part — never raises."""
    try:
        return part.get_content()
    except Exception:
        # Fallback for unusual charsets: decode the raw payload manually.
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")


def _best_text_body(message: Message) -> str:
    """Return the most readable plain-text body from *message*.

    Preference order:
      1. the first ``text/plain`` part,
      2. an HTML part converted to plain text,
      3. an empty string if nothing readable exists (never raises).
    Attachments are skipped.
    """
    plain: str | None = None
    html: str | None = None

    def consider(part: Message) -> None:
        nonlocal plain, html
        disposition = str(part.get_content_disposition() or "").lower()
        if disposition == "attachment":
            return
        ctype = part.get_content_type()
        if ctype == "text/plain" and plain is None:
            plain = _part_text(part)
        elif ctype == "text/html" and html is None:
            html = _part_text(part)

    if message.is_multipart():
        for part in message.walk():
            consider(part)
    else:
        consider(message)

    if plain is not None:
        return plain
    if html is not None:
        return _html_to_text(html)
    return ""


def read_eml(path: str | Path) -> dict:
    """Read the ``.eml`` file at *path* and return the extracted fields.

    Returns a dict with keys: ``message_id``, ``sender``, ``subject``,
    ``date``, ``bodytext``, ``sourcepath``. Only a short metadata summary is
    logged — the full body is never printed (requirement #6).
    """
    eml_path = Path(path)
    with eml_path.open("rb") as handle:
        message = email.message_from_binary_file(handle, policy=policy.default)

    # Headers may be missing; default to empty strings.
    message_id = (message.get("Message-ID") or "").strip()
    sender = (message.get("From") or "").strip()
    subject = (message.get("Subject") or "").strip()
    date = (message.get("Date") or "").strip()
    bodytext = _best_text_body(message)

    # Log a concise summary only — never the entire body.
    preview = " ".join(bodytext.split())[:60]
    log.info(
        "read %s | subject=%r | sender=%r | body_chars=%d | preview=%r",
        eml_path.name, subject, sender, len(bodytext), preview,
    )

    return {
        "message_id": message_id,
        "sender": sender,
        "subject": subject,
        "date": date,
        "bodytext": bodytext,
        "sourcepath": str(eml_path),
    }


if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python -m app.sample_email_reader <path-to.eml>", file=sys.stderr)
        sys.exit(2)

    result = read_eml(sys.argv[1])
    # Print metadata only — omit bodytext to honor requirement #6.
    summary = {key: value for key, value in result.items() if key != "bodytext"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
