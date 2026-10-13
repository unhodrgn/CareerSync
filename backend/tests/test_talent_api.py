"""GET /api/jobs/{job_id}/talent: opted-in seekers only, anonymous profile, Pref then Fit, caps (D3, D18, D19)."""
import json
import os
import threading
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ai.parsing.extract import verified_experience
from app.core.config import settings
from app.models import CvProfile, TalentOffer, User
from app.services import ai_runtime, evaluation_service, talent_service

from .conftest import auth
from .test_applications_api import CRITERIA, job, ready_seeker, upload  # noqa: F401  (job is a fixture)
from .test_jobs_api import make_published
from .test_recommendations_api import _done

TALENT_KEYS = {
    "anonymous_id", "fit", "criteria", "skills", "experience_years", "roles", "project_techs", "education",
    "certificates", "desired", "offer_status",
}


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluation_service, "run_in_background", lambda *args: calls.append(args))
    return calls


def _public_seeker(client, db, email, name="김지원", prefs=None, public=True):
    h = ready_seeker(client, db, email, name)
    user = db.scalars(select(User).where(User.email == email)).one()
    user.consent_version = settings.CONSENT_VERSION
    db.commit()
    body = {"locations": [], "employment_types": [], "job_keywords": [], "profile_public": public, **(prefs or {})}
    assert client.put("/api/preferences/me", json=body, headers=h).status_code == 200
    cv_id = client.get("/api/cv/me", headers=h).json()["id"]
    return user, h, cv_id


def _talent(client, world, job_id, **params):
    return client.get(f"/api/jobs/{job_id}/talent", params=params, headers=world["recruiter"])


def _ids(r) -> list[str]:
    return [i["anonymous_id"] for i in r.json()["items"]]


def _anon(world, user) -> str:
    return talent_service.anonymous_id(world["acme"].id, user.id)


# ── Who is a candidate ──


def test_only_opted_in_consented_seekers_with_a_confirmed_cv(client, db, world, job, queued):
    ok, _, ok_cv = _public_seeker(client, db, "ok@seeker.test")
    hidden, _, hidden_cv = _public_seeker(client, db, "hidden@seeker.test", public=False)
    old, _, old_cv = _public_seeker(client, db, "old@seeker.test")
    old.consent_version = "2026-10-01"
    db.commit()
    draft, draft_h, draft_cv = _public_seeker(client, db, "draft@seeker.test")
    upload(client, draft_h)  # newest version not confirmed
    applied, applied_h, applied_cv = _public_seeker(client, db, "applied@seeker.test")
    assert client.post(f"/api/jobs/{job}/applications", headers=applied_h).status_code == 201
    for cv in (ok_cv, hidden_cv, old_cv, draft_cv):
        _done(db, job, cv, 80)

    r = _talent(client, world, job)
    assert r.status_code == 200
    assert _ids(r) == [_anon(world, ok)] and r.json()["pending_count"] == 0

    # Turning the opt-in off takes effect on the next request
    client.put("/api/preferences/me", json={"profile_public": False}, headers=auth(ok))
    assert _ids(_talent(client, world, job)) == []


def test_offers_exclude_seekers(client, db, world, job, queued):
    other_job = world["job2"].id
    seekers = {}
    for name in ("pending", "accepted", "rejected_here", "rejected_elsewhere", "cancelled", "other_company"):
        user, _, cv = _public_seeker(client, db, f"{name}@seeker.test")
        _done(db, job, cv, 80)
        seekers[name] = user
    acme, rival = world["acme"].id, world["rival_job"].company_id
    db.add_all([
        TalentOffer(company_id=acme, seeker_id=seekers["pending"].id, job_id=other_job, status="pending"),
        TalentOffer(company_id=acme, seeker_id=seekers["accepted"].id, job_id=other_job, status="accepted"),
        TalentOffer(company_id=acme, seeker_id=seekers["rejected_here"].id, job_id=job, status="rejected"),
        TalentOffer(company_id=acme, seeker_id=seekers["rejected_elsewhere"].id, job_id=other_job, status="rejected"),
        TalentOffer(company_id=acme, seeker_id=seekers["cancelled"].id, job_id=job, status="cancelled"),
        TalentOffer(company_id=rival, seeker_id=seekers["other_company"].id, job_id=world["rival_job"].id, status="pending"),
    ])
    db.commit()
    items = {i["anonymous_id"]: i for i in _talent(client, world, job).json()["items"]}
    expected = {name: _anon(world, seekers[name]) for name in ("rejected_elsewhere", "cancelled", "other_company")}
    assert set(items) == set(expected.values())
    assert items[expected["cancelled"]]["offer_status"] == "cancelled"
    assert items[expected["other_company"]]["offer_status"] is None  # another company's offer is not shown


# ── Pref, Fit, order ──


def test_pref_then_fit_and_order(client, db, world, queued):
    job_id = make_published(client, world["recruiter"], location="서울 강남구")["id"]
    high, _, high_cv = _public_seeker(client, db, "high@seeker.test", prefs={"locations": ["서울"]})
    mid, _, mid_cv = _public_seeker(client, db, "mid@seeker.test")
    low, _, low_cv = _public_seeker(client, db, "low@seeker.test")
    busan, _, busan_cv = _public_seeker(client, db, "busan@seeker.test", prefs={"locations": ["부산"]})
    for cv, fit in ((high_cv, 90), (mid_cv, 70), (low_cv, 30), (busan_cv, 100)):
        _done(db, job_id, cv, fit)
    r = _talent(client, world, job_id)
    assert [(i["anonymous_id"], i["fit"]) for i in r.json()["items"]] == [(_anon(world, high), 90.0), (_anon(world, mid), 70.0)]
    assert _ids(_talent(client, world, job_id, limit=1)) == [_anon(world, high)]
    assert _talent(client, world, job_id, limit=0).status_code == 422


