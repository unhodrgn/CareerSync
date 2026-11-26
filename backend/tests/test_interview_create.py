"""Creating a practice interview (M4 S2): the order of the checks, no side effect when one fails, nothing read before T1 commits,
the model called outside every transaction, the planning lease and its fencing, and the quota (never refunded).

The planning model is a fake (`PlanLLM`); no network, no real model."""
import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from ai.interview import PlanItem
from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewQuota, InterviewSession, InterviewTurn, User
from app.models.interview import QuotaKind
from app.services import ai_runtime, interview_plan_service as plans, interview_quota_service as quota, interview_service as svc
from app.services.interview_time import as_utc

from .interview_fixtures import KEPT_LINES, REMOVED_LINES, SAMPLE_CV, Clock, PlanLLM, build_world

VERSION = "2026-11-26"


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


def sample_item() -> PlanItem:
    return PlanItem("c1", "technical", "q", "r", ())


def use_model(monkeypatch, llm):
    monkeypatch.setattr(ai_runtime, "llm", lambda: llm)
    return llm


def create(db, world, clock, **overrides):
    args = {"consent_transcript": True, "consent_version": VERSION, "clock": clock}
    args.update(overrides)
    return svc.create_session(db, world.user, world.job_id, **args)


def refused(db, world, clock, status, code, **overrides):
    with pytest.raises(AppError) as error:
        create(db, world, clock, **overrides)
    assert (error.value.status_code, error.value.code) == (status, code), error.value.message
    return error.value


def sessions(db):
    db.expire_all()
    return list(db.scalars(select(InterviewSession).order_by(InterviewSession.id)))


def counts(db):
    return tuple(db.scalar(select(func.count()).select_from(m)) for m in (InterviewSession, InterviewTurn, InterviewQuota))


def used(db, world, kind, clock):
    return quota.used(db, world.user.id, kind, now=clock())


@contextmanager
def capture(db):
    """Every statement and every commit of the database connection, in order."""
    log: list[tuple[str, str]] = []
    engine = db.get_bind()

    def before(_conn, _cursor, statement, _params, _context, _many):
        log.append(("sql", " ".join(statement.split())))

    def commit(_conn):
        log.append(("commit", ""))

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "commit", commit)
    try:
        yield log
    finally:
        event.remove(engine, "before_cursor_execute", before)
        event.remove(engine, "commit", commit)


def touching(log, *tables):
    return [s for kind, s in log if kind == "sql" and any(t in s for t in tables)]


# ── A session is created ──


def test_a_rules_session_is_created_and_stored_canonically(db, world, clock):
    result = create(db, world, clock)
    view = result.view
    assert result.limited is False
    assert (view.status, view.plan_method, view.joinable, view.accepting_turns, view.end_grace_open) == ("created", "rules", True, True, False)
    assert view.active_until == clock() + timedelta(seconds=300) and view.expires_at == clock() + timedelta(days=30)
    assert view.max_seconds == 600 and view.feedback_status == "none" and view.turns == () and view.ended_at is None
    assert [(t.topic_id, t.criterion_name, t.importance, t.status) for t in view.topics] == [
        ("c1", "Java", "core", "not_asked"),
        ("c2", "Spring Boot", "core", "not_asked"),
        ("c3", "협업", "important", "not_asked"),
        ("behavioral", None, None, "not_asked"),
    ]
    (row,) = sessions(db)
    assert (row.status, row.plan_method, row.consent_version) == ("created", "rules", VERSION) and row.consent_at is not None
    assert row.plan_sha256 == plans.plan_digest(row.plan) and row.coverage is None and row.feedback is None
    assert row.limits["max_seconds"] == 600 and row.prompt_version == "v1"
    assert (used(db, world, QuotaKind.SESSION, clock), used(db, world, QuotaKind.PLAN_MODEL, clock)) == (1, 0)  # rules mode asks no model


def test_a_model_session_names_the_model_and_takes_both_reservations(db, world, clock, monkeypatch):
    llm = use_model(monkeypatch, PlanLLM(db))
    result = create(db, world, clock)
    assert (result.limited, result.view.plan_method) == (False, "llm:fake-llm")
    assert len(llm.calls) == 1
    assert (used(db, world, QuotaKind.SESSION, clock), used(db, world, QuotaKind.PLAN_MODEL, clock)) == (1, 1)


