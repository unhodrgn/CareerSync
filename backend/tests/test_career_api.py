"""POST /api/jobs/{job_id}/roadmap and /interview-questions (D21): gaps, cache, shared daily LLM limit,
fallbacks, who may call."""
import os
import re
import threading
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ai.llm.client import LLMError
from app.core.config import settings
from app.models import CareerContent, CvProfile, JobPosting, User
from app.services import ai_runtime, career_service

from .test_applications_api import upload
from .test_jobs_api import make_published
from .test_recommendations_api import _seeker

GAP_JD = "Kubernetes, Kafka 기반 데이터 플랫폼 운영. SQLP 우대"


class CareerLLM:
    """Answers roadmap prompts (one step per gap) and interview prompts (one question per criterion, quoting the
    first CV excerpt line); records those calls. Anything else (e.g. CV structuring during upload) fails, so it
    falls back to rules. No network."""

    model = "fake-llm"

    def __init__(self, fail=False):
        self.calls, self.fail, self._lock = [], fail, threading.Lock()

    def complete_json(self, system, user, schema, max_tokens=4000):
        if "<gaps>" not in user and "<cv_excerpts>" not in user:
            raise LLMError("only career content here")
        with self._lock:
            self.calls.append(user)
        if self.fail:
            raise LLMError("down")
        if "<gaps>" in user:
            gaps = re.search(r"<gaps>\n(.*?)\n</gaps>", user, re.S).group(1).splitlines()
            names = [g.split(": ", 1)[1] for g in gaps]
            return schema.model_validate({"steps": [{"skill": n, "goal": f"{n} 실무 활용", "activities": ["학습", "실습"]} for n in names]})
        criteria = re.search(r"<criteria>\n(.*?)\n</criteria>", user, re.S).group(1).splitlines()
        quote = re.search(r"<cv_excerpts>\n(.*?)\n", user).group(1)
        questions = [
            {"question": f"{line.split(' | ')[1]} 관련 경험을 말씀해 주세요.", "criterion_id": int(line.split(" | ")[0]),
             "kind": "experience", "intent": "경험 확인", "answer_tips": ["구체적으로"], "cv_quote": quote}
            for line in criteria
        ]
        return schema.model_validate({"questions": questions})


@pytest.fixture
def llm_mode(monkeypatch):
    llm = CareerLLM()
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


# ── Interview questions ──


def _interview(client, h, job_id):
    return client.post(f"/api/jobs/{job_id}/interview-questions", headers=h)


def _criterion_ids(client, world, job_id) -> set[int]:
    return {c["id"] for c in client.get(f"/api/jobs/{job_id}/criteria", headers=world["recruiter"]).json()["items"]}


def test_interview_rules_mode_is_cached(client, db, world):
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    r = _interview(client, h, job_id)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["method"] == "rules" and body["limited"] is False and body["notice"].startswith("AI 분석은 참고용")
    assert 3 <= len(body["questions"]) <= 10
    ids = {q["criterion_id"] for q in body["questions"]} - {None}
    assert ids and ids <= _criterion_ids(client, world, job_id)
    assert _interview(client, h, job_id).json() == body
    assert [(c.kind, c.method) for c in _rows(db)] == [("interview", "rules")]


def test_interview_llm_is_cached_and_quotes_are_from_the_masked_cv(client, db, world, llm_mode):
    user, h = _seeker(client, db)
    job_id = _job(client, world)
    body = _interview(client, h, job_id).json()
    assert body["method"] == "llm:fake-llm"
    assert {q["criterion_id"] for q in body["questions"]} == _criterion_ids(client, world, job_id)
    cached = db.scalars(select(CareerContent)).one()
    text = db.get(CvProfile, cached.cv_profile_id).document.masked_text
    assert all(q["cv_quote"] and q["cv_quote"] in text for q in body["questions"])
    assert _interview(client, h, job_id).json() == body and len(llm_mode.calls) == 1
    for secret in ("김지원", "kim@seeker.test", "jiwon.kim@example.com", "010-1234-5678"):
        assert secret not in llm_mode.calls[0]


def test_interview_llm_failure_falls_back_and_is_not_cached(client, db, world, llm_mode):
    llm_mode.fail = True
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    assert _interview(client, h, job_id).json()["method"] == "rules"
    assert _rows(db) == []


def test_roadmap_and_interview_share_the_daily_limit(client, db, world, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 1)
    _, h = _seeker(client, db)
    job_id = _job(client, world)
    assert _roadmap(client, h, job_id).json()["method"] == "llm:fake-llm"
    limited = _interview(client, h, job_id).json()
    assert (limited["method"], limited["limited"]) == ("rules", True) and len(limited["questions"]) >= 3
    assert len(llm_mode.calls) == 1 and [c.kind for c in _rows(db)] == ["roadmap"]


def test_interview_who_may_call(client, db, world):
    user, h = _seeker(client, db)
    assert _interview(client, h, world["job2"].id).json()["code"] == "JOB_NOT_FOUND"  # draft
    open_job = _job(client, world)
    assert _interview(client, world["recruiter"], open_job).json()["code"] == "SEEKER_ONLY"
    assert client.post(f"/api/jobs/{open_job}/interview-questions").status_code == 401
    user.consent_version = "2026-10-01"
    db.commit()
    assert _interview(client, h, open_job).json()["code"] == "AI_CONSENT_REQUIRED"


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)
def test_pg_parallel_roadmaps_and_interviews_share_the_limit(client, db, world, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 3)
    _seeker(client, db)
    jobs = [_job(client, world, title=f"공고 {i}") for i in range(2)]
    targets = [(j, kind) for j in jobs for kind in ("roadmap", "interview")] * 2  # 4 distinct contents, each twice
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(len(targets))
    results, lock = [], threading.Lock()

    def call(job_id, kind):
        session = sessions()
        try:
            user = session.scalars(select(User).where(User.email == "kim@seeker.test")).one()
            barrier.wait()
            fn = career_service.roadmap if kind == "roadmap" else career_service.interview_questions
            out = fn(session, user, job_id)
            with lock:
                results.append((job_id, kind, out.method, out.limited))
        finally:
            session.close()

    threads = [threading.Thread(target=call, args=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(results) == len(targets)
    assert len(llm_mode.calls) == 3  # the limit across both kinds
    rows = _rows(db)
    assert len(rows) == 3 and len({(r.job_id, r.kind) for r in rows}) == 3
    assert all(m.startswith("llm:") or (m == "rules" and limited) for _, _, m, limited in results)
