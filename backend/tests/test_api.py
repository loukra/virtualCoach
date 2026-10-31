from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import core.auth
import routers.checkin
from core.config import get_settings
from main import app

TOKEN_USERS = {"token-owner": "owner-id", "token-stranger": "stranger-id"}


class FakeTable:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def upsert(self, data, **kwargs):
        self.db.writes.append((self.name, data))
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class FakeDB:
    def __init__(self):
        self.writes = []
        self.auth = SimpleNamespace(get_user=self._get_user)

    def _get_user(self, token):
        if token not in TOKEN_USERS:
            raise ValueError("invalid JWT")
        return SimpleNamespace(user=SimpleNamespace(id=TOKEN_USERS[token]))

    def table(self, name):
        return FakeTable(self, name)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(core.auth, "get_db", lambda: fake)
    monkeypatch.setattr(routers.checkin, "get_db", lambda: fake)
    return fake


@pytest.fixture
def client():
    return TestClient(app)


def checkin(client, token=None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/check-in", json=body or {"feel_score": 4, "soreness_score": 3}, headers=headers)


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_missing_token_is_rejected(client, db):
    assert checkin(client).status_code == 401
    assert db.writes == []


def test_invalid_token_is_rejected(client, db):
    assert checkin(client, "forged").status_code == 401


def test_user_comes_from_token_not_from_body(client, db):
    res = checkin(client, "token-owner", {"feel_score": 4, "soreness_score": 3, "user_id": "victim-id"})
    assert res.status_code == 200
    assert db.writes[0][1]["user_id"] == "owner-id"


def test_allowlist_blocks_other_accounts(client, db, monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "owner-id")
    get_settings.cache_clear()
    try:
        assert checkin(client, "token-stranger").status_code == 403
        assert checkin(client, "token-owner").status_code == 200
    finally:
        get_settings.cache_clear()


def test_scores_are_validated(client, db):
    assert checkin(client, "token-owner", {"feel_score": 9, "soreness_score": 3}).status_code == 422
