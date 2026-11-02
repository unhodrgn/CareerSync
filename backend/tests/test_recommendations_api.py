"""GET /api/recommendations/jobs: Pref first, Fit from done evaluations, caps, match score with band, strengths and gaps
(D2, D15, D16, D42, D43). GET /api/jobs/{job_id}/match: reads an existing evaluation only (D44)."""
import os
import threading
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import CriterionScore, Evaluation, JobCriterion, JobPosting, User
from app.models.application import EvaluationStatus
from ai.career.gaps import match_skills
from ai.tests.helpers import SAMPLE_CV
from app.services import ai_runtime, evaluation_service, recommendation_service

from .test_applications_api import ready_seeker
from .test_jobs_api import make_published

URL = "/api/recommendations/jobs"
# Exact key sets: a new field fails these on purpose. Never Fit, Pref, per-criterion scores, weights or criterion names
LIST_KEYS = {"items", "pending_count", "notice"}
ITEM_KEYS = {
    "job_id", "title", "company_name", "location", "employment_type", "deadline",
    "match_score", "match_level", "strengths", "gaps",
}
MATCH_KEYS = {"job_id", "match_score", "match_level", "status", "notice"}


@pytest.fixture
def queued(monkeypatch):
    """Record background runs instead of running them, so queued evaluations stay pending."""
    calls = []
    monkeypatch.setattr(evaluation_service, "run_in_background", lambda *args: calls.append(args))
    return calls


def _seeker(client, db, email="kim@seeker.test", prefs=None):
    h = ready_seeker(client, db, email, "김지원")
    user = db.scalars(select(User).where(User.email == email)).one()
    user.consent_version = settings.CONSENT_VERSION
    db.commit()
    if prefs:
        assert client.put("/api/preferences/me", json=prefs, headers=h).status_code == 200
    return user, h


def _cv_id(client, h) -> int:
    return client.get("/api/cv/me", headers=h).json()["id"]


def _job(client, world, **overrides) -> int:
    return make_published(client, world["recruiter"], **overrides)["id"]


def _done(db, job_id: int, cv_id: int, fit: int) -> None:
    """A done evaluation scoring every criterion `fit`, so Fit == fit."""
    ev = Evaluation(job_id=job_id, cv_profile_id=cv_id, status=EvaluationStatus.DONE, queued_at=datetime.now(UTC), attempts=1)
    ev.scores = [
        CriterionScore(job_criteria_id=c.id, score=fit, level=fit, reason="", evidence=[], method="rule:test")
        for c in db.scalars(select(JobCriterion).where(JobCriterion.job_id == job_id))
    ]
    db.add(ev)
    db.commit()


def _evaluations(db) -> list[Evaluation]:
    db.expire_all()
    return list(db.scalars(select(Evaluation)))


# ── Flow ──


def test_first_call_queues_then_the_job_is_listed_with_a_band(client, db, world):
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    first = client.get(URL, headers=h).json()  # scoring runs in the background after this response
    assert (first["items"], first["pending_count"]) == ([], 1)
    second = client.get(URL, headers=h).json()
    assert second["pending_count"] == 0
    assert [i["job_id"] for i in second["items"]] == [job_id]
    assert second["items"][0]["match_level"] in {"매우 적합", "적합", "참고"}


def test_pref_runs_before_fit(client, db, world, queued):
    _, h = _seeker(client, db, prefs={"locations": ["부산"]})
    _job(client, world, location="서울 강남구")
    r = client.get(URL, headers=h).json()
    assert (r["items"], r["pending_count"]) == ([], 0)
    assert _evaluations(db) == [] and queued == []  # Pref < 40: no evaluation, no scoring cost


def test_only_published_unexpired_unapplied_jobs(client, db, world, queued):
    _, h = _seeker(client, db)
    applied = _job(client, world, title="지원한 공고")
    assert client.post(f"/api/jobs/{applied}/applications", headers=h).status_code == 201
    expired = _job(client, world, title="마감 지남")
    db.get(JobPosting, expired).deadline = date.today() - timedelta(days=1)
    db.commit()
    open_job = _job(client, world, title="열린 공고")
    r = client.get(URL, headers=h).json()
    assert r["pending_count"] == 1
    assert {ev.job_id for ev in _evaluations(db)} == {applied, open_job}  # applied one came from applying
    assert [args[1] for args in queued][-1] == next(ev.id for ev in _evaluations(db) if ev.job_id == open_job)


