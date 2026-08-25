"""Pipeline runner for SchoolMail Bridge (sample files + live IMAP).

Orchestrates the project's canonical building blocks:

* :mod:`app.sample_email_reader`              — parse a local ``.eml``
* :mod:`app.mailbox`                          — Gmail/IMAP list + fetch
* :mod:`app.security` / :mod:`app.email_identity` / :mod:`app.processed_store`
                                              — secure HMAC duplicate prevention
* :mod:`app.term_store` / :mod:`app.term_detector`
                                              — terminology detection

and adds MiniMax translation (with offline placeholder fallback) plus Markdown rendering.

Run::

    python -m app.pipeline --source sample [path.eml]
    python -m app.pipeline --source live --list
    python -m app.pipeline --source live --uid 123

Steps:
  1. load email (local .eml or live IMAP)
  2. HMAC duplicate fingerprint check (skip if already processed)
  3. save original email fields -> runtime/origin_messages/
  4. terminology detection (config/terms.json)
  5. MiniMax translation (fallback to offline placeholder on failure)
  6. save translated artifact -> runtime/translated_messages/
  7. render parent-facing Markdown
  8. append rendered message -> runtime/push_log.jsonl
  9. mark processed ONLY after origin + artifact + log succeed

Constraints honoured: never write the raw Message-ID or API keys to runtime files;
no WeCom webhook in this phase.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from .ai_translator import translate_email
from .email_identity import compute_fingerprint_from_email
from .mailbox import (
    MailboxConfigError,
    MailboxError,
    fetch_message,
    imap_session,
    list_messages,
)
from .processed_store import is_processed, mark_processed
from .sample_email_reader import read_eml
from .security import SecurityConfigError, get_fingerprint_secret
from .term_detector import detect_from_email
from .term_store import TermStore

DEFAULT_INPUT = Path("data/sample_emails/progress_report.eml")
TRANSLATED_DIR = Path("runtime/translated_messages")
ORIGIN_DIR = Path("runtime/origin_messages")
PUSH_LOG_PATH = Path("runtime/push_log.jsonl")


def save_origin_message(email: dict, fingerprint: str) -> Path:
    """Save the original email fields under ``runtime/origin_messages/``.

    Persists sender/subject/date/bodytext/sourcepath plus the fingerprint.
    The raw Message-ID is intentionally omitted (project privacy constraint).
    """
    ORIGIN_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "fingerprint": fingerprint,
        "sender": email.get("sender") or "",
        "subject": email.get("subject") or "",
        "date": email.get("date") or "",
        "bodytext": email.get("bodytext") or "",
        "sourcepath": email.get("sourcepath") or "",
    }
    path = ORIGIN_DIR / f"{fingerprint}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def render_markdown(translation: dict, fingerprint: str) -> str:
    """Render a parent-facing Markdown message.

    Only the salted ``fingerprint`` is referenced — the raw Message-ID is never
    written out (project constraint).
    """
    lines = [
        f"# {translation['subject_zh']}",
        "",
        f"> 来源指纹（用于去重）：`{fingerprint}`",
        "",
        "## 摘要",
        translation["summary_zh"],
        "",
        "## 涉及术语",
    ]
    terms = translation.get("terms", [])
    if terms:
        for t in terms:
            label = t.get("zh") or t.get("term", "")
            entry = f"- **{t.get('term', '')}** — {label}"
            if t.get("explanation"):
                entry += f"：{t['explanation']}"
            lines.append(entry)
    else:
        lines.append("- （未检测到相关术语）")

    if translation.get("engine") == "minimax":
        model = translation.get("model") or "MiniMax"
        lines += ["", f"_（由 {model} 翻译生成，正式发布前请人工校对。）_"]
    else:
        lines += ["", "_（本消息为离线占位翻译，正式发布前请人工校对。）_"]
    return "\n".join(lines)


def save_translation_artifact(translation: dict, fingerprint: str) -> Path:
    """Step 5 — save the structured translation as a JSON artifact."""
    TRANSLATED_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {"fingerprint": fingerprint, "translation": translation}
    path = TRANSLATED_DIR / f"{fingerprint}.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_push_log(fingerprint: str, rendered_markdown: str, artifact_path: Path) -> None:
    """Step 7 — append the rendered parent-facing message to the push log."""
    PUSH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "fingerprint": fingerprint,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "artifact_path": str(artifact_path),
        "message": rendered_markdown,
    }
    with PUSH_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_pipeline_on_email(email: dict, secret: str | None = None) -> dict:
    """Run the pipeline on a normalized email dict (sample or live)."""
    if secret is None:
        secret = get_fingerprint_secret()
    fingerprint = compute_fingerprint_from_email(email, secret)
    if is_processed(fingerprint):
        return {
            "status": "duplicate",
            "fingerprint": fingerprint,
            "message": "Email already processed — skipped.",
        }

    origin_path = save_origin_message(email, fingerprint)
    detected = detect_from_email(email, TermStore())
    translation = translate_email(email["subject"], email["bodytext"], detected)
    artifact_path = save_translation_artifact(translation, fingerprint)
    rendered = render_markdown(translation, fingerprint)
    append_push_log(fingerprint, rendered, artifact_path)
    mark_processed(fingerprint, artifact_path=str(artifact_path))

    return {
        "status": "processed",
        "fingerprint": fingerprint,
        "origin_path": str(origin_path),
        "artifact_path": str(artifact_path),
        "detected_terms": [t["term"] for t in detected],
    }


def run_pipeline(eml_path: Path, secret: str | None = None) -> dict:
    """Run the full offline pipeline for one ``.eml`` file. Returns a summary."""
    return run_pipeline_on_email(read_eml(eml_path), secret=secret)


def _print_result(result: dict) -> None:
    print("Pipeline result:")
    for key, value in result.items():
        print(f"  {key}: {value}")


def _run_live(args: argparse.Namespace) -> int:
    if not args.list and not args.uid:
        print(
            "ERROR: live mode requires --list or --uid <imap-uid>.",
            file=sys.stderr,
        )
        return 1

    try:
        with imap_session() as (client, cfg):
            if args.list:
                messages = list_messages(client, folder=cfg.folder, limit=args.limit)
                if not messages:
                    print("Inbox is empty.")
                    return 0
                print(f"{'UID':>8}  {'DATE':<32}  SUBJECT")
                for item in messages:
                    subject = (item.get("subject") or "(no subject)")[:80]
                    date = (item.get("date") or "")[:32]
                    print(f"{item['uid']:>8}  {date:<32}  {subject}")
                return 0

            email = fetch_message(client, args.uid, folder=cfg.folder)
            result = run_pipeline_on_email(email)
    except (MailboxConfigError, MailboxError, SecurityConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_result(result)
    return 0


def _run_sample(args: argparse.Namespace) -> int:
    eml_path = Path(args.input)
    if not eml_path.is_file():
        print(f"ERROR: input not found: {eml_path}", file=sys.stderr)
        return 1
    try:
        result = run_pipeline(eml_path)
    except SecurityConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _print_result(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(
        prog="app.pipeline",
        description="SchoolMail Bridge pipeline runner (sample .eml or live IMAP).",
    )
    cli.add_argument(
        "--source",
        choices=("sample", "live"),
        default="sample",
        help="Email source: local sample file or live IMAP mailbox (default: sample).",
    )
    cli.add_argument(
        "input",
        nargs="?",
        default=str(DEFAULT_INPUT),
        help=f"Path to the .eml file when --source sample (default: {DEFAULT_INPUT}).",
    )
    cli.add_argument(
        "--list",
        action="store_true",
        help="Live mode: list recent inbox messages (UID + subject).",
    )
    cli.add_argument(
        "--uid",
        help="Live mode: fetch and process one message by IMAP UID.",
    )
    cli.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Live --list: max messages to show (default: 20).",
    )
    args = cli.parse_args(argv)

    if args.source == "live":
        return _run_live(args)
    return _run_sample(args)


if __name__ == "__main__":
    sys.exit(main())
