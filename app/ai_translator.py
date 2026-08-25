"""MiniMax overseas LLM translator for SchoolMail Bridge.

Calls the OpenAI-compatible Chat Completions API at the international host
(``https://api.minimax.io/v1`` by default). On any configuration / network /
JSON failure, callers should fall back to the offline placeholder translator.

Config (``.env``)::

    MINIMAX_API_KEY=...
    MINIMAX_API_BASE_URL=https://api.minimax.io/v1
    MINIMAX_MODEL=MiniMax-M2.5

Aliases also accepted: ``TRANSLATION_API_KEY``, ``TRANSLATION_API_BASE_URL``.

Never logs the API key or the full raw email body.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass

import requests

from .security import load_dotenv_if_present

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MODEL = "MiniMax-M2.5"
DEFAULT_TIMEOUT_SECONDS = 30
MAX_BODY_CHARS = 6000

REQUIRED_KEYS = ("subject_zh", "summary_zh")


class TranslationConfigError(Exception):
    """Raised when MiniMax API settings are missing or invalid."""


class TranslationError(Exception):
    """Raised when a live MiniMax translation attempt fails."""


@dataclass(frozen=True)
class MiniMaxConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: int = DEFAULT_TIMEOUT_SECONDS

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def load_minimax_config(env: dict[str, str] | None = None) -> MiniMaxConfig:
    """Load MiniMax settings from *env* or ``.env`` / process environment."""
    if env is None:
        load_dotenv_if_present()
        env = os.environ

    api_key = (
        (env.get("MINIMAX_API_KEY") or env.get("TRANSLATION_API_KEY") or "")
        .strip()
    )
    base_url = (
        (env.get("MINIMAX_API_BASE_URL") or env.get("TRANSLATION_API_BASE_URL") or "")
        .strip()
        or DEFAULT_BASE_URL
    ).rstrip("/")
    model = (env.get("MINIMAX_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

    if not api_key or api_key.startswith("replace_"):
        raise TranslationConfigError(
            "MiniMax API key missing. Set MINIMAX_API_KEY (or TRANSLATION_API_KEY) "
            "in your .env file."
        )
    return MiniMaxConfig(api_key=api_key, base_url=base_url, model=model)


def parse_model_json(content: str) -> dict:
    """Parse a JSON object from model output (raw or fenced)."""
    text = (content or "").strip()
    if not text:
        raise TranslationError("Model returned empty content")

    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    # Last-resort: first {...} block in the reply.
    brace = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if brace:
        candidates.append(brace.group(0))

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(data, dict):
            return data
    raise TranslationError(f"Model response is not valid JSON: {last_error}")


def _validate_translation(data: dict) -> dict:
    missing = [key for key in REQUIRED_KEYS if not str(data.get(key, "")).strip()]
    if missing:
        raise TranslationError(f"Model JSON missing required keys: {', '.join(missing)}")
    return {key: str(data[key]).strip() for key in REQUIRED_KEYS}


def _build_messages(subject: str, bodytext: str, detected_terms: list[dict]) -> list[dict]:
    term_lines = [
        f"- {t.get('term', '')}: {t.get('zh', '')} ({t.get('explanation', '')})"
        for t in detected_terms
    ]
    terms_block = "\n".join(term_lines) if term_lines else "(none detected)"
    body = (bodytext or "")[:MAX_BODY_CHARS]
    user_prompt = (
        "Translate this school email for Chinese-speaking parents.\n"
        "Return ONLY a JSON object with keys subject_zh and summary_zh.\n"
        "summary_zh must be a clear Simplified Chinese summary of the email body "
        "(not a placeholder). Keep school terms accurate.\n\n"
        f"Subject: {subject}\n\n"
        f"Body:\n{body}\n\n"
        f"Detected terms:\n{terms_block}\n"
    )
    return [
        {
            "role": "system",
            "content": (
                "You are SchoolMail Bridge. Output valid JSON only. "
                "Do not wrap the JSON in markdown unless necessary."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]


def _terms_out(detected_terms: list[dict]) -> list[dict]:
    return [
        {
            "term": t.get("term", ""),
            "zh": t.get("zh", ""),
            "explanation": t.get("explanation", ""),
            "category": t.get("category", ""),
            "priority": t.get("priority", 99),
        }
        for t in detected_terms
    ]


def fake_translate(subject: str, bodytext: str, detected_terms: list[dict]) -> dict:
    """Structured Chinese placeholder (offline fallback)."""
    return {
        "engine": "offline-placeholder",
        "warning": "PLACEHOLDER_TRANSLATION_NOT_REAL — human review required",
        "subject_zh": f"【占位翻译】{subject}",
        "summary_zh": (
            "（占位）这是一份离线生成的摘要，未经真实翻译引擎处理。"
            f"原文主题：{subject}。请家长以学校英文原件为准。"
        ),
        "terms": _terms_out(detected_terms),
    }


def live_translate(
    subject: str,
    bodytext: str,
    detected_terms: list[dict],
    *,
    config: MiniMaxConfig | None = None,
    env: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> dict:
    """Call MiniMax Chat Completions and return a structured translation dict."""
    cfg = config or load_minimax_config(env)
    payload = {
        "model": cfg.model,
        "messages": _build_messages(subject, bodytext, detected_terms),
        "temperature": 0.2,
        "max_completion_tokens": 1200,
    }
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }

    http = session or requests
    try:
        response = http.post(
            cfg.chat_url,
            headers=headers,
            json=payload,
            timeout=cfg.timeout,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        # Never include request headers (API key) in the raised message.
        raise TranslationError(f"MiniMax HTTP request failed: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise TranslationError("MiniMax response was not JSON") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TranslationError("MiniMax response missing choices[0].message.content") from exc

    parsed = _validate_translation(parse_model_json(content))
    log.info("minimax translation ok | model=%s | subject_chars=%d", cfg.model, len(subject))
    return {
        "engine": "minimax",
        "model": cfg.model,
        "subject_zh": parsed["subject_zh"],
        "summary_zh": parsed["summary_zh"],
        "terms": _terms_out(detected_terms),
    }


def translate_email(
    subject: str,
    bodytext: str,
    detected_terms: list[dict],
    *,
    env: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> dict:
    """Prefer MiniMax; fall back to placeholder on any failure."""
    try:
        return live_translate(
            subject,
            bodytext,
            detected_terms,
            env=env,
            session=session,
        )
    except (TranslationConfigError, TranslationError) as exc:
        log.warning("minimax translation failed; using placeholder: %s", exc)
        return fake_translate(subject, bodytext, detected_terms)
