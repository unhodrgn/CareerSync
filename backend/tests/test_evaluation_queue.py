"""Queue/retry rules for evaluations (doc issues 2, 25, §6.1): one scoring run per queue, no double scoring."""
import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.models import Application, Evaluation, User
from app.models.application import EvaluationStatus
from app.services import application_service, evaluation_service

from .test_applications_api import job, ready_seeker  # noqa: F401  (job is a fixture)

REAL_RUN = evaluation_service.run_in_background  # the `queued` fixture replaces the module attribute
SESSIONS = None  # session factory for the PostgreSQL thread tests


@pytest.fixture
def queued(monkeypatch):
    """Record queued background runs instead of running them, so evaluations stay pending as if still scoring."""
    calls = []
    monkeypatch.setattr(evaluation_service, "run_in_background", lambda *args: calls.append(args))
    return calls


def _apply(client, db, job_id):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")
    r = client.post(f"/api/jobs/{job_id}/applications", headers=kim)
    assert r.status_code == 201, r.json()
    return db.get(Application, r.json()["id"])


def _evaluation(db, app) -> Evaluation:
    return db.scalars(
        select(Evaluation).where(Evaluation.job_id == app.job_id, Evaluation.cv_profile_id == app.cv_profile_id)
    ).one()


def _recruiter(session) -> User:
    return session.scalars(select(User).where(User.email == "hr@acme.test")).one()


def test_two_concurrent_retries_queue_one_run(client, db, world, job, queued):
    app = _apply(client, db, job)
    ev = _evaluation(db, app)
    ev.status = EvaluationStatus.FAILED
    db.commit()

    sessions = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    first, second = sessions(), sessions()
    try:
        # The second request has read the evaluation as failed before the first one writes
        assert _evaluation(second, app).status == EvaluationStatus.FAILED
        outcomes = []
        for session in (first, second):
            try:
                application_service.retry(session, _recruiter(session), app.id)
                outcomes.append("queued")
            except AppError as e:
                outcomes.append(e.code)
    finally:
        first.close()
        second.close()
    assert outcomes == ["queued", "EVALUATION_IN_PROGRESS"]


def test_retry_while_running_is_rejected(client, db, world, job, queued):
    app = _apply(client, db, job)
    assert len(queued) == 1
    r = client.post(f"/api/applications/{app.id}/evaluation/retry", headers=world["recruiter"])
    assert (r.status_code, r.json()["code"]) == (409, "EVALUATION_IN_PROGRESS")
    assert len(queued) == 1


def test_apply_does_not_requeue_a_running_evaluation(client, db, world, job, queued):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")
    cv_id = client.get("/api/cv/me", headers=kim).json()["id"]
    # Queued moments ago by another path (e.g. recommendation) and still running
    db.add(Evaluation(job_id=job, cv_profile_id=cv_id, status=EvaluationStatus.PENDING, queued_at=datetime.now(UTC), attempts=1))
    db.commit()
    assert client.post(f"/api/jobs/{job}/applications", headers=kim).status_code == 201
    assert queued == []


def test_stale_pending_can_be_retried(client, db, world, job, queued):
    app = _apply(client, db, job)
    ev = _evaluation(db, app)
    old = datetime.now(UTC) - timedelta(minutes=settings.EVALUATION_STALE_MINUTES + 1)  # server died mid-run
    ev.queued_at, ev.attempts = old, 2
    db.commit()
    r = client.post(f"/api/applications/{app.id}/evaluation/retry", headers=world["recruiter"])
    assert r.status_code == 200, r.json()
    assert len(queued) == 2
    db.refresh(ev)
    assert ev.status == EvaluationStatus.PENDING and ev.attempts == 1
    assert queued[-1][2] > old  # new token


def test_apply_and_retry_set_queue_columns(client, db, world, job, queued):
    app = _apply(client, db, job)
    ev = _evaluation(db, app)
    assert ev.queued_at is not None and ev.attempts == 1
    factory, evaluation_id, token = queued[0]
    assert evaluation_id == ev.id and token is not None


