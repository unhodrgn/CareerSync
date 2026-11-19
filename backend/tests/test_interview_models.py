"""The practice-interview tables (M4 S1): the approved columns and nothing else, every constraint, the active-session index,
SQL NULL for a missing JSON value, and the cascades (checked on an SQLite database that enforces foreign keys)."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import LargeBinary, delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import Base
from app.models import InterviewQuota, InterviewSession, InterviewTurn, User
from app.models.interview import ACTIVE_SQL, InterviewStatus, QuotaKind

from .interview_fixtures import build_ids, fk_db, make_session  # noqa: F401  (fk_db is a fixture)

TABLES = ("interview_sessions", "interview_turns", "interview_quota")

# column -> (type, nullable): the approved schema
SESSIONS = {
    "id": ("Integer", False),
    "seeker_id": ("Integer", False),
    "job_id": ("Integer", False),
    "cv_profile_id": ("Integer", False),
    "status": ("String(10)", False),
    "end_reason": ("String(40)", True),
    "plan": ("JSON", True),
    "plan_method": ("String(80)", True),
    "plan_sha256": ("String(64)", True),
    "prompt_version": ("String(20)", False),
    "limits": ("JSON", False),
    "coverage": ("JSON", True),
    "consent_version": ("String(20)", False),
    "consent_at": ("DateTime", False),
    "created_at": ("DateTime", False),
    "started_at": ("DateTime", True),
    "ended_at": ("DateTime", True),
    "active_until": ("DateTime", True),
    "expires_at": ("DateTime", False),
    "feedback": ("JSON", True),
    "feedback_method": ("String(80)", True),
    "feedback_prompt_version": ("String(20)", True),
    "feedback_at": ("DateTime", True),
    "feedback_attempts": ("SmallInteger", False),
    "feedback_lease_until": ("DateTime", True),
    "feedback_lease_token": ("String(32)", True),
}
TURNS = {
    "id": ("Integer", False),
    "session_id": ("Integer", False),
    "seq": ("Integer", False),
    "role": ("String(10)", False),
    "kind": ("String(20)", False),
    "item_index": ("SmallInteger", True),
    "text": ("Text", False),
    "method": ("String(80)", False),
    "analysis": ("JSON", True),
    "masked_kinds": ("JSON", True),
    "created_at": ("DateTime", False),
}
QUOTA = {
    "seeker_id": ("Integer", False),
    "kst_day": ("Date", False),
    "kind": ("String(14)", False),
    "used": ("SmallInteger", False),
    "quota_limit": ("SmallInteger", False),
}


def _type(column) -> str:
    name = type(column.type).__name__
    length = getattr(column.type, "length", None)
    return f"{name}({length})" if length else name


def _schema(table) -> dict:
    return {c.name: (_type(c), c.nullable) for c in table.columns}


# ── Table definitions ──


@pytest.mark.parametrize("name, expected", [("interview_sessions", SESSIONS), ("interview_turns", TURNS), ("interview_quota", QUOTA)])
def test_the_columns_are_the_approved_ones(name, expected):
    assert _schema(Base.metadata.tables[name]) == expected


def test_no_audio_video_cv_or_weight_columns_and_no_room_or_avatar_yet():
    forbidden = ("room", "avatar", "audio", "video", "cv_text", "masked_cv", "excerpt", "cv_quote", "weight", "score", "rank", "blob")
    for name in TABLES:
        table = Base.metadata.tables[name]
        for column in table.columns:
            assert not any(word in column.name for word in forbidden), f"{name}.{column.name}"
            assert not isinstance(column.type, LargeBinary), f"{name}.{column.name} is binary"
    # The only link to the CV is the profile id; the document and its text are not reachable from a session
    assert {fk.column.table.name for fk in Base.metadata.tables["interview_sessions"].foreign_keys} == {"users", "job_postings", "cv_profiles"}


def test_keys_checks_and_indexes_are_the_approved_ones():
    sessions, turns, quota = (Base.metadata.tables[n] for n in TABLES)
    assert [c.name for c in quota.primary_key.columns] == ["seeker_id", "kst_day", "kind"]
    assert {c.name for c in sessions.constraints if c.__class__.__name__ == "CheckConstraint"} == {
        "ck_interview_sessions_status",
        "ck_interview_sessions_feedback_attempts",
        "ck_interview_sessions_feedback_method",
    }
    assert {c.name for c in turns.constraints if c.__class__.__name__ == "CheckConstraint"} == {
        "ck_interview_turns_seq",
        "ck_interview_turns_role",
        "ck_interview_turns_item_index",
        "ck_interview_turns_text_len",
    }
    assert {c.name for c in quota.constraints if c.__class__.__name__ == "CheckConstraint"} == {
        "ck_interview_quota_kind",
        "ck_interview_quota_limit",
        "ck_interview_quota_used",
    }
    assert {(i.name, tuple(c.name for c in i.columns), i.unique) for i in sessions.indexes} == {
        ("ix_interview_sessions_job_id", ("job_id",), False),
        ("ix_interview_sessions_cv_profile_id", ("cv_profile_id",), False),
        ("ix_interview_sessions_expires_at", ("expires_at",), False),
        ("ix_interview_sessions_seeker_created", ("seeker_id", "created_at"), False),
        ("uq_interview_sessions_active", ("seeker_id",), True),
    }
    # The quota table: one index besides its primary key, on the day, for deleting past days
    assert {(i.name, tuple(c.name for c in i.columns), i.unique) for i in quota.indexes} == {("ix_interview_quota_kst_day", ("kst_day",), False)}
    active = next(i for i in sessions.indexes if i.name == "uq_interview_sessions_active")
    assert str(active.dialect_options["postgresql"]["where"]) == ACTIVE_SQL == "status IN ('planning', 'created', 'live')"
    assert str(active.dialect_options["sqlite"]["where"]) == ACTIVE_SQL
    assert {tuple(c.name for c in u.columns) for u in turns.constraints if u.__class__.__name__ == "UniqueConstraint"} == {("session_id", "seq")}


def test_the_quota_table_has_no_foreign_key_to_a_session():
    quota = Base.metadata.tables["interview_quota"]
    assert [fk.column.table.name for fk in quota.foreign_keys] == ["users"]


def test_status_and_kind_vocabularies():
    assert InterviewStatus.ALL == ("planning", "created", "live", "completed", "aborted")
    assert InterviewStatus.ACTIVE == ("planning", "created", "live")
    assert QuotaKind.ALL == ("session", "plan_model", "feedback_model")


# ── Session constraints ──


@pytest.fixture
def ids(db):
    return build_ids(db)


def _insert(db, row):
    db.add(row)
    db.commit()
    return row


def test_a_valid_session_round_trips(db, ids):
    row = _insert(db, make_session(ids, plan={"items": []}, plan_method="rules", plan_sha256="a" * 64))
    db.expire_all()
    got = db.get(InterviewSession, row.id)
    assert got.status == "created" and got.plan == {"items": []} and got.feedback is None and got.feedback_attempts == 0
    assert got.created_at is not None and got.coverage is None and got.feedback_lease_token is None


def test_an_unknown_status_is_refused(db, ids):
    with pytest.raises(IntegrityError):
        _insert(db, make_session(ids, status="expired"))  # expiry is derived from expires_at, never stored


def test_a_session_needs_its_required_columns(db, ids):
    for missing in ("status", "prompt_version", "limits", "consent_version", "consent_at", "expires_at"):
        row = make_session(ids)
        setattr(row, missing, None)
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_feedback_attempts_cannot_be_negative(db, ids):
    with pytest.raises(IntegrityError):
        _insert(db, make_session(ids, feedback_attempts=-1))


def test_stored_feedback_always_has_a_method(db, ids):
    with pytest.raises(IntegrityError):
        _insert(db, make_session(ids, feedback={"topics": []}))
    db.rollback()
    row = _insert(db, make_session(ids, feedback={"topics": []}, feedback_method="rules"))
    assert row.id is not None


@pytest.mark.parametrize("status", ["planning", "created", "live"])
def test_a_seeker_has_at_most_one_active_session(db, ids, status):
    _insert(db, make_session(ids, status=status))
    for other in InterviewStatus.ACTIVE:
        with pytest.raises(IntegrityError):
            _insert(db, make_session(ids, status=other))
        db.rollback()


def test_finished_sessions_do_not_count_as_active(db, ids):
    for status in ("completed", "aborted", "completed", "aborted"):
        _insert(db, make_session(ids, status=status))
    _insert(db, make_session(ids, status="live"))
    assert db.scalar(select(func.count()).select_from(InterviewSession)) == 5


def test_a_new_session_is_possible_once_the_active_one_ended(db, ids):
    first = _insert(db, make_session(ids, status="created"))
    with pytest.raises(IntegrityError):
        _insert(db, make_session(ids, status="planning"))
    db.rollback()
    first.status, first.end_reason = "aborted", "not_joined"
    db.commit()
    assert _insert(db, make_session(ids, status="planning")).id is not None


def test_two_seekers_can_each_have_an_active_session(db, ids):
    other = build_ids(db, "s2@interview.test")
    _insert(db, make_session(ids, status="live"))
    assert _insert(db, make_session(other, status="live")).id is not None


def test_none_is_stored_as_sql_null_not_as_json_null(db, ids):
    """The feedback lease and the stored-feedback checks use IS NULL, so a JSON null must never be written for None."""
    row = _insert(db, make_session(ids, plan=None, coverage=None, feedback=None))
    cells = db.execute(text("SELECT plan IS NULL, coverage IS NULL, feedback IS NULL FROM interview_sessions WHERE id = :i"), {"i": row.id}).one()
    assert tuple(cells) == (1, 1, 1) or tuple(cells) == (True, True, True)


# ── Turn constraints ──


def _turn(session_id, seq=1, **overrides):
    values = {"session_id": session_id, "seq": seq, "role": "candidate", "kind": "answer", "text": "저는 Java로 API를 만들었습니다."}
    values.update(overrides)
    return InterviewTurn(**values)


@pytest.mark.parametrize(
    "overrides",
    [{"role": "interviewer"}, {"seq": 0}, {"seq": -3}, {"item_index": -1}, {"text": "x" * 4001}, {"text": None}, {"kind": None}],
)
def test_a_bad_turn_is_refused(db, ids, overrides):
    session = _insert(db, make_session(ids))
    with pytest.raises(IntegrityError):
        _insert(db, _turn(session.id, **overrides))


def test_a_valid_turn_round_trips_with_its_defaults(db, ids):
    session = _insert(db, make_session(ids))
    turn = _insert(db, _turn(session.id, text="x" * 4000, item_index=0, analysis={"answer_type": "answered"}, masked_kinds={"email": 1}))
    db.expire_all()
    got = db.get(InterviewTurn, turn.id)
    assert got.method == "rules" and got.created_at is not None and len(got.text) == 4000
    assert got.analysis == {"answer_type": "answered"} and got.masked_kinds == {"email": 1}


def test_a_sequence_number_is_unique_within_a_session_only(db, ids):
    first = _insert(db, make_session(ids, status="completed"))
    second = _insert(db, make_session(ids, status="aborted"))
    _insert(db, _turn(first.id, seq=1))
    _insert(db, _turn(second.id, seq=1))
    with pytest.raises(IntegrityError):
        _insert(db, _turn(first.id, seq=1))


def test_deleting_a_session_through_the_orm_deletes_its_turns(db, ids):
    session = _insert(db, make_session(ids))
    _insert(db, _turn(session.id, seq=1))
    _insert(db, _turn(session.id, seq=2, role="agent", kind="question"))
    assert [t.seq for t in db.get(InterviewSession, session.id).turns] == [1, 2]
    db.delete(db.get(InterviewSession, session.id))
    db.commit()
    assert db.scalar(select(func.count()).select_from(InterviewTurn)) == 0


# ── Cascades, on a database that enforces foreign keys ──


def _counts(db) -> tuple[int, int, int]:
    return tuple(db.scalar(select(func.count()).select_from(t)) for t in (InterviewSession, InterviewTurn, InterviewQuota))


def _populate(db, ids):
    session = _insert(db, make_session(ids))
    _insert(db, _turn(session.id, seq=1))
    db.execute(InterviewQuota.__table__.insert().values(seeker_id=ids.seeker_id, kst_day=datetime(2026, 11, 16).date(), kind="session", used=1, quota_limit=3))
    db.commit()
    return session


def test_cascade_deleting_a_session_removes_its_turns_and_keeps_the_quota(fk_db):
    ids = build_ids(fk_db)
    session = _populate(fk_db, ids)
    assert _counts(fk_db) == (1, 1, 1)
    fk_db.execute(delete(InterviewSession).where(InterviewSession.id == session.id))
    fk_db.commit()
    assert _counts(fk_db) == (0, 0, 1)  # the reservation of that day stays
    assert fk_db.scalar(select(InterviewQuota.used)) == 1


def test_cascade_deleting_the_seeker_removes_sessions_turns_and_quota(fk_db):
    ids = build_ids(fk_db)
    _populate(fk_db, ids)
    fk_db.execute(delete(User).where(User.id == ids.seeker_id))
    fk_db.commit()
    assert _counts(fk_db) == (0, 0, 0)


def test_cascade_deleting_the_job_or_the_cv_removes_the_sessions(fk_db):
    from app.models import CvProfile, JobPosting

    ids = build_ids(fk_db)
    _populate(fk_db, ids)
    fk_db.execute(delete(JobPosting).where(JobPosting.id == ids.job_id))
    fk_db.commit()
    assert _counts(fk_db)[:2] == (0, 0)

    other = build_ids(fk_db, "s2@interview.test")
    _populate(fk_db, other)
    fk_db.execute(delete(CvProfile).where(CvProfile.id == other.cv_id))
    fk_db.commit()
    assert _counts(fk_db)[:2] == (0, 0)


def test_the_database_refuses_a_session_for_a_missing_seeker(fk_db):
    ids = build_ids(fk_db)
    with pytest.raises(IntegrityError):
        _insert(fk_db, make_session(type(ids)(999999, ids.job_id, ids.cv_id)))


def test_dates_are_stored_as_given(db, ids):
    """expires_at is stored as written (the service sets created_at + 30 days)."""
    expires = datetime.now(UTC) + timedelta(days=30)
    row = _insert(db, make_session(ids, expires_at=expires))
    db.expire_all()
    assert abs((db.get(InterviewSession, row.id).expires_at.replace(tzinfo=UTC) - expires).total_seconds()) < 1
