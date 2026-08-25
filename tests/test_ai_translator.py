"""Tests for MiniMax AI translator and placeholder fallback."""

from __future__ import annotations

import json

import pytest
import requests

from app import ai_translator
from app.ai_translator import (
    TranslationConfigError,
    load_minimax_config,
    parse_model_json,
    translate_email,
)


REQUIRED_TERMS = [
    {
        "term": "Progress Report",
        "zh": "进度报告",
        "explanation": "学期中阶段性学习反馈",
        "category": "grades",
        "priority": 1,
    }
]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | str, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (payload if isinstance(payload, str) else json.dumps(payload))

    def json(self):
        if isinstance(self._payload, str):
            return json.loads(self._payload)
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


def test_load_minimax_config_from_env():
    cfg = load_minimax_config(
        {
            "MINIMAX_API_KEY": "sk-test-key",
            "MINIMAX_API_BASE_URL": "https://api.minimax.io/v1",
            "MINIMAX_MODEL": "MiniMax-M2.5",
        }
    )
    assert cfg.api_key == "sk-test-key"
    assert cfg.base_url == "https://api.minimax.io/v1"
    assert cfg.model == "MiniMax-M2.5"
    assert cfg.chat_url == "https://api.minimax.io/v1/chat/completions"


def test_load_minimax_config_accepts_translation_aliases():
    cfg = load_minimax_config(
        {
            "TRANSLATION_API_KEY": "alias-key",
            "TRANSLATION_API_BASE_URL": "https://api.minimax.io/v1/",
        }
    )
    assert cfg.api_key == "alias-key"
    assert cfg.base_url == "https://api.minimax.io/v1"
    assert cfg.model == "MiniMax-M2.5"


def test_load_minimax_config_requires_api_key():
    with pytest.raises(TranslationConfigError, match="API"):
        load_minimax_config({})


def test_parse_model_json_extracts_object_from_fenced_text():
    raw = '说明如下：\n```json\n{"subject_zh":"进度报告","summary_zh":"请查看成绩"}\n```\n'
    parsed = parse_model_json(raw)
    assert parsed["subject_zh"] == "进度报告"
    assert parsed["summary_zh"] == "请查看成绩"


def test_translate_email_uses_minimax_when_available(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        content = json_module.dumps(
            {"subject_zh": "进度报告已发布", "summary_zh": "请在 PowerSchool 查看成绩。"},
            ensure_ascii=False,
        )
        return FakeResponse(
            200,
            {
                "choices": [
                    {"message": {"role": "assistant", "content": content}},
                ]
            },
        )

    import json as json_module

    monkeypatch.setattr(ai_translator.requests, "post", fake_post)
    result = translate_email(
        "Progress Report Available",
        "Please check PowerSchool.",
        REQUIRED_TERMS,
        env={
            "MINIMAX_API_KEY": "sk-test",
            "MINIMAX_API_BASE_URL": "https://api.minimax.io/v1",
            "MINIMAX_MODEL": "MiniMax-M2.5",
        },
    )
    assert result["engine"] == "minimax"
    assert result["subject_zh"] == "进度报告已发布"
    assert "PowerSchool" in result["summary_zh"]
    assert result["terms"][0]["term"] == "Progress Report"
    assert captured["url"] == "https://api.minimax.io/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["timeout"] == 30
    assert "sk-test" not in json.dumps(captured["json"])


def test_translate_email_falls_back_on_http_error(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.Timeout("slow")

    monkeypatch.setattr(ai_translator.requests, "post", boom)
    result = translate_email(
        "Progress Report",
        "Body here",
        REQUIRED_TERMS,
        env={"MINIMAX_API_KEY": "sk-test"},
    )
    assert result["engine"] == "offline-placeholder"
    assert result["subject_zh"].startswith("【占位翻译】")


def test_translate_email_falls_back_when_api_key_missing():
    result = translate_email(
        "Progress Report",
        "Body here",
        REQUIRED_TERMS,
        env={},
    )
    assert result["engine"] == "offline-placeholder"
