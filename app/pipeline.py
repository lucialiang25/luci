"""Offline pipeline runner for SchoolMail Bridge (single file).

Orchestrates the project's canonical building blocks:

* :mod:`app.sample_email_reader`              — parse a local ``.eml``
* :mod:`app.security` / :mod:`app.email_identity` / :mod:`app.processed_store`
                                              — secure HMAC duplicate prevention
* :mod:`app.term_store` / :mod:`app.term_detector`
                                              — terminology detection

and adds an inline **fake** translator and Markdown renderer (no real LLM).

Run::

    EMAIL_FINGERPRINT_SECRET=<32+ char secret> python -m app.pipeline [path.eml]

Steps:
  1. parse local email
  2. HMAC duplicate fingerprint check (skip if already processed)
  3. terminology detection (config/terms.json)
  4. fake structured Chinese placeholder translation
  5. save translated artifact -> runtime/translated_messages/
  6. render parent-facing Markdown
  7. append rendered message -> runtime/push_log.jsonl
  8. mark processed ONLY after 5 and 7 succeed

Constraints honoured: no real LLM, no mailbox, no WeCom webhook, and the raw
Message-ID is never written to any runtime file (only its HMAC fingerprint is).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from .email_identity import compute_fingerprint_from_email
from .processed_store import is_processed, mark_processed
from .sample_email_reader import read_eml
from .security import SecurityConfigError, get_fingerprint_secret
from .term_detector import detect_from_email
from .term_store import TermStore

DEFAULT_INPUT = Path("data/sample_emails/progress_report.eml")
TRANSLATED_DIR = Path("runtime/translated_messages")
PUSH_LOG_PATH = Path("runtime/push_log.jsonl")


def fake_translate(subject: str, bodytext: str, detected_terms: list[dict]) -> dict:
    """Return STRUCTURED Chinese placeholder output (requirement #4, no real LLM)."""
    terms_out = [
        {
            "term": t.get("term", ""),
            "zh": t.get("zh", ""),
            "explanation": t.get("explanation", ""),
            "category": t.get("category", ""),
            "priority": t.get("priority", 99),
        }
        for t in detected_terms
    ]
    return {
        "engine": "offline-placeholder",
        "warning": "PLACEHOLDER_TRANSLATION_NOT_REAL — human review required",
        "subject_zh": f"【占位翻译】{subject}",
        "summary_zh": (
            "（占位）这是一份离线生成的摘要，未经真实翻译引擎处理。"
            f"原文主题：{subject}。请家长以学校英文原件为准。"
        ),
        "terms": terms_out,
    }


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
        lines.append("- （未检测到关键术语）")
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


def run_pipeline(eml_path: Path, secret: str | None = None) -> dict:
    """Run the full offline pipeline for one ``.eml`` file. Returns a summary."""
    # --- Step 1: parse the local email --------------------------------
    email = read_eml(eml_path)

    # --- Step 2: HMAC duplicate fingerprint check ---------------------
    if secret is None:
        secret = get_fingerprint_secret()
    fingerprint = compute_fingerprint_from_email(email, secret)
    if is_processed(fingerprint):
        return {
            "status": "duplicate",
            "fingerprint": fingerprint,
            "message": "Email already processed — skipped.",
        }

    # --- Step 3: detect terminology -----------------------------------
    detected = detect_from_email(email, TermStore())

    # --- Step 4: fake structured translation --------------------------
    translation = fake_translate(email["subject"], email["bodytext"], detected)

    # --- Step 5: save translated artifact -----------------------------
    artifact_path = save_translation_artifact(translation, fingerprint)

    # --- Step 6: render parent-facing Markdown ------------------------
    rendered = render_markdown(translation, fingerprint)

    # --- Step 7: append to local push log -----------------------------
    append_push_log(fingerprint, rendered, artifact_path)

    # --- Step 8: mark processed ONLY after artifact + log succeed -----
    mark_processed(fingerprint, artifact_path=str(artifact_path))

    return {
        "status": "processed",
        "fingerprint": fingerprint,
        "artifact_path": str(artifact_path),
        "detected_terms": [t["term"] for t in detected],
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(
        prog="app.pipeline",
        description="Offline SchoolMail Bridge pipeline runner.",
    )
    cli.add_argument(
        "input",
        nargs="?",
        default=str(DEFAULT_INPUT),
        help=f"Path to the .eml file to process (default: {DEFAULT_INPUT}).",
    )
    args = cli.parse_args(argv)

    eml_path = Path(args.input)
    if not eml_path.is_file():
        print(f"ERROR: input not found: {eml_path}", file=sys.stderr)
        return 1

    try:
        result = run_pipeline(eml_path)
    except SecurityConfigError as exc:
        # Clear, single-line error for a missing/short secret (requirement #8).
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Pipeline result:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
