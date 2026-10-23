"""An empty or whitespace-only variable counts as unset (like Compose's `${VAR:-default}`), so `JWT_SECRET_KEY=` in
.env no longer breaks login. A value that is set is used unchanged. While a built-in dev secret is in use the
backend logs one warning at startup, with the names only.

Each case loads its own copy of app/core/config.py, so the app's `settings` stay untouched; the root conftest keeps
.env out (CAREERSYNC_DOTENV=0)."""
import importlib.util
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.config import DEV_JWT_SECRET_KEY, DEV_TALENT_ID_SECRET, REPO_ROOT, env_or_default, settings
from app.main import app

ENV_NAMES = (
    "DATABASE_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "JWT_SECRET_KEY",
    "JWT_EXPIRE_MINUTES",
    "TALENT_ID_SECRET",
    "BLOCKLIST_PATH",
    "SKILLS_PATH",
    "INTERVIEW_BLOCKLIST_PATH",
    "LEARNING_RESOURCES_PATH",
)
DEFAULT_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/careersync_db"
DATA = REPO_ROOT / "data"


def _load(monkeypatch, **env: str) -> config.Settings:
    """Settings as a fresh process would read them with exactly these variables set."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("config_under_test", config.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.settings


def _url(s) -> str:
    return s.DATABASE_URL


# Variable, how to read it, value when missing or blank, a set value, what the set value gives
SETTINGS = [
    ("JWT_SECRET_KEY", lambda s: s.JWT_SECRET_KEY, DEV_JWT_SECRET_KEY, " test jwt secret ", " test jwt secret "),
    ("TALENT_ID_SECRET", lambda s: s.TALENT_ID_SECRET, DEV_TALENT_ID_SECRET, "test-talent-secret", "test-talent-secret"),
    ("JWT_EXPIRE_MINUTES", lambda s: s.JWT_EXPIRE_MINUTES, 120, "45", 45),
    ("DATABASE_URL", _url, DEFAULT_URL, "sqlite:///test.db", "sqlite:///test.db"),
    ("DB_HOST", _url, DEFAULT_URL, "db.test", "postgresql+psycopg://postgres:postgres@db.test:5432/careersync_db"),
    ("DB_PORT", _url, DEFAULT_URL, "5433", "postgresql+psycopg://postgres:postgres@localhost:5433/careersync_db"),
    ("DB_USER", _url, DEFAULT_URL, "app", "postgresql+psycopg://app:postgres@localhost:5432/careersync_db"),
    ("DB_PASSWORD", _url, DEFAULT_URL, "pw", "postgresql+psycopg://postgres:pw@localhost:5432/careersync_db"),
    ("DB_NAME", _url, DEFAULT_URL, "other_db", "postgresql+psycopg://postgres:postgres@localhost:5432/other_db"),
    ("BLOCKLIST_PATH", lambda s: s.BLOCKLIST_PATH, DATA / "blocklist.yaml", "custom/blocklist.yaml", Path("custom/blocklist.yaml")),
    ("SKILLS_PATH", lambda s: s.SKILLS_PATH, DATA / "skills.yaml", "custom/skills.yaml", Path("custom/skills.yaml")),
    (
        "INTERVIEW_BLOCKLIST_PATH",
        lambda s: s.INTERVIEW_BLOCKLIST_PATH,
        DATA / "interview_blocklist.yaml",
        "custom/interview.yaml",
        Path("custom/interview.yaml"),
    ),
    (
        "LEARNING_RESOURCES_PATH",
        lambda s: s.LEARNING_RESOURCES_PATH,
        DATA / "learning_resources.yaml",
        "custom/resources.yaml",
        Path("custom/resources.yaml"),
    ),
]
SETTING_IDS = [s[0] for s in SETTINGS]


@pytest.mark.parametrize("blank", [None, "", "  \t "], ids=["missing", "empty", "whitespace"])
@pytest.mark.parametrize("name, read, default, value, expected", SETTINGS, ids=SETTING_IDS)
def test_missing_empty_or_whitespace_means_the_default(monkeypatch, name, read, default, value, expected, blank):
    env = {} if blank is None else {name: blank}
    assert read(_load(monkeypatch, **env)) == default


@pytest.mark.parametrize("name, read, default, value, expected", SETTINGS, ids=SETTING_IDS)
def test_a_set_value_is_used_unchanged(monkeypatch, name, read, default, value, expected):
    assert read(_load(monkeypatch, **{name: value})) == expected


@pytest.mark.parametrize("value", ["abc", "1.5"])
def test_an_invalid_number_still_fails_at_startup(monkeypatch, value):
    with pytest.raises(ValueError):
        _load(monkeypatch, JWT_EXPIRE_MINUTES=value)


@pytest.mark.parametrize(
    "value, expected",
    [(None, "fallback"), ("", "fallback"), (" \t\n", "fallback"), ("x", "x"), (" x ", " x ")],
    ids=["missing", "empty", "whitespace", "set", "set-with-spaces"],
)
def test_env_or_default(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("CAREERSYNC_TEST_VAR", raising=False)
    else:
        monkeypatch.setenv("CAREERSYNC_TEST_VAR", value)
    assert env_or_default("CAREERSYNC_TEST_VAR", "fallback") == expected


def test_login_works_when_jwt_secret_key_is_empty(monkeypatch, client):
    loaded = _load(monkeypatch, JWT_SECRET_KEY="")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", loaded.JWT_SECRET_KEY)  # what the app runs with after JWT_SECRET_KEY=
    body = {
        "email": "empty-secret@seeker.test",
        "password": "secret123",
        "role": "seeker",
        "display_name": "테스트",
        "consent_privacy": True,
        "consent_ai": True,
    }
    assert client.post("/api/auth/register", json=body).status_code == 201
    r = client.post("/api/auth/login", json={"email": body["email"], "password": body["password"]})
    assert r.status_code == 200
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == body["email"]


def _secret_warnings(monkeypatch, caplog, jwt_secret: str, talent_secret: str) -> list[logging.LogRecord]:
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", jwt_secret)
    monkeypatch.setattr(settings, "TALENT_ID_SECRET", talent_secret)
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"), TestClient(app):
        pass
    for secret in (jwt_secret, talent_secret):
        assert secret not in caplog.text
    return [r for r in caplog.records if r.name == "uvicorn.error" and "Built-in dev secret" in r.getMessage()]


def test_startup_warns_once_while_both_dev_secrets_are_in_use(monkeypatch, caplog):
    [record] = _secret_warnings(monkeypatch, caplog, DEV_JWT_SECRET_KEY, DEV_TALENT_ID_SECRET)
    assert record.levelno == logging.WARNING
    assert "JWT_SECRET_KEY" in record.getMessage() and "TALENT_ID_SECRET" in record.getMessage()


def test_startup_names_only_the_secret_still_on_its_dev_value(monkeypatch, caplog):
    [record] = _secret_warnings(monkeypatch, caplog, "a-test-jwt-secret", DEV_TALENT_ID_SECRET)
    assert "TALENT_ID_SECRET" in record.getMessage() and "JWT_SECRET_KEY" not in record.getMessage()


def test_no_warning_when_both_secrets_are_set(monkeypatch, caplog):
    assert _secret_warnings(monkeypatch, caplog, "a-test-jwt-secret", "a-test-talent-secret") == []
