"""Tests for MiniMax AI translator and placeholder fallback."""

from __future__ import annotations

import json
import json as _json

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


def _minimax_reply(content: dict):
    def fake_post(url, headers=None, json=None, timeout=None):
        fake_post.payload = json
        return FakeResponse(
            200,
            {"choices": [{"message": {"role": "assistant", "content": _json.dumps(content, ensure_ascii=False)}}]},
        )

    return fake_post


def test_translate_email_returns_structured_sections(monkeypatch):
    fake_post = _minimax_reply(
        {
            "subject_zh": "9月28日至10月3日安排",
            "summary_zh": "曲棍球教练发来下周训练和比赛安排。",
            "key_points": ["校队对 Mt. St. Charles 的比赛改到10月5日下午4点", "", 7, None],
            "action_items": ["10月3日上午7:15到场集合"],
            "schedule": [
                {"date": "9月28日（周一）", "items": ["二队训练 3:45-5:15"]},
                {"date": "", "items": ["no date"]},
                {"date": "9月29日（周二）", "items": []},
                "bad entry",
            ],
        }
    )
    monkeypatch.setattr(ai_translator.requests, "post", fake_post)

    result = translate_email("Schedule", "Body", [], env={"MINIMAX_API_KEY": "sk-test"})

    assert result["engine"] == "minimax"
    assert result["key_points"] == ["校队对 Mt. St. Charles 的比赛改到10月5日下午4点", "7"]
    assert result["action_items"] == ["10月3日上午7:15到场集合"]
    assert result["schedule"] == [{"date": "9月28日（周一）", "items": ["二队训练 3:45-5:15"]}]
    prompt = fake_post.payload["messages"][1]["content"]
    for key in ("key_points", "action_items", "schedule"):
        assert key in prompt
    assert "never half-translate a name" in prompt


def test_translate_email_tolerates_missing_optional_sections(monkeypatch):
    monkeypatch.setattr(
        ai_translator.requests,
        "post",
        _minimax_reply({"subject_zh": "通知", "summary_zh": "学校发来通知。", "schedule": "none"}),
    )
    result = translate_email("Notice", "Body", [], env={"MINIMAX_API_KEY": "sk-test"})
    assert result["key_points"] == []
    assert result["action_items"] == []
    assert result["schedule"] == []


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