def test_fit_threshold_bands_and_order(client, db, world, queued):
    # 2 fields filled: a contract job in 서울 has Pref 100, a full-time one 50, one in 부산 0
    _, h = _seeker(client, db, prefs={"locations": ["서울"], "employment_types": ["contract"]})
    cv = _cv_id(client, h)
    a = _job(client, world, title="A", employment_type="contract")
    b = _job(client, world, title="B")
    c = _job(client, world, title="C")
    d = _job(client, world, title="D", employment_type="contract")
    e = _job(client, world, title="E", location="부산")
    for job_id, fit in ((a, 90), (b, 90), (c, 50), (d, 30), (e, 100)):
        _done(db, job_id, cv, fit)
    r = client.get(URL, headers=h).json()
    # Final: A 95 → 매우 적합, B 70 → 적합, C 50 → 참고; D Fit 30 < 40; E Pref 0 < 40
    assert [(i["job_id"], i["match_score"], i["match_level"]) for i in r["items"]] == [
        (a, 95, "매우 적합"), (b, 70, "적합"), (c, 50, "참고")
    ]
    assert r["pending_count"] == 0 and queued == []
    assert [i["job_id"] for i in client.get(f"{URL}?limit=2", headers=h).json()["items"]] == [a, b]
    assert client.get(f"{URL}?limit=0", headers=h).status_code == 422
    assert client.get(f"{URL}?limit=51", headers=h).status_code == 422


@pytest.mark.parametrize(
    "final, band", [(100, "매우 적합"), (80, "매우 적합"), (79.9, "적합"), (60, "적합"), (59.9, "참고"), (40, "참고")]
)
def test_band_thresholds(final, band):
    assert recommendation_service.match_level(final) == band


@pytest.mark.parametrize("final, score", [(79.5, 80), (79.4, 79), (60.5, 61), (0, 0), (100, 100), (100.4, 100)])
def test_match_score_is_final_rounded_half_up(final, score):
    assert recommendation_service.match_score(final) == score


def test_band_follows_the_shown_score(client, db, world, queued):
    # Pref 100, Fit 59 → Final 79.5: shown as 80, so the band is 매우 적합, not 적합 under an 80
    _, h = _seeker(client, db, prefs={"locations": ["서울"]})
    _done(db, _job(client, world), _cv_id(client, h), 59)
    item = client.get(URL, headers=h).json()["items"][0]
    assert (item["match_score"], item["match_level"]) == (80, "매우 적합")


def test_response_has_exactly_the_allowed_keys(client, db, world, queued):
    _, h = _seeker(client, db)
    _done(db, _job(client, world), _cv_id(client, h), 80)
    body = client.get(URL, headers=h).json()
    assert set(body) == LIST_KEYS and body["notice"].startswith("AI 분석은 참고용")
    item = body["items"][0]
    assert set(item) == ITEM_KEYS  # no fit, pref, final, per-criterion scores or weights
    assert isinstance(item["match_score"], int) and 0 <= item["match_score"] <= 100
    criteria = {c.name for c in db.scalars(select(JobCriterion))}
    assert not criteria & set(map(str, item.values()))  # no criterion name next to a score


# ── Strengths and gaps (D43) ──


def test_strengths_and_gaps_come_from_the_cv_text_and_are_capped(client, db, world, queued):
    _, h = _seeker(client, db)
    jd = "Java/Spring API 개발. Kubernetes, Kafka, Go, Rust 사용. SQLP 우대"
    job_id = _job(client, world, description=jd)
    _done(db, job_id, _cv_id(client, h), 80)
    item = client.get(URL, headers=h).json()["items"][0]
    cap = settings.RECO_MAX_SKILL_ITEMS
    assert 1 <= len(item["strengths"]) <= cap and 1 <= len(item["gaps"]) <= cap
    assert "Java" in item["strengths"] and "Kubernetes" in item["gaps"]
    skills = ai_runtime.skills()
    have = set(skills.find_in_text(SAMPLE_CV)) | {name for name, _ in skills.find_certificates(SAMPLE_CV)}
    assert set(item["strengths"]) <= have and not set(item["gaps"]) & have


