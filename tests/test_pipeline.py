"""Tests for sample + live pipeline CLI."""

from contextlib import contextmanager
from pathlib import Path

from app import pipeline
from app.ai_translator import fake_translate
from app.sample_email_reader import read_eml

SAMPLE = Path("data/sample_emails/progress_report.eml")
SECRET = "test-fingerprint-secret-32-chars-min"


def test_run_pipeline_on_email_writes_local_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "TRANSLATED_DIR", tmp_path / "translated")
    monkeypatch.setattr(pipeline, "ORIGIN_DIR", tmp_path / "origin_messages")
    monkeypatch.setattr(pipeline, "PUSH_LOG_PATH", tmp_path / "push_log.jsonl")
    monkeypatch.setattr(pipeline, "is_processed", lambda fingerprint: False)
    marked = {}

    def fake_mark(fingerprint, artifact_path=None):
        marked["fingerprint"] = fingerprint
        marked["artifact_path"] = artifact_path
        return {}

    monkeypatch.setattr(pipeline, "mark_processed", fake_mark)
    monkeypatch.setattr(pipeline, "translate_email", fake_translate)

    email = read_eml(SAMPLE)
    result = pipeline.run_pipeline_on_email(email, secret=SECRET)
    assert result["status"] == "processed"
    assert "Progress Report" in result["detected_terms"]
    artifact = tmp_path / "translated" / f"{result['fingerprint']}.json"
    assert artifact.is_file()
    assert "PLACEHOLDER_TRANSLATION" in artifact.read_text(encoding="utf-8")
    assert marked["artifact_path"] == str(artifact)
    # Raw Message-ID must not appear in the translation artifact.
    assert "progress-report-001@example.edu" not in artifact.read_text(encoding="utf-8")

    origin = tmp_path / "origin_messages" / f"{result['fingerprint']}.json"
    assert origin.is_file()
    assert result["origin_path"] == str(origin)
    origin_text = origin.read_text(encoding="utf-8")
    assert "Progress Report Available on PowerSchool" in origin_text
    assert "PowerSchool" in origin_text
    assert "Academic Office" in origin_text
    # Project constraint: never persist raw Message-ID in runtime files.
    assert "progress-report-001@example.edu" not in origin_text
    assert "message_id" not in origin_text


def test_main_live_list_prints_subjects(monkeypatch, capsys):
    @contextmanager
    def fake_session(config=None):
        yield "client", type("Cfg", (), {"folder": "INBOX"})()

    monkeypatch.setattr(pipeline, "imap_session", fake_session)
    monkeypatch.setattr(
        pipeline,
        "list_messages",
        lambda client, folder, limit: [
            {
                "uid": "9",
                "sender": "School <office@example.edu>",
                "subject": "Weather Closure Tomorrow",
                "date": "Tue, 10 Mar 2026",
                "message_id": "<secret-id@example.edu>",
            }
        ],
    )
    rc = pipeline.main(["--source", "live", "--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Weather Closure Tomorrow" in out
    assert "9" in out


def test_main_live_uid_runs_pipeline(monkeypatch, capsys):
    called = {}

    @contextmanager
    def fake_session(config=None):
        yield "client", type("Cfg", (), {"folder": "INBOX"})()

    def fake_fetch(client, uid, folder="INBOX"):
        called["uid"] = uid
        return read_eml(SAMPLE)

    def fake_run(email, secret=None):
        called["subject"] = email["subject"]
        return {
            "status": "processed",
            "fingerprint": "abc",
            "artifact_path": "runtime/x.json",
            "detected_terms": ["GPA"],
        }

    monkeypatch.setattr(pipeline, "imap_session", fake_session)
    monkeypatch.setattr(pipeline, "fetch_message", fake_fetch)
    monkeypatch.setattr(pipeline, "run_pipeline_on_email", fake_run)

    rc = pipeline.main(["--source", "live", "--uid", "42"])
    assert rc == 0
    assert called["uid"] == "42"
    assert "processed" in capsys.readouterr().out


def test_run_pipeline_prefers_minimax_translation(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "TRANSLATED_DIR", tmp_path / "translated")
    monkeypatch.setattr(pipeline, "ORIGIN_DIR", tmp_path / "origin_messages")
    monkeypatch.setattr(pipeline, "PUSH_LOG_PATH", tmp_path / "push_log.jsonl")
    monkeypatch.setattr(pipeline, "is_processed", lambda fingerprint: False)
    monkeypatch.setattr(pipeline, "mark_processed", lambda *a, **k: {})
    monkeypatch.setattr(
        pipeline,
        "translate_email",
        lambda subject, body, terms: {
            "engine": "minimax",
            "model": "MiniMax-M2.5",
            "subject_zh": "进度报告已发布",
            "summary_zh": "请在系统中查看成绩。",
            "terms": [],
        },
    )
    result = pipeline.run_pipeline_on_email(read_eml(SAMPLE), secret=SECRET)
    text = Path(result["artifact_path"]).read_text(encoding="utf-8")
    assert '"engine": "minimax"' in text
    assert "进度报告已发布" in text
    assert "PLACEHOLDER" not in text
    assert Path(result["origin_path"]).is_file()


def test_main_live_requires_list_or_uid(capsys):
    rc = pipeline.main(["--source", "live"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "--list" in err
    assert "--uid" in err
