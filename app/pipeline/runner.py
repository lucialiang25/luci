"""Offline pipeline orchestration for SchoolMail Bridge.

Steps:
  1. parse local email
  2. salted HMAC duplicate fingerprint check
  3. terminology detection (config/terms.json)
  4. fake structured Chinese placeholder translation
  5. save translated artifact
  6. render parent-facing Markdown
  7. append rendered message to push log
  8. mark fingerprint processed ONLY after 5 and 7 succeed
"""

from __future__ import annotations

from pathlib import Path

from . import fingerprint as fp
from . import parser, renderer, store, terms, translator


def run_pipeline(eml_path: Path) -> dict:
    """Run the full offline pipeline for one ``.eml`` file.

    Returns a small summary dict describing what happened.
    """
    # --- Step 1: parse the local email ---------------------------------
    source = parser.parse_email(eml_path)
    # Normalize the Message-ID (strip surrounding < >). It is used ONLY to
    # build the fingerprint and is never written to disk.
    raw_id = source["message_id"].strip().strip("<>")

    # --- Step 2: salted HMAC duplicate check ---------------------------
    fingerprint = fp.compute_fingerprint(raw_id or source["body"])
    if fp.already_processed(fingerprint):
        return {
            "status": "duplicate",
            "fingerprint": fingerprint,
            "message": "Email already processed — skipped.",
        }

    # --- Step 3: detect terminology ------------------------------------
    terms_index = terms.load_terms()
    detected = terms.detect_terms(
        source["subject"] + "\n" + source["body"], terms_index
    )

    # --- Step 4: fake structured translation ---------------------------
    translation = translator.fake_translate(
        source["subject"], source["body"], detected
    )

    # --- Step 5: save translated artifact ------------------------------
    artifact_path = store.save_translation_artifact(translation, fingerprint)

    # --- Step 6: render parent-facing Markdown -------------------------
    rendered = renderer.render_markdown(translation, fingerprint)

    # --- Step 7: append to local push log ------------------------------
    store.append_push_log(fingerprint, rendered, artifact_path)

    # --- Step 8: mark processed ONLY after artifact + log succeed ------
    fp.mark_processed(fingerprint, meta={"subject": source["subject"]})

    return {
        "status": "processed",
        "fingerprint": fingerprint,
        "artifact_path": str(artifact_path),
        "detected_terms": [t["term"] for t in detected],
    }
