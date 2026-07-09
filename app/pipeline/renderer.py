"""Step 6 — Render a parent-facing Markdown message from the translation."""

from __future__ import annotations


def render_markdown(translation: dict, fingerprint: str) -> str:
    """Produce a short, parent-friendly Markdown message.

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
            explanation = t.get("explanation", "")
            if explanation:
                entry += f"：{explanation}"
            lines.append(entry)
    else:
        lines.append("- （未检测到关键术语）")

    lines += [
        "",
        "_（本消息为离线占位翻译，正式发布前请人工校对。）_",
    ]
    return "\n".join(lines)
