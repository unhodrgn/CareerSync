"""POST /api/jobs/{job_id}/roadmap (D21): gaps, cache, daily LLM limit, fallbacks, who may call."""
import os
import re
import threading
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ai.llm.client import LLMError
from app.core.config import settings
from app.models import CareerContent, JobPosting, User
from app.services import ai_runtime, career_service

from .test_applications_api import upload
from .test_jobs_api import make_published
from .test_recommendations_api import _seeker

GAP_JD = "Kubernetes, Kafka 기반 데이터 플랫폼 운영. SQLP 우대"


class RoadmapLLM:
    """Writes one step per gap it is given; records calls. No network."""

    model = "fake-llm"

    def __init__(self, fail=False):
        self.calls, self.fail, self._lock = [], fail, threading.Lock()

    def complete_json(self, system, user, schema, max_tokens=4000):
        if "<gaps>" not in user:
            raise LLMError("only roadmaps here")  # e.g. CV structuring during upload falls back to rules
        with self._lock:
            self.calls.append(user)
        if self.fail:
            raise LLMError("down")
        gaps = re.search(r"<gaps>\n(.*?)\n</gaps>", user, re.S).group(1).splitlines()
        names = [g.split(": ", 1)[1] for g in gaps]
        return schema.model_validate({"steps": [{"skill": n, "goal": f"{n} 실무 활용", "activities": ["학습", "실습"]} for n in names]})


@pytest.fixture
def llm_mode(monkeypatch):
    llm = RoadmapLLM()
    monkeypatch.setattr(ai_runtime, "mode", lambda: "llm")
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    return llm


def _job(client, world, **overrides) -> int:
    return make_published(client, world["recruiter"], description=GAP_JD, **overrides)["id"]


def _roadmap(client, h, job_id):
    return client.post(f"/api/jobs/{job_id}/roadmap", headers=h)


def _rows(db) -> list[CareerContent]:
    db.expire_all()
    return list(db.scalars(select(CareerContent)))


def test_rules_mode_template_is_cached(client, db, world):
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    r = _roadmap(client, h, job_id)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["method"] == "rules" and body["limited"] is False and body["notice"].startswith("AI 분석은 참고용")
    assert body["gaps"] == [{"name": "Kubernetes", "kind": "skill"}, {"name": "Kafka", "kind": "skill"}, {"name": "SQLP", "kind": "certificate"}]
    assert [s["skill"] for s in body["steps"]] == ["Kubernetes", "Kafka", "SQLP"]
    assert body["steps"][0]["resources"] == [{"title": "Kubernetes 기초 튜토리얼", "url": "https://kubernetes.io/docs/tutorials/kubernetes-basics/"}]
    assert _roadmap(client, h, job_id).json() == body
    assert [(c.kind, c.method) for c in _rows(db)] == [("roadmap", "rules")]


def test_no_gaps_returns_a_message_without_llm_or_cache(client, db, world, llm_mode):
    _, h = _seeker(client, db)
    job_id = make_published(client, world["recruiter"], description="Java, Spring 기반 API 개발")["id"]
    body = _roadmap(client, h, job_id).json()
    assert (body["gaps"], body["steps"], body["method"]) == ([], [], "rules")
    assert body["message"] == career_service.NO_GAP_MESSAGE
    assert llm_mode.calls == [] and _rows(db) == []


def test_llm_result_is_cached_per_cv_version(client, db, world, llm_mode):
    user, h = _seeker(client, db)
    job_id = _job(client, world)
    first = _roadmap(client, h, job_id).json()
    assert first["method"] == "llm:fake-llm" and first["steps"][0]["goal"] == "Kubernetes 실무 활용"
    assert _roadmap(client, h, job_id).json() == first and len(llm_mode.calls) == 1
    # A newly confirmed CV version generates again
    cv = upload(client, h).json()
    db.expire_all()
    client.put(f"/api/cv/{cv['id']}", json={"profile": cv["profile"], "confirm": True}, headers=h)
    _roadmap(client, h, job_id)
    assert len(llm_mode.calls) == 2 and len(_rows(db)) == 2


