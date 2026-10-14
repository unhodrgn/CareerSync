"""CV self-check `POST /api/cv/{profile_id}/review` (docs/DECISIONS.md D25)."""
import os
import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ai.llm.client import LLMError
from ai.tests.helpers import SAMPLE_CV
from app.core.config import settings
from app.core.errors import AppError
from app.models import CareerContent, CvProfile, CvReview, User
from app.services import ai_runtime, cv_review_service
from tests.test_applications_api import confirm, seeker, upload


class ReviewLLM:
    """Answers CV review prompts with two strengths quoting lines of the CV it was sent, plus one improvement;
    anything else (CV structuring during upload) fails, so it falls back to rules. Thread-safe. No network."""

    model = "fake-llm"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def complete_json(self, system, user, schema, max_tokens=4000):
        if "You review a job seeker's CV" not in system:
            raise LLMError("not a CV review prompt")
        with self._lock:
            self.calls.append(user)
        if self.fail:
            raise LLMError("down")
        lines = [line.strip() for line in user.splitlines() if "MySQL" in line or "FastAPI" in line]
        return schema.model_validate(
            {
                "strengths": [
                    {"title": "성능 개선 경험", "detail": "개선 결과가 수치로 드러납니다.", "cv_quote": lines[0]},
                    {"title": "리더십", "detail": "팀을 이끈 경험이 있습니다.", "cv_quote": lines[1]},
                    {"title": "지어낸 강점", "detail": "없는 내용입니다.", "cv_quote": "- 하루 1억 건 처리"},
                ],
                "improvements": [
                    {"title": "자기소개 추가", "detail": "짧은 자기소개를 추가해 보세요.", "cv_quote": None},
                    {"title": "나이 기재", "detail": "나이를 적어 주세요.", "cv_quote": None},
                ],
            }
        )


@pytest.fixture
def llm_mode(monkeypatch):
    llm = ReviewLLM()
    monkeypatch.setattr(ai_runtime, "mode", lambda: "llm")
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    return llm


def _cv(client, db, email="kim@seeker.test", name="김지원"):
    h = seeker(db, email, name)
    cv = upload(client, h).json()
    return h, cv


def _review(client, h, profile_id):
    return client.post(f"/api/cv/{profile_id}/review", headers=h)


def test_rules_review_of_an_unconfirmed_version(client, db):
    h, cv = _cv(client, db)
    assert cv["confirmed"] is False
    r = _review(client, h, cv["id"])
    assert r.status_code == 200, r.json()
    body = r.json()
    assert set(body) == {"profile_id", "strengths", "improvements", "method", "limited", "notice"}
    assert body["profile_id"] == cv["id"] and body["method"] == "rules" and body["limited"] is False
    assert "참고용" in body["notice"]
    assert body["strengths"] and all(s["cv_quote"] for s in body["strengths"])
    assert set(body["strengths"][0]) == {"title", "detail", "cv_quote", "affects_scoring"}
    assert db.scalars(select(CvReview)).all() == []  # rules reviews are not stored


def test_editor_only_skill_is_flagged_on_that_version(client, db):
    h, cv = _cv(client, db)
    cv["profile"]["skills"].append("Kubernetes")
    edited = confirm(client, h, cv).json()
    flagged = [i for i in _review(client, h, edited["id"]).json()["improvements"] if i["affects_scoring"]]
    assert any("Kubernetes" in i["detail"] for i in flagged)
    original = _review(client, h, cv["id"]).json()["improvements"]
    assert not any("Kubernetes" in i["detail"] for i in original)


def test_access(client, db, world):
    h, cv = _cv(client, db)
    other, _ = _cv(client, db, "park@seeker.test", "박하은")
    r = _review(client, other, cv["id"])
    assert r.status_code == 404 and r.json()["code"] == "CV_NOT_FOUND"
    assert _review(client, h, 9999).status_code == 404
    assert _review(client, world["recruiter"], cv["id"]).status_code == 403
    assert client.post(f"/api/cv/{cv['id']}/review").status_code == 401


def test_needs_ai_consent_but_not_the_newest_version(client, db):
    h, cv = _cv(client, db)
    user = db.scalars(select(User).where(User.email == "kim@seeker.test")).one()
    assert user.consent_version is None  # consented to an older text: still allowed (D17)
    assert _review(client, h, cv["id"]).status_code == 200
    assert client.delete("/api/users/me/consent/ai", headers=h).status_code == 200
    r = _review(client, h, cv["id"])
    assert r.status_code == 409 and r.json()["code"] == "AI_CONSENT_REQUIRED"


