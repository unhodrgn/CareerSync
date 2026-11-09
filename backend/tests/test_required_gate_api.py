"""Required criteria gate in the backend (docs/DECISIONS.md D50, Phase 1b): job recommendation and talent leave out
FAIL before queueing, the offer check refuses FAIL, the applicant list only labels and filters, the evaluation and job
detail show the result. Fit and stored scores never change."""
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import CriterionScore, CvProfile, Evaluation, JobCriterion, JobPosting, User
from app.models.application import EvaluationStatus
from app.services import evaluation_service, gate_service, talent_service

from .test_applications_api import JUNIOR_CV, SAMPLE_CV, ready_seeker
from .test_jobs_api import make_published

RECO = "/api/recommendations/jobs"
GATE_KEYS = {"status", "reason", "basis", "evidence", "checks"}
CHECK_KEYS = {"kind", "source", "required_months", "candidate_months", "basis", "status", "reason", "evidence"}

# TC-14 in short: the CV states 0 years and gives no employment period
ZERO_CV = """이민수
이메일: minsu@example.com
경력: 0년

보유 기술
Java, Spring Boot, PostgreSQL

프로젝트
게시판 API 2025.03 ~ 2025.06
- Java, Spring Boot로 REST API 구현
"""
# Enough stated experience, no period (the 14 scenarios' CVs)
FIVE_CV = ZERO_CV.replace("경력: 0년", "경력: 5년").replace("이민수", "최도윤").replace("minsu", "doyun")


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluation_service, "run_in_background", lambda *args: calls.append(args))
    return calls


def _seeker(client, db, email, name, text, public=False):
    h = ready_seeker(client, db, email, name, text)
    user = db.scalars(select(User).where(User.email == email)).one()
    user.consent_version = settings.CONSENT_VERSION
    db.commit()
    if public:
        body = {"locations": [], "employment_types": [], "job_keywords": [], "profile_public": True}
        assert client.put("/api/preferences/me", json=body, headers=h).status_code == 200
    cv_id = client.get("/api/cv/me", headers=h).json()["id"]
    return user, h, cv_id


def _job(client, world, min_years, title="백엔드 개발자") -> int:
    return make_published(client, world["recruiter"], title=title, min_experience_years=min_years)["id"]


def _finish(db, job_id: int, cv_id: int, fit: int) -> Evaluation:
    """Mark the (job, CV) evaluation done with every criterion at `fit` (creating it if missing)."""
    ev = db.scalars(select(Evaluation).where(Evaluation.job_id == job_id, Evaluation.cv_profile_id == cv_id)).first()
    if ev is None:
        ev = Evaluation(job_id=job_id, cv_profile_id=cv_id)
        db.add(ev)
    ev.status, ev.queued_at, ev.attempts = EvaluationStatus.DONE, datetime.now(UTC), 1
    ev.scores = [
        CriterionScore(job_criteria_id=c.id, score=fit, level=fit, reason="", evidence=[], method="rule:test")
        for c in db.scalars(select(JobCriterion).where(JobCriterion.job_id == job_id))
    ]
    db.commit()
    return ev


def _evaluated_jobs(db, cv_id: int) -> set[int]:
    db.expire_all()
    return {ev.job_id for ev in db.scalars(select(Evaluation).where(Evaluation.cv_profile_id == cv_id))}


def _stored_scores(db) -> list[tuple]:
    db.expire_all()
    return sorted((s.evaluation_id, s.job_criteria_id, s.score) for s in db.scalars(select(CriterionScore)))


# ── Seeker job recommendation ──


def test_fail_jobs_are_left_out_and_never_queued(client, db, world, queued):
    _, h, cv = _seeker(client, db, "zero@seeker.test", "이민수", ZERO_CV)
    fail_job = _job(client, world, 3, "경력 3년 공고")
    open_job = _job(client, world, None, "신입 가능 공고")
    first = client.get(RECO, headers=h).json()
    assert first["pending_count"] == 1  # only the job without a minimum
    assert _evaluated_jobs(db, cv) == {open_job} and len(queued) == 1

    # Even with a done evaluation and a high Fit, a FAIL job is not recommended
    _finish(db, fail_job, cv, 95)
    _finish(db, open_job, cv, 80)
    items = client.get(RECO, headers=h).json()["items"]
    assert [i["job_id"] for i in items] == [open_job]
    gate = items[0]["required_gate"]
    assert set(gate) == GATE_KEYS and (gate["status"], gate["checks"], gate["reason"]) == ("PASS", [], "필수 경력 조건 없음")


