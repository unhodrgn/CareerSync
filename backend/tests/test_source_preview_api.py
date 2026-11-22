"""Regression tests for source preview and local poster extraction."""
import pytest

from app.core.errors import AppError
from app.services import poster_service


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
    assert "job_id" not in response.json()
    assert job.description == before


def test_poster_is_reviewable_and_not_stored(client, world, monkeypatch):
    monkeypatch.setattr(poster_service, "extract_text", lambda data, mime: "Java / Spring 개발")
    r = client.post("/api/jobs/poster-text", files={"file": ("poster.png", b"fake", "image/png")}, headers=world["recruiter"])
    assert r.status_code == 200, r.json()
    assert r.json() == {"text": "Java / Spring 개발"}


def test_poster_rejects_invalid_bytes():
    with pytest.raises(AppError):
        poster_service.extract_text(b"not an image", "image/png")
