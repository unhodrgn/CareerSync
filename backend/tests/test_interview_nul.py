"""U+0000 is refused, never stripped, at the boundaries of the practice interview (M4 S3c, D65).

PostgreSQL TEXT and JSONB cannot hold the NUL character, SQLite can, so a transcript line or a plan with one passes every SQLite test and
fails in production with a database error whose log line carries the row. These tests show the refusal itself, which does not depend on the
database: a turn is refused with 422 `INTERVIEW_BAD_TURN` before anything is written, and a plan is refused with `PlanRefused` at three
points (the cleaned CV, before any model sees it; the questions the model made; the canonical plan that would be stored), which the
lifecycle turns into 422 `INTERVIEW_NOT_AVAILABLE`. The PostgreSQL side (what the database does with it) is in
test_interview_nul_postgres.py, PostgreSQL only."""
import dataclasses

import pytest

from ai.career.interview import Question
from ai.interview import InterviewPlan, RubricPoint, clean_cv
from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn
from app.services import ai_runtime
from app.services import interview_plan_service as plan_service
from app.services import interview_service as svc
from app.services.career_service import interview_blocklists

from .interview_feedback_fixtures import plan_item
from .interview_fixtures import SAMPLE_CV, Clock, PlanLLM, build_world, new_session, turn_rows
from .test_interview_ingest_end import end_ev, refuse_end
from .test_interview_ingest_turns import ev, rec, refuse, row, started, unchanged

NUL = "\x00"


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


# ── The check itself ──


def test_has_nul_looks_at_every_string_a_plan_can_hold():
    has = plan_service.has_nul
    assert has(f"a{NUL}b") and has(NUL) and not has("") and not has("a b")
    assert has({"k": ["x", ("y", f"z{NUL}")]}) and has({f"k{NUL}": 1}) and has({"a": {"b": {"c": [NUL]}}})
    assert has({"a", f"b{NUL}"}) and has(frozenset({NUL}))
    assert not has({"items": [{"n": 1, "ok": True, "none": None, "f": 1.5, "s": "text"}]}) and not has(None) and not has(3)
    question = Question("질문", 1, "Java", "technical", "확인", ("팁",), None)
    assert not has(question) and not has([question])
    for field in ("question", "criterion_name", "kind", "intent", "cv_quote"):
        assert has(dataclasses.replace(question, **{field: f"x{NUL}"})), field
    assert has(dataclasses.replace(question, answer_tips=("팁", f"x{NUL}")))
    assert not has(Question)  # a class is not an instance


# ── A turn ──


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


