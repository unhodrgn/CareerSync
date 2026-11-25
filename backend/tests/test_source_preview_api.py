"""Regression tests for source preview and local poster extraction."""
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from ai.tests.helpers import FakeLLM
from app.core.config import settings
from app.core.errors import AppError
from app.services import ai_runtime, jd_service, poster_service


@pytest.fixture(autouse=True)
def _fresh_counts():
    jd_service.reset_counts()
    yield
    jd_service.reset_counts()


def test_preview_requires_company(client, world):
    body = {"source_type": "job_posting", "title": "Developer", "text": "Java Spring 개발"}
    assert client.post("/api/jobs/criteria-preview", json=body).status_code == 401
    assert client.post("/api/jobs/criteria-preview", json=body, headers=world["seeker"]).status_code == 403


def test_project_preview_does_not_modify_job(client, world):
    job = world["job"]
    owner = world["recruiter"]
    before = job.description
    body = {
        "source_type": "project_spec", "title": "Java backend developer",
        "text": "프로젝트 수행\n자격 요건\nJava Spring PostgreSQL API 개발",
    }
    response = client.post("/api/jobs/criteria-preview", json=body, headers=owner)
    assert response.status_code == 200, response.json()
    assert sum(x["weight"] for x in response.json()["analysis"]["criteria"]) == 100
    assert response.json()["limited"] is False
    assert "job_id" not in response.json()
    assert job.description == before


def test_preview_daily_llm_limit_falls_back_to_rules(client, world, monkeypatch):
    analysis = {
        "profile": {"required_skills": ["Java"], "preferred_skills": [], "min_years": 3, "duties": [], "certificates": []},
        "criteria": [{"name": "Java 역량", "description": "Java 실무 경험", "category": "skill", "weight": 100}],
    }
    llm = FakeLLM(analysis, analysis)
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    monkeypatch.setattr(settings, "COMPANY_DAILY_LLM_PREVIEWS", 2)
    body = {"source_type": "job_posting", "title": "Backend", "text": "Java Spring 개발 3년 이상"}
    results = [client.post("/api/jobs/criteria-preview", json=body, headers=world["recruiter"]).json() for _ in range(3)]
    assert [r["method"] for r in results] == ["llm:fake-llm", "llm:fake-llm", "rules"]
    assert [r["limited"] for r in results] == [False, False, True]


def test_poster_is_reviewable_and_not_stored(client, world, monkeypatch):
    monkeypatch.setattr(poster_service, "extract_text", lambda data, mime: "Java / Spring 개발")
    r = client.post("/api/jobs/poster-text", files={"file": ("poster.png", b"fake", "image/png")}, headers=world["recruiter"])
    assert r.status_code == 200, r.json()
    assert r.json() == {"text": "Java / Spring 개발"}


def test_poster_decodes_utf8_and_enforces_size_and_format(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="  백엔드 개발자 채용 \n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = poster_service.extract_text(b"\x89PNG\r\n\x1a\npayload", "image/png")
    assert out == "백엔드 개발자 채용"
    assert calls[0][1]["encoding"] == "utf-8"

    with pytest.raises(AppError) as size_exc:
        poster_service.extract_text(b"x" * (poster_service.MAX_IMAGE_BYTES + 1), "image/png")
    assert size_exc.value.code == "POSTER_SIZE"


def test_poster_rejects_invalid_bytes():
    with pytest.raises(AppError) as exc:
        poster_service.extract_text(b"not an image", "image/png")
    assert exc.value.code == "POSTER_FORMAT"


def test_poster_text_does_not_block_other_requests(client, world, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    released = {"ok": False}

    def slow_extract(_data, _mime):
        entered.set()
        released["ok"] = release.wait(5)
        return "백엔드 개발자 채용"

    monkeypatch.setattr(poster_service, "extract_text", slow_extract)
    result = {}
    with client:
        def run_ocr():
            result["response"] = client.post(
                "/api/jobs/poster-text",
                files={"file": ("poster.png", b"\x89PNG\r\n\x1a\nok", "image/png")},
                headers=world["recruiter"],
            )

        t = threading.Thread(target=run_ocr)
        t.start()
        try:
            assert entered.wait(5)
            start = time.monotonic()
            health = client.get("/health")
            elapsed = time.monotonic() - start
        finally:
            release.set()
            t.join(10)

    assert health.status_code == 200 and elapsed < 1
    assert released["ok"] is True
    assert result["response"].status_code == 200 and result["response"].json() == {"text": "백엔드 개발자 채용"}