def test_strengths_and_gaps_do_not_depend_on_scores(client, db, world, queued, monkeypatch):
    # The same job and CV give the same lists whatever the evaluation scored, and scoring code is not consulted
    _, h = _seeker(client, db)
    cv = _cv_id(client, h)
    a, b = _job(client, world, title="A"), _job(client, world, title="B")
    _done(db, a, cv, 100)
    _done(db, b, cv, 40)
    seen = []
    monkeypatch.setattr(recommendation_service, "match_skills", lambda *args: seen.append(args) or match_skills(*args))
    items = {i["job_id"]: i for i in client.get(URL, headers=h).json()["items"]}
    assert (items[a]["strengths"], items[a]["gaps"]) == (items[b]["strengths"], items[b]["gaps"])
    assert items[a]["match_score"] != items[b]["match_score"]
    for criteria_lines, job_text, cv_text, _ in seen:
        assert "Java 활용 능력 (skill): Java 17, 동시성" in criteria_lines and job_text.endswith("Java/Spring 기반 API 개발")
        assert "jiwon.kim@example.com" not in cv_text  # the masked text, not the raw CV
        assert not any(str(w) in line for line in criteria_lines for w in (30, 25, 20, 15, 10))  # no weights


# ── Caps and re-queues ──


def test_per_call_cap(client, db, world, queued):
    _, h = _seeker(client, db)
    for i in range(12):
        _job(client, world, title=f"공고 {i}")
    assert client.get(URL, headers=h).json()["pending_count"] == 12
    assert len(queued) == settings.RECO_MAX_NEW_EVALUATIONS == 10
    assert client.get(URL, headers=h).json()["pending_count"] == 12
    assert len(queued) == 12  # the next call queues the rest; running ones are not queued again
    assert len({args[1] for args in queued}) == 12


@pytest.mark.parametrize("mode, expected", [("llm", 3), ("rules", 5)])
def test_daily_cap_only_in_llm_mode(client, db, world, queued, monkeypatch, mode, expected):
    monkeypatch.setattr(ai_runtime, "mode", lambda: mode)
    monkeypatch.setattr(settings, "RECO_DAILY_NEW_EVALUATIONS", 3)
    _, h = _seeker(client, db)
    for i in range(5):
        _job(client, world, title=f"공고 {i}")
    client.get(URL, headers=h)
    client.get(URL, headers=h)
    assert len(queued) == expected


def test_daily_count_ignores_evaluations_of_applications(client, db, world, queued):
    user, h = _seeker(client, db)
    job_id = _job(client, world)
    assert client.post(f"/api/jobs/{job_id}/applications", headers=h).status_code == 201
    assert recommendation_service.queued_today(db, user.id) == 0
    _job(client, world, title="다른 공고")
    client.get(URL, headers=h)
    assert recommendation_service.queued_today(db, user.id) == 1


def test_attempt_limit_and_stale_requeue(client, db, world, queued):
    _, h = _seeker(client, db)
    cv = _cv_id(client, h)
    old = datetime.now(UTC) - timedelta(minutes=settings.EVALUATION_STALE_MINUTES + 1)
    rows = {
        "gave_up": dict(status=EvaluationStatus.FAILED, attempts=3, queued_at=old),
        "retry": dict(status=EvaluationStatus.FAILED, attempts=2, queued_at=old),
        "running": dict(status=EvaluationStatus.PENDING, attempts=1, queued_at=datetime.now(UTC)),
        "stale": dict(status=EvaluationStatus.PENDING, attempts=1, queued_at=old),
    }
    ids = {}
    for name, values in rows.items():
        job_id = _job(client, world, title=name)
        ev = Evaluation(job_id=job_id, cv_profile_id=cv, **values)
        db.add(ev)
        db.commit()
        ids[name] = ev.id
    r = client.get(URL, headers=h).json()
    assert r["pending_count"] == 3  # gave_up is skipped
    assert sorted(args[1] for args in queued) == sorted([ids["retry"], ids["stale"]])
    attempts = {ev.id: ev.attempts for ev in _evaluations(db)}
    assert (attempts[ids["retry"]], attempts[ids["stale"]], attempts[ids["gave_up"]]) == (3, 2, 3)