def test_pass_jobs_follow_the_existing_flow(client, db, world, queued):
    _, h, cv = _seeker(client, db, "kim@seeker.test", "김지원", SAMPLE_CV)
    job = _job(client, world, 3)
    assert client.get(RECO, headers=h).json()["pending_count"] == 1 and _evaluated_jobs(db, cv) == {job}
    _finish(db, job, cv, 80)
    item = client.get(RECO, headers=h).json()["items"][0]
    gate = item["required_gate"]
    assert (gate["status"], gate["basis"]) == ("PASS", "periods") and len(gate["evidence"]) == 2
    assert set(gate["checks"][0]) == CHECK_KEYS and gate["checks"][0]["required_months"] == 36


def test_review_jobs_stay_in_the_flow(client, db, world, queued):
    _, h, cv = _seeker(client, db, "junior@seeker.test", "박하은", JUNIOR_CV)
    job = _job(client, world, 3)
    assert client.get(RECO, headers=h).json()["pending_count"] == 1 and _evaluated_jobs(db, cv) == {job}
    _finish(db, job, cv, 80)
    gate = client.get(RECO, headers=h).json()["items"][0]["required_gate"]
    assert (gate["status"], gate["basis"], gate["evidence"]) == ("REVIEW", None, [])
    assert "확인 필요" in gate["reason"]


# ── Seeker job detail ──


def test_job_detail_shows_the_gate_with_every_status(client, db, world, queued):
    _, h, cv = _seeker(client, db, "zero@seeker.test", "이민수", ZERO_CV)
    job = _job(client, world, 3)
    body = client.get(f"/api/jobs/{job}/match", headers=h).json()
    assert body["status"] == "none" and body["required_gate"]["status"] == "FAIL"
    check = body["required_gate"]["checks"][0]
    assert (check["required_months"], check["candidate_months"], check["basis"]) == (36, 0, "stated")
    assert body["required_gate"]["evidence"] == ["경력: 0년"] and "최소 경력 3년에 미달" in body["required_gate"]["reason"]

    # Read-only scores (D43) are still shown next to a FAIL gate; nothing is queued by job detail
    _finish(db, job, cv, 70)
    body = client.get(f"/api/jobs/{job}/match", headers=h).json()
    assert body["status"] == "done" and body["match_score"] is not None and body["required_gate"]["status"] == "FAIL"
    assert queued == []

    # Applying stays possible whatever the gate says; an applied job shows no score and no gate
    assert client.post(f"/api/jobs/{job}/applications", headers=h).status_code == 201
    body = client.get(f"/api/jobs/{job}/match", headers=h).json()
    assert (body["status"], body["required_gate"]) == ("none", None)


# ── Talent and offers ──


def test_talent_leaves_out_fail_and_shows_status_only(client, db, world, queued):
    job = _job(client, world, 3)
    zero, _, zero_cv = _seeker(client, db, "zero@seeker.test", "이민수", ZERO_CV, public=True)
    five, _, five_cv = _seeker(client, db, "five@seeker.test", "최도윤", FIVE_CV, public=True)
    junior, _, junior_cv = _seeker(client, db, "junior@seeker.test", "박하은", JUNIOR_CV, public=True)
    r = client.get(f"/api/jobs/{job}/talent", headers=world["recruiter"]).json()
    assert r["pending_count"] == 2
    queued_cvs = {ev.cv_profile_id for ev in db.scalars(select(Evaluation).where(Evaluation.job_id == job))}
    assert queued_cvs == {five_cv, junior_cv}  # the FAIL candidate is never evaluated for this job

    for cv in (zero_cv, five_cv, junior_cv):
        _finish(db, job, cv, 80)
    items = client.get(f"/api/jobs/{job}/talent", headers=world["recruiter"]).json()["items"]
    by_id = {i["anonymous_id"]: i for i in items}
    anon = {u: talent_service.anonymous_id(world["acme"].id, u.id) for u in (zero, five, junior)}
    assert set(by_id) == {anon[five], anon[junior]}
    assert by_id[anon[five]]["required_gate"] == {"status": "PASS"}
    assert by_id[anon[junior]]["required_gate"] == {"status": "REVIEW"}
    body = json.dumps(items, ensure_ascii=False)
    assert "경력: 5년" not in body and "evidence" not in body and "reason" not in body


