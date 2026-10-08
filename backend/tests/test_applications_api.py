"""CV upload → confirm → apply → background evaluation → ranked list and evidence."""
from datetime import UTC, datetime

import pytest

from ai.tests.helpers import SAMPLE_CV, FakeLLM, make_pdf
from app.models import CvProfile, Evaluation, User
from app.services import ai_runtime
from tests.conftest import _PASSWORD_HASH, auth

CRITERIA = [
    {"name": "Java 활용 능력", "category": "skill", "weight": 30},
    {"name": "Spring 경험", "category": "skill", "weight": 25},
    {"name": "경력 3년 이상", "category": "experience", "weight": 20},
    {"name": "프로젝트 경험", "category": "project", "weight": 15, "description": "추천 시스템이나 API 설계 경험"},
    {"name": "관련 자격증", "category": "certificate", "weight": 10},
]
JUNIOR_CV = """박하은
이메일: haeun@example.com

프로젝트
학교 과제 게시판 2025.03 ~ 2025.06
- Java로 게시판 구현

학력
한빛대학교 경영학과 학사 2021.03 ~ 2025.02
"""


def seeker(db, email, name):
    now = datetime.now(UTC)
    user = User(email=email, password_hash=_PASSWORD_HASH, role="seeker", display_name=name, consent_privacy_at=now, consent_ai_at=now)
    db.add(user)
    db.commit()
    return auth(user)


@pytest.fixture
def job(client, world):
    h, job_id = world["recruiter"], world["job"].id
    assert client.put(f"/api/jobs/{job_id}/criteria", json={"items": CRITERIA}, headers=h).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/publish", headers=h).status_code == 200
    return job_id


def upload(client, headers, text=SAMPLE_CV):
    return client.post("/api/cv", files={"file": ("cv.pdf", make_pdf(text), "application/pdf")}, headers=headers)


def confirm(client, headers, cv):
    return client.put(f"/api/cv/{cv['id']}", json={"profile": cv["profile"], "confirm": True}, headers=headers)


def ready_seeker(client, db, email, name, text=SAMPLE_CV):
    h = seeker(db, email, name)
    cv = upload(client, h, text).json()
    assert confirm(client, h, cv).status_code == 200
    return h


def test_upload_masks_pii_and_structures(client, db):
    h = seeker(db, "kim@seeker.test", "김지원")
    r = upload(client, h)
    assert r.status_code == 201, r.json()
    cv = r.json()
    assert cv["version"] == 1 and cv["confirmed"] is False and cv["method"] == "rules"
    assert {"email", "phone", "name"} <= set(cv["masked_kinds"])
    assert "Java" in cv["profile"]["skills"]
    assert cv["total_experience_months"] > 60
    assert "jiwon.kim@example.com" not in str(cv)


def test_cv_profile_is_stored_relationally(client, db):
    h = seeker(db, "relational@seeker.test", "김지원")
    body = upload(client, h).json()

    row = db.get(CvProfile, body["id"])
    assert row is not None
    assert "Java" in [skill.skill_name for skill in row.skills]
    assert row.experiences
    assert row.projects
    assert row.educations
    assert row.summary == body["profile"]["summary"]