# ── Who may call ──


def test_needs_confirmed_cv_and_current_consent(client, db, world):
    from .test_applications_api import seeker

    no_cv = seeker(db, "nocv@seeker.test", "이수진")
    db.scalars(select(User).where(User.email == "nocv@seeker.test")).one().consent_version = settings.CONSENT_VERSION
    db.commit()
    r = client.get(URL, headers=no_cv)
    assert (r.status_code, r.json()["code"]) == (409, "CV_NOT_CONFIRMED")

    user, h = _seeker(client, db)
    user.consent_version = "2026-10-01"  # consented before recommendation was a stated purpose
    db.commit()
    r = client.get(URL, headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "AI_CONSENT_REQUIRED")
    # The old consent still allows applying (only recommendation needs the new version)
    assert client.post(f"/api/jobs/{_job(client, world)}/applications", headers=h).status_code == 201

    r = client.get(URL, headers=world["recruiter"])
    assert (r.status_code, r.json()["code"]) == (403, "SEEKER_ONLY")
    assert client.get(URL).status_code == 401


def test_new_registrations_get_the_current_consent_version(client):
    body = {"email": "new@seeker.test", "password": "pass1234", "role": "seeker", "display_name": "신규",
            "consent_privacy": True, "consent_ai": True}
    assert client.post("/api/auth/register", json=body).json()["consent_version"] == settings.CONSENT_VERSION
    assert settings.CONSENT_VERSION >= settings.RECO_MIN_CONSENT_VERSION


# ── GET /api/jobs/{job_id}/match (D44) ──


def _match(client, job_id, headers=None):
    return client.get(f"/api/jobs/{job_id}/match", headers=headers)


@pytest.fixture
def no_new_evaluations(monkeypatch):
    """Every way to create, queue or run an evaluation fails the test if it is called."""

    def forbidden(name):
        def fail(*args, **kwargs):
            raise AssertionError(f"/match called evaluation_service.{name}")

        return fail

    for name in ("ensure", "claim", "queue", "run_in_background", "evaluate"):
        monkeypatch.setattr(evaluation_service, name, forbidden(name))


def test_match_done_has_the_same_score_as_the_recommendation(client, db, world, queued):
    _, h = _seeker(client, db, prefs={"locations": ["서울"], "employment_types": ["contract"]})
    job_id = _job(client, world)  # full time in 서울: Pref 50
    _done(db, job_id, _cv_id(client, h), 90)
    r = _match(client, job_id, h)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == MATCH_KEYS and body["notice"].startswith("AI 분석은 참고용")
    assert (body["job_id"], body["match_score"], body["match_level"], body["status"]) == (job_id, 70, "적합", "done")
    item = client.get(URL, headers=h).json()["items"][0]
    assert (item["match_score"], item["match_level"]) == (body["match_score"], body["match_level"])


def test_match_never_creates_or_queues_an_evaluation(client, db, world, no_new_evaluations):
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    body = _match(client, job_id, h).json()
    assert set(body) == MATCH_KEYS
    assert (body["match_score"], body["match_level"], body["status"]) == (None, None, "none")
    assert _evaluations(db) == []


@pytest.mark.parametrize(
    "status, attempts, expected", [(EvaluationStatus.PENDING, 1, "pending"), (EvaluationStatus.FAILED, 1, "none"), (EvaluationStatus.FAILED, 3, "none")]
)
def test_match_pending_and_failed_leave_the_evaluation_alone(client, db, world, no_new_evaluations, status, attempts, expected):
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    old = datetime.now(UTC) - timedelta(minutes=settings.EVALUATION_STALE_MINUTES + 1)  # stale: recommendation would re-queue it
    db.add(Evaluation(job_id=job_id, cv_profile_id=_cv_id(client, h), status=status, attempts=attempts, queued_at=old))
    db.commit()
    body = _match(client, job_id, h).json()
    assert set(body) == MATCH_KEYS
    assert (body["match_score"], body["match_level"], body["status"]) == (None, None, expected)
    [ev] = _evaluations(db)
    assert (ev.status, ev.attempts, ev.queued_at.replace(tzinfo=UTC)) == (status, attempts, old)