# ── What the company sees ──


def test_anonymous_profile_shows_only_safe_fields(client, db, world, job, queued):
    user, h, cv_id = _public_seeker(client, db, "kim@seeker.test", prefs={"job_keywords": ["백엔드"]})
    # The seeker stretches dates and adds a skill in the structured CV: not shown
    cv = client.get("/api/cv/me", headers=h).json()
    for e in cv["profile"]["experiences"]:
        e["start"] = "2005-01"
    cv["profile"]["skills"].append("Rust")
    db.expire_all()  # requests share this test session; a real request loads the document's versions fresh
    cv_id = client.put(f"/api/cv/{cv['id']}", json={"profile": cv["profile"], "confirm": True}, headers=h).json()["id"]
    _done(db, job, cv_id, 80)

    item = _talent(client, world, job).json()["items"][0]
    assert set(item) == TALENT_KEYS
    row = db.get(CvProfile, cv_id)
    months, _ = verified_experience(row.document.masked_text, [], date.today().strftime("%Y-%m"))
    assert item["experience_years"] == months // 12
    assert "Java" in item["skills"] and "Rust" not in item["skills"]
    assert item["roles"] == ["백엔드 개발자", "서버 개발"]
    assert {"Python", "FastAPI", "Docker", "AWS"} <= set(item["project_techs"])
    assert item["education"] == [{"degree": "학사", "major": "컴퓨터공학과"}]
    assert "정보처리기사" in item["certificates"]
    assert item["desired"]["job_keywords"] == ["백엔드"]
    assert {c["name"] for c in item["criteria"]} == {c["name"] for c in CRITERIA}
    assert all(set(c) == {"criterion_id", "name", "score", "level"} for c in item["criteria"])

    body = json.dumps(item, ensure_ascii=False)
    for secret in ("김지원", "kim@seeker.test", "한국대학교", "넥스트코드", "에이비씨소프트", "쇼핑몰 추천 시스템", "2021.03", "2021-03",
                   "reason", "evidence", "summary"):
        assert secret not in body, secret


def test_anonymous_id_is_stable_per_company_and_differs_across_companies(client, db, world, job, queued):
    user, _, cv = _public_seeker(client, db, "kim@seeker.test")
    _done(db, job, cv, 80)
    first, second = _ids(_talent(client, world, job)), _ids(_talent(client, world, job))
    assert first == second == [_anon(world, user)]
    assert talent_service.anonymous_id(world["rival_job"].company_id, user.id) != first[0]
    assert first[0].startswith("C-") and len(first[0]) == 12


# ── Caps ──


def test_per_call_cap(client, db, world, job, queued):
    for i in range(12):
        _public_seeker(client, db, f"s{i}@seeker.test")
    assert _talent(client, world, job).json()["pending_count"] == 12
    assert len(queued) == settings.TALENT_MAX_NEW_EVALUATIONS == 10
    _talent(client, world, job)
    assert len(queued) == 12 and len({args[1] for args in queued}) == 12


@pytest.mark.parametrize("mode, expected", [("llm", 3), ("rules", 5)])
def test_daily_cap_only_in_llm_mode(client, db, world, job, queued, monkeypatch, mode, expected):
    monkeypatch.setattr(ai_runtime, "mode", lambda: mode)
    monkeypatch.setattr(settings, "TALENT_DAILY_NEW_EVALUATIONS", 3)
    for i in range(5):
        _public_seeker(client, db, f"s{i}@seeker.test")
    _talent(client, world, job)
    _talent(client, world, job)
    assert len(queued) == expected


def test_the_daily_count_includes_seeker_side_queues(client, db, world, job, queued):
    """Counted generously: a seeker's own job recommendation of this company's job also uses a slot."""
    user, h, _ = _public_seeker(client, db, "kim@seeker.test")
    assert client.get("/api/recommendations/jobs", headers=h).status_code == 200
    assert talent_service.queued_today(db, world["acme"].id) == 1


# ── Who may call ──


def test_access(client, db, world, job):
    assert _talent(client, world, world["job2"].id).status_code == 404  # own draft
    r = client.get(f"/api/jobs/{job}/talent", headers=world["rival"])
    assert (r.status_code, r.json()["code"]) == (404, "JOB_NOT_FOUND")
    assert client.get(f"/api/jobs/{job}/talent", headers=world["seeker"]).status_code == 403
    assert client.get(f"/api/jobs/{job}/talent").status_code == 401


# ── Real concurrency: PostgreSQL only ──


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)
def test_pg_parallel_calls_respect_the_company_daily_cap(client, db, world, job, queued, monkeypatch):
    monkeypatch.setattr(ai_runtime, "mode", lambda: "llm")
    monkeypatch.setattr(settings, "TALENT_DAILY_NEW_EVALUATIONS", 5)
    for i in range(8):
        _public_seeker(client, db, f"s{i}@seeker.test")
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    n = 6
    barrier = threading.Barrier(n)
    results, lock = [], threading.Lock()

    def call():
        session = sessions()
        try:
            recruiter = session.scalars(select(User).where(User.email == "hr@acme.test")).one()
            barrier.wait()
            reco = talent_service.recommend(session, recruiter, job, 20)
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
    assert len(queued_ids) == 5 and len(set(queued_ids)) == 5
