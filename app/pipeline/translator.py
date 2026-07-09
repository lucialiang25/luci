"""Step 4 — Fake translator returning STRUCTURED Chinese placeholder output.

No real LLM or translation API is used. The output is clearly flagged as a
placeholder so it can never be mistaken for a finished translation.
"""

from __future__ import annotations


def fake_translate(subject: str, body: str, detected_terms: list[dict]) -> dict:
    """Return a structured Chinese placeholder translation.

    Stable keys (``subject_zh``, ``summary_zh``, ``terms``) are consumed by the
    artifact writer and the Markdown renderer. ``terms`` keeps the full term
    objects (Chinese label + explanation) coming straight from terms.json.
    """
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