def test_offers_follow_the_talent_list(client, db, world, queued):
    job = _job(client, world, 3)
    zero, _, zero_cv = _seeker(client, db, "zero@seeker.test", "이민수", ZERO_CV, public=True)
    junior, _, junior_cv = _seeker(client, db, "junior@seeker.test", "박하은", JUNIOR_CV, public=True)
    for cv in (zero_cv, junior_cv):
        _finish(db, job, cv, 80)

    def offer(user):
        body = {"job_id": job, "anonymous_id": talent_service.anonymous_id(world["acme"].id, user.id)}
        return client.post("/api/talent-offers", json=body, headers=world["recruiter"])

    r = offer(zero)
    assert (r.status_code, r.json()["code"]) == (404, "TALENT_NOT_FOUND")  # FAIL never qualifies
    assert offer(junior).status_code == 201  # REVIEW follows the existing rules (Pref, Fit)

    # The talent list and the offer check use one rule: listed exactly when the offer check qualifies
    db.expire_all()
    job_obj = db.get(JobPosting, job)
    listed = {i["anonymous_id"] for i in client.get(f"/api/jobs/{job}/talent", headers=world["recruiter"]).json()["items"]}
    for user, pref, profile in talent_service.public_pool(db, job_obj):
        in_list = talent_service.anonymous_id(world["acme"].id, user.id) in listed
        assert (talent_service.gate_allows(job_obj, profile) is not None) == (user.id != zero.id)
        if user.id == zero.id:
            assert not in_list and not talent_service.qualifies(db, job_obj, pref, profile)


# ── Applicant list and evaluation detail ──


def test_applicant_list_labels_and_filters_but_never_excludes_or_reranks(client, db, world, queued):
    job = _job(client, world, 3)
    _, zero_h, zero_cv = _seeker(client, db, "zero@seeker.test", "이민수", ZERO_CV)
    _, kim_h, kim_cv = _seeker(client, db, "kim@seeker.test", "김지원", SAMPLE_CV)
    _, junior_h, junior_cv = _seeker(client, db, "junior@seeker.test", "박하은", JUNIOR_CV)
    for h in (zero_h, kim_h, junior_h):
        assert client.post(f"/api/jobs/{job}/applications", headers=h).status_code == 201  # direct applications always work
    assert len(queued) == 3  # applying runs the normal evaluation, FAIL included
    _finish(db, job, zero_cv, 90)
    _finish(db, job, kim_cv, 70)
    _finish(db, job, junior_cv, 50)
    before = _stored_scores(db)

    url, rh = f"/api/jobs/{job}/applications", world["recruiter"]
    body = client.get(url, headers=rh).json()
    assert body["total_count"] == 3
    rows = [(r["name"], r["rank"], r["fit"], r["status"], r["required_gate"]["status"]) for r in body["items"]]
    # Ranked by Fit as before: the FAIL applicant keeps rank 1, every status stays submitted
    assert rows == [("이민수", 1, 90.0, "submitted", "FAIL"), ("김지원", 2, 70.0, "submitted", "PASS"),
                    ("박하은", 3, 50.0, "submitted", "REVIEW")]
    assert body["items"][0]["required_gate"]["evidence"] == ["경력: 0년"]

    only_fail = client.get(url, params={"required_gate": "FAIL"}, headers=rh).json()
    assert [(r["name"], r["rank"]) for r in only_fail["items"]] == [("이민수", 1)] and only_fail["total_count"] == 3
    combined = client.get(url, params={"required_gate": "PASS", "min_fit": 60}, headers=rh).json()
    assert [r["name"] for r in combined["items"]] == ["김지원"]
    assert [r["name"] for r in client.get(url, params={"min_fit": 60}, headers=rh).json()["items"]] == ["이민수", "김지원"]
    assert client.get(url, params={"required_gate": "fail"}, headers=rh).status_code == 422

    # Evaluation detail: the full result
    app_id = body["items"][0]["application_id"]
    detail = client.get(f"/api/applications/{app_id}/evaluation", headers=rh).json()
    gate = detail["required_gate"]
    assert (gate["status"], gate["basis"]) == ("FAIL", "stated")
    assert (gate["checks"][0]["required_months"], gate["checks"][0]["candidate_months"]) == (36, 0)
    assert detail["fit"] == 90.0 and detail["notice"].startswith("AI 분석은 참고용")

    # Nothing changed: stored scores, statuses
    assert _stored_scores(db) == before
    assert {r["status"] for r in client.get(url, headers=rh).json()["items"]} == {"submitted"}


def test_gate_memo_reads_each_cv_once_per_request(client, db, world, monkeypatch):
    _, _, cv = _seeker(client, db, "kim@seeker.test", "김지원", SAMPLE_CV)
    profile = db.get(CvProfile, cv)
    reads = []
    real = gate_service.cv_service.to_profile_data
    monkeypatch.setattr(gate_service.cv_service, "to_profile_data", lambda p: reads.append(p.id) or real(p))
    gates = gate_service.Gates()
    first = gates.get(profile, 3)
    assert gates.get(profile, 3) is first and gates.get(profile, 5).status == "PASS" and gates.get(profile, None).status == "PASS"
    assert reads == [cv]