@pytest.mark.parametrize("text", [NUL, f"{NUL}답변", f"답변{NUL}", f"Java를 {NUL}써 봤습니다.", f"앞{NUL}{NUL}뒤"])
def test_a_candidate_text_with_nul_is_refused_and_nothing_is_written(db, clock, sid, text):
    plan = started(db, sid, clock)
    before = [(t.seq, t.text) for t in turn_rows(db, sid)]
    coverage = row(db, sid).coverage
    refuse(db, sid, ev(plan, 2, "candidate", "answer", text=text), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    assert [(t.seq, t.text) for t in turn_rows(db, sid)] == before  # not stored, and not stored with the character removed
    assert row(db, sid).coverage == coverage


def test_the_first_turn_with_nul_does_not_start_the_session(db, clock, sid):
    plan = InterviewPlan.from_dict(row(db, sid).plan)
    refuse(db, sid, ev(plan, 1, "agent", "question", text=f"질문{NUL}입니다."), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    unchanged(db, sid)  # still `created`, no turn, no coverage


def test_an_agent_line_with_nul_is_refused_too(db, clock, sid):
    plan = started(db, sid, clock)
    refuse(db, sid, ev(plan, 2, "agent", "follow_up", text=f"조금 더{NUL} 설명해 주세요."), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    assert [t.seq for t in turn_rows(db, sid)] == [1]


def test_a_closing_line_with_nul_is_refused_and_the_session_stays_live(db, clock, sid):
    plan = started(db, sid, clock)
    event = end_ev(plan, 2, text=f"수고하셨습니다.{NUL}")
    refuse_end(db, sid, event, clock, 422, "INTERVIEW_BAD_TURN", field="text")
    r = row(db, sid)
    assert (r.status, r.end_reason) == ("live", None) and [t.kind for t in turn_rows(db, sid)] == ["question"]


def test_a_text_without_nul_is_still_stored(db, clock, sid):
    plan = started(db, sid, clock)
    ok = ev(plan, 2, "candidate", "answer", text="Java로 API를 만들었습니다.")
    assert rec(db, sid, ok, clock).outcome == "stored"


# ── A plan ──


def make_world_with_cv(db, cv, email="s9@interview.test"):
    return build_world(db, email=email, masked_cv=cv)


def refused_creation(db, world, clock):
    with pytest.raises(AppError) as error:
        svc.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version="2026-11-26", clock=clock)
    assert (error.value.status_code, error.value.code) == (422, "INTERVIEW_NOT_AVAILABLE")
    db.rollback()
    return db.query(InterviewSession).filter_by(seeker_id=world.user.id).one()


def test_a_cv_with_nul_is_refused_before_any_model_sees_it(db, clock, monkeypatch):
    world = make_world_with_cv(db, SAMPLE_CV)
    # PostgreSQL cannot store a NUL in `cv_documents.masked_text` (the INSERT of the fixture fails there), so the text is patched in at the one place
    # the service reads the stored CV, and this runs the same on SQLite and PostgreSQL (test_interview_nul_postgres.py has the PostgreSQL-only side).
    monkeypatch.setattr(svc, "_read_stored_cv", lambda _db, _cv_document_id: SAMPLE_CV.replace("Spring Boot", f"Spring{NUL}Boot", 1))
    llm = PlanLLM(db)
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    session = refused_creation(db, world, clock)
    assert llm.calls == []  # the planning model was never asked
    assert (session.status, session.end_reason, session.plan, session.plan_sha256) == ("aborted", "plan_unavailable", None, None)
    assert db.query(InterviewTurn).count() == 0


def test_questions_with_nul_from_the_model_are_refused(db, clock, monkeypatch):
    world = make_world_with_cv(db, SAMPLE_CV)
    llm = PlanLLM(db, question=lambda _cid, name: f"{name} 경험을 말씀{NUL}해 주세요.")
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    session = refused_creation(db, world, clock)
    assert len(llm.calls) == 1  # the model was asked once, and what it made was refused
    assert (session.status, session.end_reason, session.plan) == ("aborted", "plan_unavailable", None)


def test_a_bank_field_that_would_be_discarded_is_refused_too(monkeypatch):
    """The model's `cv_quote` is cleared before the plan is built, so sealing would never see a NUL in it; the bank check refuses it anyway:
    the plan is not made from a model answer that has one."""
    from ai.interview import PlanCriterion

    from app.services.interview_plan_service import build_canonical_plan, limits_from_settings

    bank = [Question("Java를 실무에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요.", 1, "Java", "technical", "Java 경험 확인", ("구체적으로",), f"인용{NUL}문장")]
    monkeypatch.setattr(plan_service, "make_bank", lambda *args, **kwargs: (bank, "rules"))
    criteria = [PlanCriterion(1, "Java", "skill", "Java 개발 경험", "core", 0)]
    arguments = dict(
        stored_cv=SAMPLE_CV, job_title="Backend Engineer", job_text="Java/Spring 백엔드 API 개발", criteria=criteria, blocklists=interview_blocklists(),
        embedder=ai_runtime.embedder(), skills=ai_runtime.skills(), limits=limits_from_settings(), llm=None,
    )
    with pytest.raises(plan_service.PlanRefused) as refused:
        build_canonical_plan(**arguments)
    assert refused.value.code == "nul_bank"
    monkeypatch.setattr(plan_service, "make_bank", lambda *args, **kwargs: ([dataclasses.replace(bank[0], cv_quote=None)], "rules"))
    assert build_canonical_plan(**arguments).sha256  # the same bank without the character is accepted


def sealed_item(**changes):
    return dataclasses.replace(plan_item(1, "Java"), **changes)


FIELDS = {
    "question": {"question": f"Java를 실무에서 어떻게{NUL} 사용했는지 설명해 주세요."},
    "rephrase": {"rephrase": f"조금 더 쉽게{NUL} 말씀해 주세요."},
    "intent": {"intent": f"Java 경험{NUL} 확인"},
    "answer_tips": {"answer_tips": (f"구체적으로{NUL} 설명해 보세요",)},
    "criterion_name": {"criterion_name": f"Java{NUL} 활용"},
    "rubric_text": {"rubric": (RubricPoint("p1", f"핵심{NUL} 개념과 동작 방식", ("개념", "동작"), 1), RubricPoint("p2", "실제 사용 사례", ("사용", "적용"), 1))},
}


@pytest.mark.parametrize("name", list(FIELDS))
def test_a_canonical_plan_with_nul_in_any_text_field_is_refused_at_sealing(name):
    plan = InterviewPlan((sealed_item(**FIELDS[name]),), ())
    clean = clean_cv(SAMPLE_CV)
    with pytest.raises(plan_service.PlanRefused) as refused:
        plan_service.seal(plan, clean, interview_blocklists())
    assert refused.value.code == "nul_plan", name


def test_a_clean_plan_is_still_sealed():
    sealed = plan_service.seal(InterviewPlan((sealed_item(),), ()), clean_cv(SAMPLE_CV), interview_blocklists())
    assert sealed.sha256 and not plan_service.has_nul(sealed.data)
