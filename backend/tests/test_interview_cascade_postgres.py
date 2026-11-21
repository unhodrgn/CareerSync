"""What PostgreSQL itself does with the interview tables when no service is involved (M4 PostgreSQL QA, N3): PostgreSQL only.

The services delete a session's turns before the session, so they never use the foreign key; the SQLite fixture does not enforce foreign
keys at all (`fk_db` does, but it is SQLite). Here rows are removed with plain SQL statements (never the ORM, whose own cascade would hide
the database's), and the assertions are on what is left:

- deleting a session removes its turns, and not another session's, and the quota row of the seeker stays;
- deleting a user removes the seeker's sessions, turns and quota rows (and the CV that the session points at), and no other seeker's;
- deleting a job or a CV profile removes the sessions that point at it, with their turns, and keeps the quota;
- the partial unique index: at most one planning, created or live session per seeker, any number that are over, and the slot is free again
  as soon as the active one ends; each seeker has their own slot;
- `UNIQUE (session_id, seq)`, and each of the checks refuses its row *by name* (the name comes from the server's diagnostics, not from the
  text of its message, which quotes the failing row).

They need `TEST_DATABASE_URL` on PostgreSQL (see db_safety.py) and are SKIPPED without it. They ran and passed on PostgreSQL on 2026-11-22 (D77)."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.models import CvProfile, InterviewQuota, InterviewSession, InterviewTurn, JobPosting, User
from app.models.interview import QuotaKind
from app.services import interview_quota_service as quota

from .interview_fixtures import Ids, build_ids, make_session
from .test_interview_ingest_concurrency import PG

S, T, Q = InterviewSession.__table__, InterviewTurn.__table__, InterviewQuota.__table__
NOON = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)


def add_session(db, ids, status="completed", turns=2, **overrides) -> int:
    row = make_session(ids, status=status, **overrides)
    db.add(row)
    db.flush()
    for seq in range(1, turns + 1):
        mine = seq % 2 == 1
        db.add(
            InterviewTurn(session_id=row.id, seq=seq, role="agent" if mine else "candidate", kind="question" if mine else "answer", text=f"line {seq}")
        )
    db.commit()
    return row.id


def count(db, table, *conditions) -> int:
    db.rollback()
    return db.scalar(select(func.count()).select_from(table).where(*conditions))


def reserve(db, seeker_id, kind=QuotaKind.SESSION) -> None:
    assert quota.claim(db, seeker_id, kind, now=NOON) is True
    db.commit()


def used(db, seeker_id, kind=QuotaKind.SESSION) -> int:
    db.rollback()
    return quota.used(db, seeker_id, kind, now=NOON)


def remove(db, table, *conditions) -> None:
    db.execute(delete(table).where(*conditions))
    db.commit()


# ── The foreign keys ──


@PG
def test_postgres_deleting_a_session_row_removes_its_turns_and_only_its_own_and_keeps_the_quota(db):
    ids = build_ids(db)
    reserve(db, ids.seeker_id)
    gone, kept = add_session(db, ids, turns=3), add_session(db, ids, "aborted", turns=2)
    remove(db, S, S.c.id == gone)
    assert count(db, S, S.c.id == gone) == 0 and count(db, T, T.c.session_id == gone) == 0
    assert count(db, S, S.c.id == kept) == 1 and count(db, T, T.c.session_id == kept) == 2
    assert used(db, ids.seeker_id) == 1  # deleting a session never gives a reservation back


@PG
def test_postgres_deleting_a_user_removes_that_seekers_interview_rows_and_nobody_elses(db):
    one, two = build_ids(db, "one@interview.test"), build_ids(db, "two@interview.test")
    for ids in (one, two):
        reserve(db, ids.seeker_id)
        reserve(db, ids.seeker_id, QuotaKind.FEEDBACK_MODEL)
        add_session(db, ids, "completed", turns=2)
        add_session(db, ids, "aborted", turns=2)
    mine = list(db.scalars(select(S.c.id).where(S.c.seeker_id == one.seeker_id)))
    assert len(mine) == 2
    remove(db, User.__table__, User.__table__.c.id == one.seeker_id)
    assert count(db, S, S.c.seeker_id == one.seeker_id) == 0 and count(db, T, T.c.session_id.in_(mine)) == 0
    assert count(db, Q, Q.c.seeker_id == one.seeker_id) == 0  # the ledger goes with the user, and only then
    assert count(db, CvProfile.__table__, CvProfile.__table__.c.seeker_id == one.seeker_id) == 0
    assert count(db, JobPosting.__table__, JobPosting.__table__.c.id == one.job_id) == 1  # a job belongs to a company, not to the seeker
    assert (count(db, S, S.c.seeker_id == two.seeker_id), count(db, T), count(db, Q, Q.c.seeker_id == two.seeker_id)) == (2, 4, 2)


@PG
def test_postgres_deleting_a_job_removes_the_sessions_on_it_with_their_turns_and_keeps_the_quota(db):
    one, two = build_ids(db, "one@interview.test"), build_ids(db, "two@interview.test")
    for ids in (one, two):
        reserve(db, ids.seeker_id)
    on_job_one = [add_session(db, one, turns=2), add_session(db, Ids(two.seeker_id, one.job_id, two.cv_id), turns=2)]
    elsewhere = add_session(db, two, "aborted", turns=2)
    remove(db, JobPosting.__table__, JobPosting.__table__.c.id == one.job_id)
    assert count(db, S, S.c.id.in_(on_job_one)) == 0 and count(db, T, T.c.session_id.in_(on_job_one)) == 0
    assert count(db, S, S.c.id == elsewhere) == 1 and count(db, T, T.c.session_id == elsewhere) == 2
    assert used(db, one.seeker_id) == 1 and used(db, two.seeker_id) == 1


@PG
def test_postgres_deleting_a_cv_profile_removes_the_sessions_made_from_it_with_their_turns(db):
    ids = build_ids(db)
    profile = CvProfile.__table__
    document_id = db.scalar(select(profile.c.cv_document_id).where(profile.c.id == ids.cv_id))
    second = CvProfile(cv_document_id=document_id, seeker_id=ids.seeker_id, version=2, schema_version="cv_profile.v1", method="rules")
    db.add(second)
    db.commit()
    from_first = add_session(db, ids, turns=2)
    from_second = add_session(db, Ids(ids.seeker_id, ids.job_id, second.id), "aborted", turns=2)
    remove(db, profile, profile.c.id == ids.cv_id)
    assert count(db, S, S.c.id == from_first) == 0 and count(db, T, T.c.session_id == from_first) == 0
    assert count(db, S, S.c.id == from_second) == 1 and count(db, T, T.c.session_id == from_second) == 2


# ── The one-active-session index and the sequence number ──


@PG
def test_postgres_a_seeker_has_one_active_session_any_number_of_finished_ones_and_a_free_slot_when_it_ends(db):
    ids = build_ids(db)
    live = add_session(db, ids, "live", turns=0)
    add_session(db, ids, "completed", turns=0)
    add_session(db, ids, "aborted", turns=0)  # finished sessions never count
    assert count(db, S, S.c.seeker_id == ids.seeker_id) == 3
    for status in ("planning", "created", "live"):
        db.add(make_session(ids, status=status))
        with pytest.raises(IntegrityError) as refused:
            db.commit()
        assert refused.value.orig.diag.constraint_name == "uq_interview_sessions_active", status
        db.rollback()
    assert count(db, S, S.c.seeker_id == ids.seeker_id) == 3  # a refused insert left nothing behind, and the first rows are still there
    db.execute(update(S).where(S.c.id == live).values(status="completed", active_until=None))
    db.commit()
    assert add_session(db, ids, "created", turns=0)  # the slot is free as soon as the active one ends
    other = build_ids(db, "other@interview.test")
    assert add_session(db, other, "live", turns=0)  # and each seeker has a slot of their own
    assert count(db, S, S.c.seeker_id == ids.seeker_id, S.c.status.in_(("planning", "created", "live"))) == 1


@PG
def test_postgres_a_sequence_number_is_stored_once_per_session_and_a_failed_insert_changes_nothing(db):
    ids = build_ids(db)
    first = add_session(db, ids, "completed", turns=1)
    second = add_session(db, ids, "aborted", turns=0)
    db.add(InterviewTurn(session_id=first, seq=1, role="agent", kind="question", text="again"))
    with pytest.raises(IntegrityError) as refused:
        db.commit()
    assert refused.value.orig.diag.constraint_name == "uq_interview_turns_session_seq"
    db.rollback()
    assert [t.text for t in db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == first))] == ["line 1"]
    db.add(InterviewTurn(session_id=second, seq=1, role="agent", kind="question", text="another session, same number"))
    db.commit()  # the same number in another session is fine
    assert count(db, T) == 2


# ── Each check refuses its row, by name ──


def refused_by(db, name, statement=None, row=None):
    """Run the statement (or add the row) and commit: the server must refuse it with the check called `name`; nothing is kept."""
    with pytest.raises(IntegrityError) as refused:
        if row is not None:
            db.add(row)
        else:
            db.execute(statement)
        db.commit()
    db.rollback()
    assert refused.value.orig.diag.constraint_name == name


@PG
@pytest.mark.parametrize(
    "name, overrides",
    [
        ("ck_interview_sessions_status", {"status": "expired"}),
        ("ck_interview_sessions_feedback_attempts", {"status": "completed", "feedback_attempts": -1}),
        ("ck_interview_sessions_feedback_method", {"status": "completed", "feedback": {"strengths": []}, "feedback_method": None}),
    ],
    ids=["status", "feedback-attempts", "feedback-without-method"],
)
def test_postgres_a_session_that_breaks_a_check_is_refused_by_that_check(db, name, overrides):
    ids = build_ids(db)
    refused_by(db, name, row=make_session(ids, **overrides))
    assert count(db, S) == 0
    ok = make_session(ids, status="completed", feedback={"strengths": []}, feedback_method="rules", feedback_attempts=0)
    db.add(ok)
    db.commit()  # the same row without the fault is accepted
    assert count(db, S) == 1


@PG
@pytest.mark.parametrize(
    "name, values",
    [
        ("ck_interview_turns_seq", {"seq": 0}),
        ("ck_interview_turns_role", {"role": "bot"}),
        ("ck_interview_turns_item_index", {"item_index": -1}),
        ("ck_interview_turns_text_len", {"text": "가" * 4001}),
    ],
    ids=["seq", "role", "item-index", "text-length"],
)
def test_postgres_a_turn_that_breaks_a_check_is_refused_by_that_check(db, name, values):
    ids = build_ids(db)
    session_id = add_session(db, ids, "live", turns=0)
    good = {"session_id": session_id, "seq": 1, "role": "candidate", "kind": "answer", "text": "ok"}
    refused_by(db, name, statement=insert(T).values(**{**good, **values}))
    assert count(db, T) == 0
    db.execute(insert(T).values(**{**good, "text": "가" * 4000}))  # the longest text there is room for is accepted
    db.commit()
    assert count(db, T) == 1


@PG
@pytest.mark.parametrize(
    "name, values",
    [
        ("ck_interview_quota_kind", {"kind": "bogus"}),
        ("ck_interview_quota_used", {"used": 4, "quota_limit": 3}),
        ("ck_interview_quota_used", {"used": -1, "quota_limit": 3}),
        ("ck_interview_quota_limit", {"used": 0, "quota_limit": -1}),
    ],
    ids=["kind", "used-above-limit", "used-below-zero", "negative-limit"],
)
def test_postgres_a_quota_row_that_breaks_a_check_is_refused_by_that_check(db, name, values):
    ids = build_ids(db)
    good = {"seeker_id": ids.seeker_id, "kst_day": date(2026, 11, 16), "kind": "session", "used": 0, "quota_limit": 3}
    with pytest.raises(IntegrityError) as refused:
        db.execute(insert(Q).values(**{**good, **values}))
        db.commit()
    db.rollback()
    # A row that breaks two checks is refused by one of them: the server tries them in the order of their names
    assert refused.value.orig.diag.constraint_name in {name, "ck_interview_quota_limit", "ck_interview_quota_used"}
    if name != "ck_interview_quota_limit":
        assert refused.value.orig.diag.constraint_name == name
    assert count(db, Q) == 0
    db.execute(insert(Q).values(**good))
    db.commit()
    assert count(db, Q) == 1
