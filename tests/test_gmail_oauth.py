"""Tests for Gmail OAuth token handling (no live network or browser)."""

import json
import stat

import pytest
from google.auth.exceptions import RefreshError

from app import gmail_oauth
from app.gmail_oauth import (
    GmailOAuthError,
    authorize,
    build_xoauth2_string,
    get_access_token,
)


class FakeCreds:
    def __init__(self, valid=True, refresh_token="1//refresh", fail_refresh=False):
        self.valid = valid
        self.refresh_token = refresh_token
        self.token = "ya29.old"
        self.fail_refresh = fail_refresh
        self.refreshed = False

    def refresh(self, request):
        if self.fail_refresh:
            raise RefreshError("invalid_grant")
        self.refreshed = True
        self.valid = True
        self.token = "ya29.new"

    def to_json(self):
        return json.dumps({"token": self.token, "refresh_token": self.refresh_token})


def _use_creds(monkeypatch, creds):
    monkeypatch.setattr(
        gmail_oauth.Credentials,
        "from_authorized_user_file",
        classmethod(lambda cls, path, scopes: creds),
    )


def test_build_xoauth2_string_format():
    assert (
        build_xoauth2_string("parent@gmail.com", "tok")
        == "user=parent@gmail.com\x01auth=Bearer tok\x01\x01"
    )


def test_get_access_token_missing_file_points_to_authorize(tmp_path):
    with pytest.raises(GmailOAuthError, match="app.gmail_oauth"):
        get_access_token(tmp_path / "missing.json")


def test_get_access_token_valid_does_not_refresh(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    creds = FakeCreds(valid=True)
    _use_creds(monkeypatch, creds)

    assert get_access_token(token_file) == "ya29.old"
    assert not creds.refreshed


def test_get_access_token_refreshes_and_saves_privately(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    creds = FakeCreds(valid=False)
    _use_creds(monkeypatch, creds)

    assert get_access_token(token_file) == "ya29.new"
    assert json.loads(token_file.read_text())["token"] == "ya29.new"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_get_access_token_rejected_refresh_asks_to_reauthorize(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    _use_creds(monkeypatch, FakeCreds(valid=False, fail_refresh=True))

    with pytest.raises(GmailOAuthError, match="app.gmail_oauth"):
        get_access_token(token_file)


def test_get_access_token_without_refresh_token(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    _use_creds(monkeypatch, FakeCreds(valid=False, refresh_token=None))

    with pytest.raises(GmailOAuthError, match="no refresh token"):
        get_access_token(token_file)


def test_authorize_requires_client_file(tmp_path):
    with pytest.raises(GmailOAuthError, match="client file not found"):
        authorize(tmp_path / "client.json", tmp_path / "token.json")


def test_authorize_saves_token_with_consent_and_login_hint(tmp_path, monkeypatch):
    client_file = tmp_path / "client.json"
    client_file.write_text("{}", encoding="utf-8")
    token_file = tmp_path / "secrets" / "token.json"
    seen = {}

    class FakeFlow:
        def run_local_server(self, port, **kwargs):
            seen.update(kwargs, port=port)
            return FakeCreds()

    monkeypatch.setattr(
        gmail_oauth.InstalledAppFlow,
        "from_client_secrets_file",
        classmethod(lambda cls, path, scopes: seen.update(scopes=scopes) or FakeFlow()),
    )

    authorize(client_file, token_file, login_hint="parent@gmail.com")

    assert seen["scopes"] == ["https://mail.google.com/"]
    assert seen["prompt"] == "consent"
    assert seen["login_hint"] == "parent@gmail.com"
    assert seen["port"] == 0
    assert json.loads(token_file.read_text())["refresh_token"] == "1//refresh"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