def test_match_reads_only_the_newest_confirmed_cv(client, db, world, no_new_evaluations):
    _, h = _seeker(client, db)
    old_cv = client.get("/api/cv/me", headers=h).json()
    job_id = _job(client, world)
    _done(db, job_id, old_cv["id"], 90)
    assert _match(client, job_id, h).json()["status"] == "done"
    db.expire_all()  # the test shares one session with the app; a request would see the new version list anyway
    assert client.put(f"/api/cv/{old_cv['id']}", json={"profile": old_cv["profile"], "confirm": True}, headers=h).status_code == 200
    assert _match(client, job_id, h).json()["status"] == "none"  # the old version's score is not shown


def test_applied_jobs_show_no_score(client, db, world, queued):
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    assert client.post(f"/api/jobs/{job_id}/applications", headers=h).status_code == 201
    [ev] = _evaluations(db)
    ev.status = EvaluationStatus.DONE  # even a finished evaluation of the application is not shown
    ev.scores = [
        CriterionScore(job_criteria_id=c.id, score=90, level=90, reason="", evidence=[], method="rule:test")
        for c in db.scalars(select(JobCriterion).where(JobCriterion.job_id == job_id))
    ]
    db.commit()
    body = _match(client, job_id, h).json()
    assert (body["match_score"], body["match_level"], body["status"]) == (None, None, "none")
    assert job_id not in [i["job_id"] for i in client.get(URL, headers=h).json()["items"]]


def test_match_without_confirmed_cv_or_current_consent_is_none(client, db, world, no_new_evaluations):
    from .test_applications_api import seeker

    job_id = _job(client, world)
    no_cv = seeker(db, "nocv@seeker.test", "이수진")
    assert _match(client, job_id, no_cv).json()["status"] == "none"

    user, h = _seeker(client, db)
    _done(db, job_id, _cv_id(client, h), 90)
    user.consent_version = "2026-10-01"
    db.commit()
    assert _match(client, job_id, h).json()["status"] == "none"


def test_companies_and_guests_get_no_score_from_either_endpoint(client, db, world, queued):
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    _done(db, job_id, _cv_id(client, h), 90)
    for headers in (world["recruiter"],):  # also the company that owns the job
        for path in (URL, f"/api/jobs/{job_id}/match"):
            r = client.get(path, headers=headers)
            assert (r.status_code, r.json()["code"]) == (403, "SEEKER_ONLY")
            assert "match_score" not in r.text
    assert _match(client, job_id).status_code == 401


def test_match_404_for_jobs_the_seeker_cannot_see(client, db, world):
    from .test_jobs_api import create

    _, h = _seeker(client, db)
    draft = create(client, world["recruiter"]).json()["id"]
    closed = _job(client, world)
    assert client.post(f"/api/jobs/{closed}/close", headers=world["recruiter"]).status_code == 200
    for job_id in (draft, closed, 999999):
        r = _match(client, job_id, h)
        assert (r.status_code, r.json()["code"]) == (404, "JOB_NOT_FOUND")


# ── Real concurrency: PostgreSQL only ──


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)
def test_pg_parallel_calls_respect_the_daily_cap(client, db, world, queued, monkeypatch):
    monkeypatch.setattr(ai_runtime, "mode", lambda: "llm")
    monkeypatch.setattr(settings, "RECO_DAILY_NEW_EVALUATIONS", 10)
    _seeker(client, db)
    for i in range(20):
        _job(client, world, title=f"공고 {i}")
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    n = 6
    barrier = threading.Barrier(n)
    results, lock = [], threading.Lock()

    def call():
        session = sessions()
        try:
            user = session.scalars(select(User).where(User.email == "kim@seeker.test")).one()
            barrier.wait()
            reco = recommendation_service.recommend(session, user, 20)
            with lock:
                results.append(reco.queued)
        finally:
            session.close()

    threads = [threading.Thread(target=call) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    queued_ids = [ev_id for r in results for ev_id, _ in r]
    assert len(results) == n
    assert len(queued_ids) == 10 and len(set(queued_ids)) == 10  # cap held, nothing queued twice