def test_a_failing_model_gives_the_template_and_the_attempt_is_spent(db, world, clock, monkeypatch):
    llm = use_model(monkeypatch, PlanLLM(db, fail=True))
    result = create(db, world, clock)
    assert (result.limited, result.view.plan_method, result.view.status) == (False, "rules", "created")  # tried, failed, not "limited"
    assert len(llm.calls) == 1 and used(db, world, QuotaKind.PLAN_MODEL, clock) == 1


def test_the_model_is_not_asked_once_the_planning_quota_is_used_up_and_limited_says_so(db, world, clock, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_PLAN_MODEL_CALLS", 1)
    llm = use_model(monkeypatch, PlanLLM(db))
    first = create(db, world, clock)
    assert first.limited is False and first.view.plan_method == "llm:fake-llm"
    svc.end(db, world.user, first.view.id, clock=clock)
    second = create(db, world, clock)
    assert (second.limited, second.view.plan_method) == (True, "rules")
    assert len(llm.calls) == 1  # no second attempt
    assert (used(db, world, QuotaKind.SESSION, clock), used(db, world, QuotaKind.PLAN_MODEL, clock)) == (2, 1)


def test_rules_mode_is_never_limited(db, world, clock, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_PLAN_MODEL_CALLS", 0)
    assert create(db, world, clock).limited is False  # no model is configured, so no model attempt was stopped


# ── Order of the checks, and no side effect when one fails ──


def test_a_company_user_is_stopped_before_anything_is_read(db, clock):
    company = build_world(db, email="hr@interview.test", role="company")
    with capture(db) as log:
        error = refused(db, company, clock, 403, "SEEKER_ONLY")
    assert log == [] and counts(db) == (0, 0, 0) and error.status_code == 403


@pytest.mark.parametrize(
    "kwargs, status, code",
    [
        ({"ai_consent": False}, 409, "AI_CONSENT_REQUIRED"),
        ({"confirmed": False}, 409, "CV_NOT_CONFIRMED"),
        ({"status": "draft"}, 404, "JOB_NOT_FOUND"),
        ({"status": "closed"}, 404, "JOB_NOT_FOUND"),
        ({"deadline": date.today() - timedelta(days=1)}, 404, "JOB_NOT_FOUND"),
    ],
)
def test_the_gates_come_before_the_transcript_consent(db, clock, kwargs, status, code):
    other = build_world(db, email="gate@interview.test", **kwargs)
    refused(db, other, clock, status, code, consent_transcript=None, consent_version="old")  # the earlier gate answers first
    assert counts(db) == (0, 0, 0)


@pytest.mark.parametrize(
    "overrides, code",
    [
        ({"consent_transcript": None}, "INTERVIEW_CONSENT_REQUIRED"),
        ({"consent_transcript": False}, "INTERVIEW_CONSENT_REQUIRED"),
        ({"consent_transcript": "true"}, "INTERVIEW_CONSENT_REQUIRED"),
        ({"consent_version": "2026-11-15"}, "INTERVIEW_CONSENT_OUTDATED"),
        ({"consent_version": None}, "INTERVIEW_CONSENT_OUTDATED"),
    ],
)
def test_without_the_transcript_consent_nothing_is_processed_and_nothing_is_written(db, world, clock, monkeypatch, overrides, code):
    llm = use_model(monkeypatch, PlanLLM(db))
    with capture(db) as log:
        error = refused(db, world, clock, 409, code, **overrides)
    assert error.extra == {"current_version": VERSION}
    assert counts(db) == (0, 0, 0) and llm.calls == []
    # No CV text, no criteria and no interview table was touched; only the gate reads of the profile and the job
    assert touching(log, "cv_documents", "job_criteria", "interview_", "career_contents") == []
    assert [kind for kind, _ in log].count("commit") == 0


def test_a_job_without_usable_criteria_is_refused_before_anything_is_reserved(db, clock):
    empty = build_world(db, email="empty@interview.test", criteria=())
    refused(db, empty, clock, 422, "INTERVIEW_NOT_AVAILABLE")
    assert counts(db) == (0, 0, 0)


# ── Nothing of the CV is read before T1 commits ──


def test_the_cv_text_is_read_once_and_only_after_the_reservation_is_committed(db, world, clock):
    with capture(db) as log:
        create(db, world, clock)
    events = [(i, kind, s) for i, (kind, s) in enumerate(log)]
    insert = next(i for i, kind, s in events if kind == "sql" and s.startswith("INSERT INTO interview_sessions"))
    commit = next(i for i, kind, _ in events if kind == "commit" and i > insert)
    reads = [i for i, kind, s in events if kind == "sql" and "FROM cv_documents" in s]
    assert len(reads) == 1 and insert < commit < reads[0]
    assert not touching(log[:commit], "cv_documents")
    quota_claims = [i for i, kind, s in events if kind == "sql" and "interview_quota" in s and i < commit]
    assert quota_claims  # the claims are in T1, before the commit and before the CV read


# ── The model is called outside every transaction, and the claims are already committed ──


def test_the_model_is_called_with_no_transaction_open_and_the_claims_already_committed(db, world, clock, monkeypatch):
    seen = {}

    def inside_the_call(llm):
        seen["tx"] = db.in_transaction()
        db.rollback()  # whatever happens to the session now cannot take a committed reservation back
        seen["used"] = (used(db, world, QuotaKind.SESSION, clock), used(db, world, QuotaKind.PLAN_MODEL, clock))
        db.rollback()

    use_model(monkeypatch, PlanLLM(db, on_call=inside_the_call))
    create(db, world, clock)
    assert seen == {"tx": False, "used": (1, 1)}


# ── Plan quota and the daily limit ──


def test_the_daily_limit_stops_the_fourth_session_and_the_refusal_takes_nothing(db, world, clock):
    for _ in range(3):
        view = create(db, world, clock).view
        svc.end(db, world.user, view.id, clock=clock)
        clock.advance(1)
    error = refused(db, world, clock, 429, "INTERVIEW_DAILY_LIMIT")
    assert error.extra == {"quota": "sessions", "limit": 3, "resets_at": "2026-11-17T00:00:00+09:00"}
    assert counts(db)[0] == 3 and used(db, world, QuotaKind.SESSION, clock) == 3  # the refused T1 was rolled back whole


def test_deleting_a_session_does_not_give_the_day_back(db, world, clock):
    for _ in range(3):
        view = create(db, world, clock).view
        svc.delete(db, world.user, view.id, clock=clock)
        clock.advance(1)
    assert counts(db)[0] == 0
    refused(db, world, clock, 429, "INTERVIEW_DAILY_LIMIT")


def test_a_new_kst_day_starts_a_new_quota(db, world, clock):
    for _ in range(3):
        svc.end(db, world.user, create(db, world, clock).view.id, clock=clock)
    refused(db, world, clock, 429, "INTERVIEW_DAILY_LIMIT")
    clock.now = datetime(2026, 11, 16, 15, 0, 1, tzinfo=UTC)  # just after midnight KST
    assert create(db, world, clock).view.status == "created"


def test_a_second_session_is_refused_while_one_is_active_and_nothing_is_taken(db, world, clock):
    first = create(db, world, clock).view
    error = refused(db, world, clock, 409, "INTERVIEW_SESSION_ACTIVE")
    assert error.extra == {"session_id": first.id, "status": "created"}
    assert counts(db)[0] == 1 and used(db, world, QuotaKind.SESSION, clock) == 1


def test_a_session_nobody_joined_stops_blocking_and_its_reservation_stays_spent(db, world, clock):
    first = create(db, world, clock).view
    clock.advance(301)  # past the join deadline
    second = create(db, world, clock).view
    assert second.id != first.id and second.status == "created"
    old = next(r for r in sessions(db) if r.id == first.id)
    assert (old.status, old.end_reason) == ("aborted", "not_joined") and old.active_until is None
    assert used(db, world, QuotaKind.SESSION, clock) == 2  # no refund


# ── The planning lease and the fencing of a stale worker ──


def test_a_planning_that_outlives_its_lease_is_not_stored_and_nothing_is_refunded(db, world, clock, monkeypatch):
    use_model(monkeypatch, PlanLLM(db, on_call=lambda llm: clock.advance(121)))
    error = refused(db, world, clock, 409, "INTERVIEW_PLANNING_EXPIRED")
    (row,) = sessions(db)
    assert (row.status, row.plan, row.plan_sha256) == ("planning", None, None)  # not brought back to life
    assert error.extra["session_id"] == row.id
    assert (used(db, world, QuotaKind.SESSION, clock), used(db, world, QuotaKind.PLAN_MODEL, clock)) == (1, 1)
    assert svc.detail(db, world.user, row.id, clock=clock).status == "aborted"  # the reader sees the lost reservation as aborted
    # the next create settles it, keeps its reservations spent, and plans again (this time the model is not slow)
    use_model(monkeypatch, PlanLLM(db))
    second = create(db, world, clock).view
    assert second.status == "created"
    lost = next(r for r in sessions(db) if r.id == row.id)
    assert (lost.status, lost.end_reason, lost.plan) == ("aborted", "planning_lost", None)
    assert used(db, world, QuotaKind.SESSION, clock) == 2


def test_the_lease_ends_exactly_after_the_configured_seconds(db, world, clock, monkeypatch):
    use_model(monkeypatch, PlanLLM(db, on_call=lambda llm: clock.advance(120)))  # on the deadline the lease still holds
    assert create(db, world, clock).view.status == "created"


def test_a_worker_whose_reservation_was_superseded_does_not_overwrite_the_newer_session(db, world, clock, monkeypatch):
    state = {"nested": False, "second": None}

    def act_as_the_next_request(llm):
        if state["nested"]:
            return
        state["nested"] = True
        clock.advance(130)  # the first lease ran out, so the next request may settle it and start its own session
        state["second"] = create(db, world, clock).view

    use_model(monkeypatch, PlanLLM(db, on_call=act_as_the_next_request))
    refused(db, world, clock, 409, "INTERVIEW_PLANNING_EXPIRED")
    first, second = sessions(db)
    assert (first.status, first.end_reason, first.plan) == ("aborted", "planning_lost", None)
    assert second.id == state["second"].id and second.status == "created" and second.plan is not None
    assert used(db, world, QuotaKind.SESSION, clock) == 2


def test_a_session_deleted_while_it_is_planned_is_not_brought_back(db, world, clock, monkeypatch):
    def delete_it(llm):
        svc.delete(db, world.user, db.scalar(select(InterviewSession.id)), clock=clock)

    use_model(monkeypatch, PlanLLM(db, on_call=delete_it))
    refused(db, world, clock, 404, "INTERVIEW_NOT_FOUND")
    assert counts(db)[0] == 0 and used(db, world, QuotaKind.SESSION, clock) == 1


def test_a_reservation_that_expired_is_not_brought_back_either(db, world, clock, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_PLAN_LEASE_SECONDS", 40 * 86400)  # the lease is not what stops it here
    use_model(monkeypatch, PlanLLM(db, on_call=lambda llm: clock.advance(31 * 86400)))
    refused(db, world, clock, 409, "INTERVIEW_PLANNING_EXPIRED")
    (row,) = sessions(db)
    assert row.status == "planning" and row.plan is None


def test_another_seekers_reservation_is_never_touched(db, world, clock, monkeypatch):
    other = build_world(db, email="other@interview.test")
    svc.create_session(db, other.user, other.job_id, consent_transcript=True, consent_version=VERSION, clock=clock)
    use_model(monkeypatch, PlanLLM(db, on_call=lambda llm: clock.advance(121)))
    refused(db, world, clock, 409, "INTERVIEW_PLANNING_EXPIRED")
    mine, theirs = (next(r for r in sessions(db) if r.seeker_id == w.user.id) for w in (world, other))
    assert (mine.status, theirs.status) == ("planning", "created")


# ── A plan that cannot be stored ──


def test_a_plan_that_repeats_the_cv_is_refused_and_the_reservation_stays_spent(db, world, clock, monkeypatch):
    real_prefilter = plans.prefilter_bank
    monkeypatch.setattr(plans, "prefilter_bank", lambda bank, clean: [replace(q, cv_quote=None) for q in bank])  # the prefilter off
    copy = lambda cid, name: f"{KEPT_LINES[0]} 에서 {name}를 맡으셨나요?" if cid == 1 else f"{name} 관련 경험을 말씀해 주세요."
    use_model(monkeypatch, PlanLLM(db, question=copy))
    refused(db, world, clock, 422, "INTERVIEW_NOT_AVAILABLE")
    (row,) = sessions(db)
    assert (row.status, row.end_reason, row.plan, row.plan_sha256) == ("aborted", "plan_unavailable", None, None)
    assert (used(db, world, QuotaKind.SESSION, clock), used(db, world, QuotaKind.PLAN_MODEL, clock)) == (1, 1)
    monkeypatch.setattr(plans, "prefilter_bank", real_prefilter)  # the seeker is not blocked: the next session can be planned
    use_model(monkeypatch, PlanLLM(db))
    assert create(db, world, clock).view.status == "created"


def test_an_unexpected_error_closes_the_reservation_and_is_not_hidden(db, world, clock, monkeypatch):
    def boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(svc, "build_canonical_plan", boom)
    with pytest.raises(RuntimeError):
        create(db, world, clock)
    (row,) = sessions(db)
    assert (row.status, row.end_reason, row.plan) == ("aborted", "internal_error", None)
    assert used(db, world, QuotaKind.SESSION, clock) == 1


# ── What reaches the model and what is stored ──


def test_the_planning_request_carries_no_stored_only_cv_text(db, world, clock, monkeypatch):
    llm = use_model(monkeypatch, PlanLLM(db))
    create(db, world, clock)
    (system, user), = llm.calls
    for line in REMOVED_LINES:
        assert line not in user and line not in system
    for word in ("홍길동", "서울특별시", "병장", "성별", "취미"):
        assert word not in user
    assert any(line in user for line in KEPT_LINES[:3])


def test_nothing_of_the_cv_is_stored_in_the_interview_tables(db, world, clock, monkeypatch):
    use_model(monkeypatch, PlanLLM(db, cv_quote=KEPT_LINES[0], question=lambda cid, name: f"{KEPT_LINES[1]} 를 {name}에 어떻게 적용했나요?" if cid == 2 else f"{name} 관련 경험을 말씀해 주세요."))
    create(db, world, clock)
    db.expire_all()
    dump = json.dumps(
        [[{c.name: str(getattr(r, c.name)) for c in r.__table__.columns} for r in db.scalars(select(m))] for m in (InterviewSession, InterviewTurn, InterviewQuota)],
        ensure_ascii=False,
    )
    for line in (*REMOVED_LINES, *KEPT_LINES[:3]):
        assert line not in dump
    assert SAMPLE_CV not in dump and "weight" not in dump
    (row,) = sessions(db)
    assert all(item["cv_quote"] is None for item in row.plan["items"])


def test_importance_labels_are_stored_and_weights_are_not(db, world, clock):
    create(db, world, clock)
    (row,) = sessions(db)
    assert [i["importance"] for i in row.plan["items"]] == ["core", "core", "important", None]
    assert "weight" not in json.dumps(row.plan)
    assert {key for item in row.plan["items"] for key in item} == set(PlanItem.to_dict(sample_item()))  # the engine's own fields, no weight


def test_the_user_object_is_not_changed_by_a_session(db, world, clock):
    before = (as_utc(world.user.consent_ai_at), world.user.consent_version)
    create(db, world, clock)
    db.expire_all()
    user = db.get(User, world.user.id)
    assert (as_utc(user.consent_ai_at), user.consent_version) == before  # the transcript consent is the session's own


def test_an_integrity_error_that_is_not_the_active_session_index_is_not_hidden(db, world, clock, monkeypatch):
    """Only the one-active-session index means "you already have a session". Any other integrity error is a real error."""
    from sqlalchemy.exc import IntegrityError

    def flush(*_args, **_kwargs):
        raise IntegrityError("INSERT", {}, Exception("foreign key"))

    monkeypatch.setattr(db, "flush", flush)
    with pytest.raises(IntegrityError):
        create(db, world, clock)
    monkeypatch.undo()
    assert counts(db) == (0, 0, 0)


def test_a_reservation_that_another_writer_already_moved_on_is_not_overwritten(db, world, clock, monkeypatch):
    """The lease alone would not stop this: the row is no longer `planning`, but it still has a deadline in the future."""
    from sqlalchemy import update

    def moved_on(llm):
        db.execute(
            update(InterviewSession.__table__)
            .where(InterviewSession.__table__.c.status == "planning")
            .values(status="completed", end_reason="engine", active_until=clock() + timedelta(days=1))
        )
        db.commit()

    use_model(monkeypatch, PlanLLM(db, on_call=moved_on))
    refused(db, world, clock, 409, "INTERVIEW_PLANNING_EXPIRED")
    (row,) = sessions(db)
    assert (row.status, row.end_reason, row.plan, row.plan_sha256) == ("completed", "engine", None, None)  # not turned into `created`