def test_llm_never_sees_personal_data(client, db, world, llm_mode):
    _seeker_user, h = _seeker(client, db)
    _roadmap(client, h, _job(client, world))
    (prompt,) = llm_mode.calls
    for secret in ("김지원", "kim@seeker.test", "jiwon.kim@example.com", "010-1234-5678", "넥스트코드"):
        assert secret not in prompt


def test_llm_failure_falls_back_and_is_not_cached(client, db, world, llm_mode):
    llm_mode.fail = True
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    assert _roadmap(client, h, job_id).json()["method"] == "rules"
    assert _rows(db) == []
    llm_mode.fail = False
    assert _roadmap(client, h, job_id).json()["method"] == "llm:fake-llm"  # retried, now cached
    assert len(_rows(db)) == 1


def test_daily_llm_limit(client, db, world, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 1)
    _, h = _seeker(client, db)
    a, b = _job(client, world, title="A"), _job(client, world, title="B")
    assert _roadmap(client, h, a).json()["method"] == "llm:fake-llm"
    limited = _roadmap(client, h, b).json()
    assert (limited["method"], limited["limited"]) == ("rules", True) and limited["steps"]
    assert _roadmap(client, h, a).json()["method"] == "llm:fake-llm"  # cached: no slot needed
    assert len(llm_mode.calls) == 1 and len(_rows(db)) == 1


def test_rules_mode_has_no_limit(client, db, world, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 0)
    _, h = _seeker(client, db)
    assert _roadmap(client, h, _job(client, world)).json()["limited"] is False


def test_who_may_call(client, db, world):
    from .test_applications_api import seeker

    user, h = _seeker(client, db)
    draft = world["job2"].id
    expired = _job(client, world, title="마감")
    db.get(JobPosting, expired).deadline = date.today() - timedelta(days=1)
    db.commit()
    for job_id in (draft, expired, 99999):
        r = _roadmap(client, h, job_id)
        assert (r.status_code, r.json()["code"]) == (404, "JOB_NOT_FOUND"), job_id
    open_job = _job(client, world)
    user.consent_version = "2026-10-01"
    db.commit()
    assert _roadmap(client, h, open_job).json()["code"] == "AI_CONSENT_REQUIRED"
    no_cv = seeker(db, "nocv@seeker.test", "이수진")
    db.scalars(select(User).where(User.email == "nocv@seeker.test")).one().consent_version = settings.CONSENT_VERSION
    db.commit()
    assert _roadmap(client, no_cv, open_job).json()["code"] == "CV_NOT_CONFIRMED"
    assert _roadmap(client, world["recruiter"], open_job).json()["code"] == "SEEKER_ONLY"
    assert client.post(f"/api/jobs/{open_job}/roadmap").status_code == 401


# ── Real concurrency: PostgreSQL only ──


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)
def test_pg_parallel_generations_respect_the_limit_and_cache(client, db, world, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 2)
    _seeker(client, db)
    jobs = [_job(client, world, title=f"공고 {i}") for i in range(3)]
    targets = [jobs[0]] * 3 + jobs[1:] * 2  # the same job three times, the others twice
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(len(targets))
    methods, lock = [], threading.Lock()

    def call(job_id):
        session = sessions()
        try:
            user = session.scalars(select(User).where(User.email == "kim@seeker.test")).one()
            barrier.wait()
            out = career_service.roadmap(session, user, job_id)
            with lock:
                methods.append((job_id, out.method, out.limited))
        finally:
            session.close()

    threads = [threading.Thread(target=call, args=(j,)) for j in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(methods) == len(targets)
    assert len(llm_mode.calls) == 2  # never more generations than the limit
    rows = _rows(db)
    assert len(rows) == 2 and len({r.job_id for r in rows}) == 2  # one cached result per job, no duplicates
    # Every call got either an LLM roadmap (new or cached) or the template marked as limited
    assert all(m.startswith("llm:") or (m == "rules" and limited) for _, m, limited in methods)
    assert {j for j, m, _ in methods if m.startswith("llm:")} == {r.job_id for r in rows}