def test_llm_review_is_validated_cached_and_sees_masked_text_only(client, db, llm_mode):
    h, cv = _cv(client, db)
    body = _review(client, h, cv["id"]).json()
    assert body["method"] == "llm:fake-llm" and body["limited"] is False
    assert [s["title"] for s in body["strengths"]] == ["성능 개선 경험", "리더십"]  # unverified quote dropped
    assert "자기소개 추가" in [i["title"] for i in body["improvements"]]
    assert "나이 기재" not in [i["title"] for i in body["improvements"]]  # blocklist
    [sent] = llm_mode.calls
    assert "[이메일]" in sent and "jiwon.kim@example.com" not in sent and "김지원" not in sent and "010-1234" not in sent
    assert len(db.scalars(select(CvReview)).all()) == 1

    # Another version of the same document reuses the LLM part; its own rule findings are added
    cv["profile"]["skills"].append("Kubernetes")
    edited = confirm(client, h, cv).json()
    again = _review(client, h, edited["id"]).json()
    assert len(llm_mode.calls) == 1 and again["method"] == "llm:fake-llm"
    assert again["strengths"] == body["strengths"]
    assert again["improvements"][0]["affects_scoring"] and "Kubernetes" in again["improvements"][0]["detail"]


def test_llm_failure_returns_rules_and_stores_nothing(client, db, llm_mode):
    llm_mode.fail = True
    h, cv = _cv(client, db)
    body = _review(client, h, cv["id"]).json()
    assert body["method"] == "rules" and body["limited"] is False and body["strengths"]
    assert db.scalars(select(CvReview)).all() == []
    llm_mode.fail = False
    assert _review(client, h, cv["id"]).json()["method"] == "llm:fake-llm"  # retried
    assert len(llm_mode.calls) == 2


def test_daily_limit_is_shared_with_career_content(client, db, world, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 2)
    h, cv = _cv(client, db)
    user = db.scalars(select(User).where(User.email == "kim@seeker.test")).one()
    # One roadmap generated by the LLM today
    db.add(
        CareerContent(
            seeker_id=user.id, job_id=world["job"].id, cv_profile_id=cv["id"], kind="roadmap", prompt_version="v1",
            method="llm:fake-llm", content={}, created_at=datetime.now(UTC),
        )
    )
    db.commit()
    assert _review(client, h, cv["id"]).json()["method"] == "llm:fake-llm"
    # A second CV document needs a new generation: over the shared limit
    second = upload(client, h, SAMPLE_CV.replace("SQLD", "ADsP")).json()
    body = _review(client, h, second["id"]).json()
    assert body["method"] == "rules" and body["limited"] is True and body["strengths"]
    assert len(llm_mode.calls) == 1
    # The cached review stays available over the limit
    assert _review(client, h, cv["id"]).json()["limited"] is False


def test_rules_mode_has_no_limit(client, db, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 0)
    h, cv = _cv(client, db)
    assert all(_review(client, h, cv["id"]).json()["limited"] is False for _ in range(3))


# ── Real concurrency: PostgreSQL only ──

on_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)


def _parallel(db, profile_ids):
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(len(profile_ids))
    outcomes, lock = [], threading.Lock()

    def run(profile_id):
        session = sessions()
        try:
            user = session.scalars(select(User).where(User.email == "kim@seeker.test")).one()
            barrier.wait()
            out = cv_review_service.review(session, user, profile_id)
            result = "limited" if out.limited else out.method
        except AppError as e:
            result = e.code
        finally:
            session.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=run, args=(p,)) for p in profile_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return sorted(outcomes)


@on_postgres
def test_pg_parallel_reviews_of_one_document_call_the_llm_once(client, db, llm_mode):
    h, cv = _cv(client, db)
    assert _parallel(db, [cv["id"]] * 5) == ["llm:fake-llm"] * 5
    assert len(llm_mode.calls) == 1 and len(db.scalars(select(CvReview)).all()) == 1


@on_postgres
def test_pg_parallel_reviews_respect_the_daily_limit(client, db, llm_mode, monkeypatch):
    monkeypatch.setattr(settings, "CAREER_DAILY_LLM_GENERATIONS", 2)
    h, first = _cv(client, db)
    ids = [first["id"]] + [upload(client, h, SAMPLE_CV + f"\n비고 {i}").json()["id"] for i in range(3)]
    assert len({db.get(CvProfile, i).cv_document_id for i in ids}) == 4
    assert _parallel(db, ids) == ["limited"] * 2 + ["llm:fake-llm"] * 2
    assert len(llm_mode.calls) == 2