def test_an_older_run_never_overwrites_a_newer_one(client, db, world, job, queued, monkeypatch):
    app = _apply(client, db, job)
    ev = _evaluation(db, app)
    factory, evaluation_id, _ = queued[0]
    # Run 1 was queued long ago and is still running (slow LLM); the evaluation is re-queued as run 2
    old_token = datetime.now(UTC) - timedelta(minutes=settings.EVALUATION_STALE_MINUTES + 1)
    ev.queued_at = old_token
    db.commit()
    assert client.post(f"/api/applications/{app.id}/evaluation/retry", headers=world["recruiter"]).status_code == 200
    new_token = queued[-1][2]

    REAL_RUN(factory, evaluation_id, new_token)  # run 2 finishes first
    db.expire_all()
    done = _evaluation(db, app)
    assert done.status == EvaluationStatus.DONE
    scores = sorted((s.job_criteria_id, s.score) for s in done.scores)
    finished_at = done.finished_at

    def broken(*a, **k):
        raise RuntimeError("late failure")

    with monkeypatch.context() as m:
        m.setattr("app.services.evaluation_service.score_candidate", broken)
        REAL_RUN(factory, evaluation_id, old_token)  # run 1 ends late with a failure: discarded
    REAL_RUN(factory, evaluation_id, old_token)  # run 1 ends late with results: discarded too
    db.expire_all()
    after = _evaluation(db, app)
    assert after.status == EvaluationStatus.DONE and after.error == ""
    assert after.finished_at == finished_at  # run 1 wrote nothing
    assert sorted((s.job_criteria_id, s.score) for s in after.scores) == scores


def test_ensure_returns_the_row_a_concurrent_request_inserted(client, db, world, job, queued, monkeypatch):
    app = _apply(client, db, job)
    existing = _evaluation(db, app)
    real_find = evaluation_service._find
    calls = []

    def find_missing_once(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_find(*args)  # the other request inserted after our read

    monkeypatch.setattr(evaluation_service, "_find", find_missing_once)
    ev = evaluation_service.ensure(db, app.job_id, app.cv_profile_id)
    assert ev.id == existing.id and len(calls) == 2
    db.commit()  # the session is still usable after the failed insert
    assert db.scalars(select(Evaluation)).all() == [existing]


def test_concurrent_apply_by_the_same_seeker_is_409(client, db, world, job, queued, monkeypatch):
    kim = ready_seeker(client, db, "kim@seeker.test", "김지원")
    assert client.post(f"/api/jobs/{job}/applications", headers=kim).status_code == 201
    # The second request checked before the first one committed
    monkeypatch.setattr(application_service, "_already_applied", lambda *args: False)
    r = client.post(f"/api/jobs/{job}/applications", headers=kim)
    assert (r.status_code, r.json()["code"]) == (409, "ALREADY_APPLIED")
    assert len(db.scalars(select(Application)).all()) == 1 and len(queued) == 1


# ── Real concurrency: PostgreSQL only (TEST_DATABASE_URL=postgresql+psycopg://…/careersync_test) ──

on_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL"
)


def _in_parallel(n: int, work) -> list[str]:
    """Run work(session) in n threads with their own sessions, released together; returns outcomes."""
    barrier = threading.Barrier(n)
    outcomes: list[str] = []
    lock = threading.Lock()

    def run():
        session = SESSIONS()
        try:
            barrier.wait()
            result = work(session)
        except AppError as e:
            result = e.code
        finally:
            session.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return sorted(outcomes)


@pytest.fixture
def sessions(db):
    global SESSIONS
    SESSIONS = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    yield
    SESSIONS = None


@on_postgres
def test_pg_parallel_retries_queue_once(client, db, world, job, queued, sessions):
    app = _apply(client, db, job)
    ev = _evaluation(db, app)
    ev.status = EvaluationStatus.FAILED
    db.commit()

    def retry(session):
        application_service.retry(session, _recruiter(session), app.id)
        return "queued"

    n = 8
    assert _in_parallel(n, retry) == ["EVALUATION_IN_PROGRESS"] * (n - 1) + ["queued"]


@pytest.mark.parametrize("rounds", range(3))
@on_postgres
def test_pg_parallel_claims_one_token(client, db, world, job, queued, sessions, rounds):
    app = _apply(client, db, job)
    ev = _evaluation(db, app)
    ev.status = EvaluationStatus.FAILED
    db.commit()

    def claim(session):
        token = evaluation_service.claim(session, session.get(Evaluation, ev.id), reset_attempts=False)
        session.commit()
        return "token" if token else "none"

    n = 8
    assert _in_parallel(n, claim) == ["none"] * (n - 1) + ["token"]
    db.expire_all()
    assert _evaluation(db, app).attempts == 2  # 1 from apply + exactly one parallel claim


@on_postgres
def test_pg_parallel_apply_same_seeker(client, db, world, job, queued, sessions):
    ready_seeker(client, db, "kim@seeker.test", "김지원")

    def apply(session):
        user = session.scalars(select(User).where(User.email == "kim@seeker.test")).one()
        application_service.apply(session, user, job)
        return "applied"

    n = 6
    assert _in_parallel(n, apply) == ["ALREADY_APPLIED"] * (n - 1) + ["applied"]
    assert len(db.scalars(select(Application)).all()) == 1
    assert len(db.scalars(select(Evaluation)).all()) == 1
