"""What PostgreSQL does with U+0000, and that the interview never gets that far (M4 S3c, D65): PostgreSQL only.

These need `TEST_DATABASE_URL=postgresql+psycopg://…/<name>_pgtest` on this machine (a throwaway database: the fixture drops every table)
and are SKIPPED without it. They ran and passed on PostgreSQL on 2026-11-22 (D77), so PostgreSQL does behave as the first two tests
assume. The refusals themselves are tested on SQLite in test_interview_nul.py.

1. The characterization tests insert a NUL straight into the tables. They assert the hazard the refusals exist for: if PostgreSQL ever
   accepts the character, the refusals are not needed any more and these tests say so by failing.
2. The end-to-end tests send a NUL through the services and assert the refusal, and that no row was written. The last one is S3c.1: a
   feedback that the model wrote with a NUL is dropped before it is stored, and PostgreSQL never raises."""
import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DBAPIError

from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn, User
from app.services import ai_runtime
from app.services import interview_feedback_service as fb
from app.services import interview_service as svc

from .interview_feedback_fixtures import SpyLLM, askable_session, install, row
from .interview_fixtures import SAMPLE_CV, Clock, PlanLLM, build_world, new_session
from .test_interview_ingest_concurrency import PG
from .test_interview_ingest_turns import ev, rec, refuse, started

NUL = "\x00"


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def turn_count(db, session_id):
    db.rollback()
    return db.scalar(select(func.count()).select_from(InterviewTurn).where(InterviewTurn.session_id == session_id))


@PG
def test_pg_text_cannot_hold_a_nul_character(db, world, clock):
    sid = new_session(db, world, clock)
    with pytest.raises(DBAPIError):
        db.execute(insert(InterviewTurn.__table__).values(session_id=sid, seq=1, role="candidate", kind="answer", text=f"답변{NUL}", method="rules"))
        db.flush()
    db.rollback()
    assert turn_count(db, sid) == 0


@PG
def test_pg_jsonb_cannot_hold_a_nul_character(db, world, clock):
    sid = new_session(db, world, clock)
    with pytest.raises(DBAPIError):
        db.execute(update(InterviewSession.__table__).where(InterviewSession.id == sid).values(plan={"items": [{"question": f"질문{NUL}"}]}))
        db.flush()
    db.rollback()
    assert db.get(InterviewSession, sid).plan["items"]  # the plan that was there is untouched


@PG
@pytest.mark.parametrize("text", [NUL, f"{NUL}답변", f"답변{NUL}", f"Java를 {NUL}써 봤습니다."])
def test_pg_a_turn_with_nul_is_refused_with_422_and_no_row(db, world, clock, text):
    sid = new_session(db, world, clock)
    plan = started(db, sid, clock)
    assert turn_count(db, sid) == 1
    refuse(db, sid, ev(plan, 2, "candidate", "answer", text=text), clock, 422, "INTERVIEW_BAD_TURN", field="text")
    assert turn_count(db, sid) == 1
    assert rec(db, sid, ev(plan, 2, "candidate", "answer", text="Java로 API를 만들었습니다."), clock).outcome == "stored"  # the sequence is not blocked


@PG
def test_pg_a_cv_with_nul_is_refused_before_the_model_and_nothing_is_stored(db, world, clock, monkeypatch):
    # PostgreSQL cannot hold a NUL in `cv_documents.masked_text` (the INSERT of the fixture itself fails), so the stored CV stays clean and the one
    # place the service reads the CV text from is patched: this shows that the refusal completes on PostgreSQL, before the model, with no database
    # error. The SQLite tests of the same guard (test_interview_nul.py, test_interview_api_create.py) use the same patch: a really stored NUL fails
    # on PostgreSQL in the INSERT of the fixture, as the first PostgreSQL run of Tier B showed, so no test stores one any more.
    monkeypatch.setattr(svc, "_read_stored_cv", lambda _db, _cv_document_id: SAMPLE_CV.replace("Spring Boot", f"Spring{NUL}Boot", 1))
    llm = PlanLLM(db)
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    with pytest.raises(AppError) as error:
        svc.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version="2026-11-16", clock=clock)
    assert (error.value.status_code, error.value.code) == (422, "INTERVIEW_NOT_AVAILABLE")
    db.rollback()
    session = db.query(InterviewSession).filter_by(seeker_id=world.user.id).one()
    assert (session.status, session.end_reason, session.plan) == ("aborted", "plan_unavailable", None)
    assert llm.calls == []
    assert db.scalar(select(func.count()).select_from(InterviewTurn)) == 0  # and nothing else of the interview was written


@PG
def test_pg_questions_with_nul_from_the_model_are_refused_and_no_plan_is_stored(db, world, clock, monkeypatch):
    llm = PlanLLM(db, question=lambda _cid, name: f"{name} 경험을 말씀{NUL}해 주세요.")
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    with pytest.raises(AppError) as error:
        svc.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version="2026-11-16", clock=clock)
    assert (error.value.status_code, error.value.code) == (422, "INTERVIEW_NOT_AVAILABLE")
    db.rollback()
    session = db.query(InterviewSession).filter_by(seeker_id=world.user.id).one()
    assert (session.status, session.plan, session.plan_sha256) == ("aborted", None, None)


@PG
def test_pg_a_model_feedback_with_nul_is_dropped_before_the_database_and_nothing_is_raised(db, world, clock, monkeypatch):
    sid, uid = askable_session(db, world, clock), world.user.id
    llm = SpyLLM(reply={"strengths": [], "gaps": [], "improvements": ["답변은 상황과 역할," + NUL + " 해결 과정과 결과의 순서로 구성해 보세요."], "practice_questions": []})
    install(monkeypatch, llm)
    result = fb.ensure(db, db.get(User, uid), sid, clock=clock)  # no DBAPIError: the report never reached the UPDATE
    assert (result.final, result.reason, result.method) == (False, fb.REASON_MODEL_FAILED, "rules")
    stored = row(db, sid)
    assert (stored.feedback, stored.feedback_method, stored.feedback_lease_token, stored.feedback_attempts) == (None, None, None, 1)
    assert len(llm.calls) == 1