def test_upload_rejects_non_pdf_and_company_users(client, db, world):
    h = seeker(db, "kim@seeker.test", "김지원")
    r = client.post("/api/cv", files={"file": ("cv.txt", b"hello", "text/plain")}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "CV_NOT_PDF"
    assert upload(client, world["recruiter"]).status_code == 403


def test_edit_creates_new_confirmed_version(client, db):
    h = seeker(db, "kim@seeker.test", "김지원")
    cv = upload(client, h).json()
    cv["profile"]["skills"].append("스프링부트")
    r = confirm(client, h, cv)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 2 and body["confirmed"] and body["method"] == "seeker"
    assert body["profile"]["skills"].count("Spring") == 1  # alias normalized, no duplicate
    assert client.get("/api/cv/me", headers=h).json()["id"] == body["id"]


def test_cv_is_private(client, db):
    h = seeker(db, "kim@seeker.test", "김지원")
    other = seeker(db, "park@seeker.test", "박하은")
    cv = upload(client, h).json()
    assert client.get(f"/api/cv/{cv['id']}", headers=other).status_code == 404


def test_apply_needs_confirmed_cv(client, db, job):
    h = seeker(db, "kim@seeker.test", "김지원")
    assert client.post(f"/api/jobs/{job}/applications", headers=h).json()["code"] == "CV_NOT_CONFIRMED"
    upload(client, h)
    assert client.post(f"/api/jobs/{job}/applications", headers=h).json()["code"] == "CV_NOT_CONFIRMED"


def test_apply_evaluates_and_ranks(client, db, world, job):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")
    park = ready_seeker(client, db, "park@seeker.test", "박하은", JUNIOR_CV)
    r = client.post(f"/api/jobs/{job}/applications", headers=park)
    assert r.status_code == 201, r.json()
    assert client.post(f"/api/jobs/{job}/applications", headers=kim).status_code == 201
    assert client.post(f"/api/jobs/{job}/applications", headers=kim).json()["code"] == "ALREADY_APPLIED"
    assert client.get("/api/applications/mine", headers=kim).json()[0]["evaluation_status"] == "done"

    listing = client.get(f"/api/jobs/{job}/applications", headers=world["recruiter"]).json()
    names = [i["name"] for i in listing["items"]]
    assert names == ["김지원", "박하은"]
    top = listing["items"][0]
    assert top["rank"] == 1 and top["evaluation_status"] == "done" and top["status"] == "submitted"
    assert top["fit"] > listing["items"][1]["fit"]
    assert sum(c["weight"] for c in listing["criteria"]) == 100

    ev = client.get(f"/api/applications/{top['application_id']}/evaluation", headers=world["recruiter"]).json()
    assert ev["status"] == "done" and ev["fit"] == top["fit"]
    assert [i["name"] for i in ev["items"]] == [c["name"] for c in CRITERIA]
    for item in ev["items"]:
        assert item["score"] == 0 or item["evidence"]
    assert ev["summary"] and "참고용" in ev["notice"]
    assert ev["embedding_model"] == "hashing-ngram-v1" and ev["prompt_version"] == "v1"


def test_weight_change_reranks_without_rescoring(client, db, world, job, monkeypatch):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")
    client.post(f"/api/jobs/{job}/applications", headers=kim)
    h = world["recruiter"]
    before = client.get(f"/api/jobs/{job}/applications", headers=h).json()["items"][0]["fit"]

    def boom(*a, **k):
        raise AssertionError("scoring must not run again")

    monkeypatch.setattr("app.services.evaluation_service.score_candidate", boom)
    current = client.get(f"/api/jobs/{job}/criteria", headers=h).json()["items"]
    reweighted = [{**c, "weight": w} for c, w in zip(current, [10, 10, 10, 60, 10], strict=True)]
    for c in reweighted:
        c.pop("position"), c.pop("importance")
    assert client.put(f"/api/jobs/{job}/criteria", json={"items": reweighted}, headers=h).status_code == 200
    after = client.get(f"/api/jobs/{job}/applications", headers=h).json()["items"][0]["fit"]
    assert after != before


def test_recruiter_only_and_own_company_only(client, db, world, job):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")
    app_id = client.post(f"/api/jobs/{job}/applications", headers=kim).json()["id"]
    assert client.get(f"/api/applications/{app_id}/evaluation", headers=kim).status_code == 403
    assert client.get(f"/api/applications/{app_id}/evaluation", headers=world["rival"]).status_code == 404
    assert client.get(f"/api/jobs/{job}/applications", headers=world["rival"]).status_code == 404
    assert client.put(f"/api/applications/{app_id}/status", json={"status": "interview"}, headers=world["rival"]).status_code == 404


def test_status_is_changed_only_by_recruiter(client, db, world, job):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")
    app_id = client.post(f"/api/jobs/{job}/applications", headers=kim).json()["id"]
    r = client.put(f"/api/applications/{app_id}/status", json={"status": "interview"}, headers=world["recruiter"])
    assert r.status_code == 200 and r.json()["status"] == "interview"
    assert client.put(f"/api/applications/{app_id}/status", json={"status": "auto"}, headers=world["recruiter"]).status_code == 422


def test_failed_evaluation_can_be_retried(client, db, world, job, monkeypatch):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")

    def broken(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr("app.services.evaluation_service.score_candidate", broken)
    app_id = client.post(f"/api/jobs/{job}/applications", headers=kim).json()["id"]
    h = world["recruiter"]
    ev = client.get(f"/api/applications/{app_id}/evaluation", headers=h).json()
    assert ev["status"] == "failed" and "model down" in ev["error"] and ev["fit"] is None
    row = client.get(f"/api/jobs/{job}/applications", headers=h).json()["items"][0]
    assert row["rank"] is None and row["evaluation_status"] == "failed"

    monkeypatch.undo()
    assert client.post(f"/api/applications/{app_id}/evaluation/retry", headers=h).status_code == 200
    assert client.get(f"/api/applications/{app_id}/evaluation", headers=h).json()["status"] == "done"
    assert client.post(f"/api/applications/{app_id}/evaluation/retry", headers=h).json()["code"] == "EVALUATION_DONE"


def test_no_personal_data_reaches_the_llm(client, db, world, job, monkeypatch):
    llm = FakeLLM(
        {"skills": ["Java"], "experiences": [], "summary": ""},
        {"level": 75, "reason": "API 설계", "evidence": ["Python, FastAPI로 추천 API 설계 및 팀 리드"]},
    )
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    h = seeker(db, "kim@seeker.test", "김지원")
    cv = upload(client, h).json()
    confirm(client, h, cv)
    client.post(f"/api/jobs/{job}/applications", headers=h)
    assert len(llm.calls) == 2
    for _system, user in llm.calls:
        for secret in ("jiwon.kim@example.com", "010-1234-5678", "김지원", "테헤란로"):
            assert secret not in user
    ev = db.query(Evaluation).one()
    assert ev.llm_model == "fake-llm"


def test_jd_analysis_suggests_criteria(client, world):
    job_id = world["job"].id
    r = client.post(f"/api/jobs/{job_id}/analyze", headers=world["recruiter"])
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "rules"
    assert {"Java", "Spring"} <= set(body["analysis"]["profile"]["required_skills"])
    assert sum(c["weight"] for c in body["analysis"]["criteria"]) == 100
    assert client.post(f"/api/jobs/{job_id}/analyze", headers=world["rival"]).status_code == 404
