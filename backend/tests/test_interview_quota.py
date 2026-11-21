"""The daily quota ledger of the practice interview (M4 S1): sequential claims and denial, independent kinds, KST day
rollover, the limit a row was created with, the CHECK that keeps `used` within it, no way to give a reservation back, and
that database errors are not hidden.

Real concurrency is tested only on PostgreSQL (`TEST_DATABASE_URL=postgresql+psycopg://…`, as the other PG-only tests
of this suite): the shared SQLite test database is one connection, so it proves none of it. Those tests are skipped
without a PostgreSQL URL.
"""
import inspect
import os
import threading
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import InterviewQuota, InterviewSession
from app.models.interview import QuotaKind
from app.services import interview_quota_service as quota
from app.services.interview_quota_service import KST, claim, kst_day, limit_for, used

from .interview_fixtures import build_ids, fk_db, make_session  # noqa: F401  (fk_db is a fixture)

NOON = datetime(2026, 11, 16, 12, 0, tzinfo=KST)
TABLE = InterviewQuota.__table__
SETTING = {
    QuotaKind.SESSION: "INTERVIEW_DAILY_SESSIONS",
    QuotaKind.PLAN_MODEL: "INTERVIEW_DAILY_PLAN_MODEL_CALLS",
    QuotaKind.FEEDBACK_MODEL: "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS",
}


@pytest.fixture
def ids(db):
    return build_ids(db)


def _row(db, seeker_id, kind, now=NOON):
    """(used, quota_limit) of the row of that day, or None."""
    row = db.execute(
        select(TABLE.c.used, TABLE.c.quota_limit).where(TABLE.c.seeker_id == seeker_id, TABLE.c.kst_day == kst_day(now), TABLE.c.kind == kind)
    ).first()
    return None if row is None else tuple(row)


def _take(db, seeker_id, kind, times, now=NOON):
    return [claim(db, seeker_id, kind, now=now) for _ in range(times)]


# ── The limits ──


def test_the_daily_limits_are_three_each():
    assert (settings.INTERVIEW_DAILY_SESSIONS, settings.INTERVIEW_DAILY_PLAN_MODEL_CALLS, settings.INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS) == (3, 3, 3)
    assert {kind: limit_for(kind) for kind in QuotaKind.ALL} == {"session": 3, "plan_model": 3, "feedback_model": 3}


def test_each_kind_reads_its_own_setting(db, ids, monkeypatch):
    """All three limits are 3 by default, so only different values show that each kind reads its own setting."""
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 1)
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_PLAN_MODEL_CALLS", 2)
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS", 4)
    assert [limit_for(kind) for kind in QuotaKind.ALL] == [1, 2, 4]
    assert [sum(_take(db, ids.seeker_id, kind, 6)) for kind in QuotaKind.ALL] == [1, 2, 4]
    assert [_row(db, ids.seeker_id, kind) for kind in QuotaKind.ALL] == [(1, 1), (2, 2), (4, 4)]


@pytest.mark.parametrize("value", [-1, 32768, True, 2.5, "3", None])
def test_a_bad_limit_setting_is_refused(monkeypatch, value):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", value)
    with pytest.raises(ValueError):
        limit_for(QuotaKind.SESSION)


# ── Sequential claims ──


@pytest.mark.parametrize("kind", QuotaKind.ALL)
def test_three_claims_are_granted_and_the_fourth_is_denied(db, ids, kind):
    assert _take(db, ids.seeker_id, kind, 3) == [True, True, True]
    assert claim(db, ids.seeker_id, kind, now=NOON) is False
    assert claim(db, ids.seeker_id, kind, now=NOON) is False  # and stays denied
    db.commit()
    assert used(db, ids.seeker_id, kind, now=NOON) == 3
    assert _row(db, ids.seeker_id, kind) == (3, 3)


def test_a_denial_changes_nothing_and_raises_nothing(db, ids):
    _take(db, ids.seeker_id, QuotaKind.SESSION, 3)
    db.commit()
    before = _row(db, ids.seeker_id, QuotaKind.SESSION)
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is False
    db.commit()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == before


def test_a_limit_of_zero_denies_every_claim(db, ids, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 0)
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 2) == [False, False]
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (0, 0)


def test_the_kinds_are_independent(db, ids):
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 4) == [True, True, True, False]
    assert _take(db, ids.seeker_id, QuotaKind.PLAN_MODEL, 2) == [True, True]
    assert _take(db, ids.seeker_id, QuotaKind.FEEDBACK_MODEL, 1) == [True]
    assert [used(db, ids.seeker_id, k, now=NOON) for k in QuotaKind.ALL] == [3, 2, 1]


def test_the_seekers_are_independent(db, ids):
    other = build_ids(db, "s2@interview.test")
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 4) == [True, True, True, False]
    assert _take(db, other.seeker_id, QuotaKind.SESSION, 4) == [True, True, True, False]
    assert used(db, other.seeker_id, QuotaKind.SESSION, now=NOON) == 3


def test_used_is_zero_before_any_claim(db, ids):
    assert used(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) == 0
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) is None


# ── The KST day and the clock ──


def test_the_day_is_the_kst_day():
    assert kst_day(datetime(2026, 11, 16, 14, 59, 59, tzinfo=UTC)) == date(2026, 11, 16)
    assert kst_day(datetime(2026, 11, 16, 15, 0, 0, tzinfo=UTC)) == date(2026, 11, 17)  # 00:00 KST
    assert kst_day(datetime(2026, 11, 16, 23, 59, 59, 999999, tzinfo=KST)) == date(2026, 11, 16)
    assert kst_day(datetime(2026, 11, 17, 0, 0, 0, tzinfo=KST)) == date(2026, 11, 17)


def test_the_default_clock_is_now():
    before = datetime.now(KST).date()
    got = kst_day()
    assert got in (before, datetime.now(KST).date())


def test_a_naive_time_is_refused(db, ids):
    with pytest.raises(ValueError):
        kst_day(datetime(2026, 11, 16, 12, 0))
    with pytest.raises(ValueError):
        claim(db, ids.seeker_id, QuotaKind.SESSION, now=datetime(2026, 11, 16, 12, 0))


def test_a_new_kst_day_starts_a_new_row(db, ids):
    last_second = datetime(2026, 11, 16, 23, 59, 59, tzinfo=KST)
    midnight = datetime(2026, 11, 17, 0, 0, 0, tzinfo=KST)
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 4, now=last_second) == [True, True, True, False]
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 4, now=midnight) == [True, True, True, False]
    db.commit()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION, last_second) == (3, 3)
    assert _row(db, ids.seeker_id, QuotaKind.SESSION, midnight) == (3, 3)


def test_the_utc_clock_rolls_over_at_kst_midnight(db, ids):
    before = datetime(2026, 11, 16, 14, 59, 59, tzinfo=UTC)  # 23:59:59 KST
    after = datetime(2026, 11, 16, 15, 0, 0, tzinfo=UTC)  # 00:00:00 KST the next day
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 4, now=before) == [True, True, True, False]
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=after) is True


# ── The limit a row was created with ──


def test_a_raised_limit_does_not_change_a_day_that_started(db, ids, monkeypatch):
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True  # the row is created with limit 3
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 5)
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 3) == [True, True, False]  # still 3 for this day
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (3, 3)
    tomorrow = datetime(2026, 11, 17, 12, 0, tzinfo=KST)
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 6, now=tomorrow) == [True] * 5 + [False]  # the new day gets 5
    assert _row(db, ids.seeker_id, QuotaKind.SESSION, tomorrow) == (5, 5)


def test_a_lowered_limit_does_not_change_a_day_that_started(db, ids, monkeypatch):
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 2) == [True, True]
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 1)
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True  # this day keeps its limit of 3
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is False
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (3, 3)
    tomorrow = datetime(2026, 11, 17, 12, 0, tzinfo=KST)
    assert _take(db, ids.seeker_id, QuotaKind.SESSION, 2, now=tomorrow) == [True, False]  # a new day gets the lowered limit


# ── The database keeps `used` within the limit ──


def test_a_raw_increment_beyond_the_limit_fails_the_check(db, ids):
    _take(db, ids.seeker_id, QuotaKind.SESSION, 3)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(update(TABLE).values(used=TABLE.c.used + 1))
    db.rollback()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (3, 3)


@pytest.mark.parametrize(
    "values",
    [
        {"used": 4, "quota_limit": 3},  # over the limit
        {"used": -1, "quota_limit": 3},
        {"used": 0, "quota_limit": -1},
        {"used": 0, "quota_limit": 3, "kind": "refund"},  # an unknown kind
    ],
)
def test_a_row_outside_the_rules_is_refused(db, ids, values):
    row = {"seeker_id": ids.seeker_id, "kst_day": date(2026, 11, 16), "kind": "session", **values}
    with pytest.raises(IntegrityError):
        db.execute(insert(TABLE).values(**row))
        db.commit()


def test_a_day_has_one_row_per_seeker_and_kind(db, ids):
    row = {"seeker_id": ids.seeker_id, "kst_day": date(2026, 11, 16), "kind": "session", "used": 0, "quota_limit": 3}
    db.execute(insert(TABLE).values(**row))
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(insert(TABLE).values(**row))
        db.commit()


# ── A claim belongs to the caller's transaction ──


def test_a_claim_is_kept_only_when_the_caller_commits(db, ids):
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True
    db.rollback()  # the caller's transaction failed: nothing was taken
    assert used(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) == 0
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True
    db.commit()
    db.rollback()  # a later rollback does not take it back
    assert used(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) == 1


def test_losing_the_row_creation_race_is_fine_and_keeps_the_callers_work(db, ids, monkeypatch):
    """Another request creates today's row between our UPDATE and our INSERT: the INSERT fails on the primary key, the
    claim carries on with the row that is there, and what the caller had already done in the transaction is kept."""
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True  # "the other request" (used = 1)
    db.commit()
    db.add(make_session(ids, status="planning"))  # the caller's pending work
    real_increment, real_exists = quota._increment, quota._exists
    calls = {"increment": 0, "exists": 0}

    def increment(*args):
        calls["increment"] += 1
        return False if calls["increment"] == 1 else real_increment(*args)  # the first UPDATE saw no row

    def exists(*args):
        calls["exists"] += 1
        return False if calls["exists"] == 1 else real_exists(*args)  # and so did the first existence check

    monkeypatch.setattr(quota, "_increment", increment)
    monkeypatch.setattr(quota, "_exists", exists)
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True
    assert calls == {"increment": 2, "exists": 2}  # the INSERT lost, the row was found, the UPDATE then took the reservation
    db.commit()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (2, 3)
    assert db.scalar(select(InterviewSession.status)) == "planning"  # the caller's work survived the savepoint


def _count_increments(monkeypatch, *, miss_first=0):
    """Wrap `_increment`: count its calls, and make the first `miss_first` of them answer "no row matched" without running (our UPDATE ran before
    another request's row was visible)."""
    real, calls = quota._increment, {"n": 0}

    def increment(*args):
        calls["n"] += 1
        return False if calls["n"] <= miss_first else real(*args)

    monkeypatch.setattr(quota, "_increment", increment)
    return calls


@pytest.mark.parametrize("kind", QuotaKind.ALL)
def test_a_row_created_between_our_update_and_our_existence_check_still_gives_a_reservation(db, ids, monkeypatch, kind):
    """Another request creates and commits today's row after our UPDATE looked for it and before our existence check (READ COMMITTED: each
    statement sees what was committed before it started). Our UPDATE matched no row only because the row was not there yet, so a row with room
    (used 1 of 3) must give us a reservation: the UPDATE is tried once more (D75)."""
    assert claim(db, ids.seeker_id, kind, now=NOON) is True  # "the other request": it created the row, used = 1
    db.commit()
    calls = _count_increments(monkeypatch, miss_first=1)
    assert claim(db, ids.seeker_id, kind, now=NOON) is True
    assert calls["n"] == 2  # the first UPDATE missed, the retry took the reservation
    db.commit()
    assert _row(db, ids.seeker_id, kind) == (2, 3)


@pytest.mark.parametrize("kind", QuotaKind.ALL)
def test_a_denied_claim_tries_the_update_once_more_and_the_answer_is_still_no(db, ids, monkeypatch, kind):
    """A row with no room (3 of 3): the UPDATE and its one retry both match no row, and the answer is False, with nothing changed."""
    assert _take(db, ids.seeker_id, kind, 3) == [True, True, True]
    db.commit()
    calls = _count_increments(monkeypatch)
    assert claim(db, ids.seeker_id, kind, now=NOON) is False
    assert calls["n"] == 2
    db.commit()
    assert _row(db, ids.seeker_id, kind) == (3, 3)


@pytest.mark.parametrize("kind", QuotaKind.ALL)
def test_the_retry_is_one_and_not_a_loop(db, ids, monkeypatch, kind):
    """If the retry matches no row either, the claim gives up: two UPDATEs, never a third (here the row has room, and the UPDATE is made to miss)."""
    assert claim(db, ids.seeker_id, kind, now=NOON) is True  # used = 1 of 3
    db.commit()
    calls = _count_increments(monkeypatch, miss_first=99)
    assert claim(db, ids.seeker_id, kind, now=NOON) is False
    assert calls["n"] == 2
    db.commit()
    assert _row(db, ids.seeker_id, kind) == (1, 3)


def test_a_missing_row_is_created_inside_a_savepoint_and_an_existing_one_needs_none(db, ids):
    """On PostgreSQL a failed INSERT aborts the whole transaction unless it ran in a savepoint, so the creation must use one
    (SQLite would not show the difference)."""
    savepoints: list[str] = []

    def on_savepoint(_connection, name):
        savepoints.append(name)

    event.listen(db.get_bind(), "savepoint", on_savepoint)
    try:
        assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True  # creates the row
        assert len(savepoints) == 1
        assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True  # the row is there: no savepoint, one UPDATE
        assert len(savepoints) == 1
    finally:
        event.remove(db.get_bind(), "savepoint", on_savepoint)


def test_a_database_error_that_is_not_the_lost_race_is_not_hidden(fk_db, monkeypatch):
    # A seeker that does not exist: the foreign key fails and no row is there, so it is an error, not a lost race
    with pytest.raises(IntegrityError):
        claim(fk_db, 999999, QuotaKind.SESSION, now=NOON)
    fk_db.rollback()
    assert fk_db.execute(select(TABLE.c.used)).first() is None


def test_a_check_violation_while_creating_the_row_is_not_hidden(db, ids, monkeypatch):
    monkeypatch.setattr(quota, "limit_for", lambda kind: -1)  # the CHECK on quota_limit refuses the row
    with pytest.raises(IntegrityError):
        claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON)
    db.rollback()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) is None


def test_an_operational_error_is_not_hidden(db, ids, monkeypatch):
    real_execute = db.execute

    def execute(statement, *args, **kwargs):
        if getattr(statement, "is_insert", False):
            raise OperationalError("INSERT", {}, Exception("disk I/O error"))
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", execute)
    with pytest.raises(OperationalError):
        claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON)


def test_the_arguments_are_checked(db, ids):
    with pytest.raises(ValueError):
        claim(db, ids.seeker_id, "tokens", now=NOON)
    with pytest.raises(ValueError):
        used(db, ids.seeker_id, "tokens", now=NOON)
    for bad in (True, "1", None, 1.0):
        with pytest.raises(TypeError):
            claim(db, bad, QuotaKind.SESSION, now=NOON)


# ── No reservation is ever given back ──


def test_there_is_no_api_to_give_a_reservation_back():
    public = sorted(
        name for name, value in vars(quota).items() if not name.startswith("_") and inspect.isfunction(value) and value.__module__ == quota.__name__
    )
    assert public == ["claim", "kst_day", "limit_for", "used"]
    source = inspect.getsource(quota)
    for forbidden in ("delete(", "used - ", "used -", "- 1", "refund", "release"):
        assert forbidden not in source, forbidden


def test_deleting_a_session_leaves_the_quota_unchanged(db, ids):
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True
    session = make_session(ids)
    db.add(session)
    db.commit()
    db.delete(session)
    db.commit()
    assert db.scalar(select(InterviewSession.id)) is None
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (1, 3)


def test_cascade_deleting_a_session_in_the_database_leaves_the_quota_unchanged(fk_db):
    ids = build_ids(fk_db)
    assert _take(fk_db, ids.seeker_id, QuotaKind.SESSION, 2) == [True, True]
    session = make_session(ids)
    fk_db.add(session)
    fk_db.commit()
    from sqlalchemy import delete

    fk_db.execute(delete(InterviewSession).where(InterviewSession.id == session.id))
    fk_db.commit()
    assert _row(fk_db, ids.seeker_id, QuotaKind.SESSION) == (2, 3)
    assert claim(fk_db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True  # the third and last one
    assert claim(fk_db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is False


# ── Real concurrency: PostgreSQL only ──

PG = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL")


def _parallel(db, count, work):
    """Run `work(session, index)` in `count` threads, each with its own session, released together; return the results."""
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    barrier = threading.Barrier(count)
    results, errors = [None] * count, []

    def run(index):
        session = factory()
        try:
            barrier.wait(30)
            results[index] = work(session, index)
        except BaseException as error:  # noqa: BLE001  (reported by the test)
            errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads), "a thread did not finish"
    assert not errors, errors
    return results


@PG
@pytest.mark.parametrize("kind", QuotaKind.ALL)
def test_pg_parallel_claims_never_exceed_the_limit(db, ids, kind):
    """16 requests race for a day with no row yet: exactly 3 are granted, and the table says 3 of 3."""

    def work(session, _index):
        granted = claim(session, ids.seeker_id, kind, now=NOON)
        session.commit()
        return granted

    results = _parallel(db, 16, work)
    assert sum(results) == 3
    db.rollback()
    assert _row(db, ids.seeker_id, kind) == (3, 3)


@PG
def test_pg_parallel_claims_of_two_seekers_do_not_interfere(db, ids):
    other = build_ids(db, "s2@interview.test")
    owners = [ids.seeker_id] * 12 + [other.seeker_id] * 12

    def work(session, index):
        granted = claim(session, owners[index], QuotaKind.SESSION, now=NOON)
        session.commit()
        return owners[index], granted

    results = _parallel(db, 24, work)
    for seeker in (ids.seeker_id, other.seeker_id):
        assert sum(granted for owner, granted in results if owner == seeker) == 3
        db.rollback()
        assert _row(db, seeker, QuotaKind.SESSION) == (3, 3)


@PG
def test_pg_parallel_claims_with_a_raised_limit_still_stop_at_the_row_limit(db, ids, monkeypatch):
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True  # the row is created with limit 3, used 1
    db.commit()
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_SESSIONS", 9)

    def work(session, _index):
        granted = claim(session, ids.seeker_id, QuotaKind.SESSION, now=NOON)
        session.commit()
        return granted

    assert sum(_parallel(db, 12, work)) == 2  # 3 - 1 left on the row, whatever the setting says now
    db.rollback()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (3, 3)


@PG
def test_pg_a_rolled_back_claim_takes_nothing_and_a_committed_one_keeps_its_place(db, ids):
    def work(session, index):
        granted = claim(session, ids.seeker_id, QuotaKind.SESSION, now=NOON)
        keep = granted and index % 2 == 0
        session.commit() if keep else session.rollback()
        return granted, keep

    results = _parallel(db, 12, work)
    kept = sum(keep for _granted, keep in results)
    db.rollback()
    assert kept <= 3
    assert used(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) == kept  # only committed claims count


@PG
def test_pg_a_raw_increment_beyond_the_limit_fails_the_check(db, ids):
    _take(db, ids.seeker_id, QuotaKind.SESSION, 3)
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(update(TABLE).values(used=TABLE.c.used + 1))
    db.rollback()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (3, 3)


@PG
def test_pg_a_missing_seeker_is_an_error_and_not_a_denial(db):
    with pytest.raises(IntegrityError):
        claim(db, 999999, QuotaKind.SESSION, now=NOON)
    db.rollback()
    assert db.execute(select(TABLE.c.used)).first() is None


@PG
def test_pg_deleting_a_session_leaves_the_quota_unchanged(db, ids):
    assert claim(db, ids.seeker_id, QuotaKind.SESSION, now=NOON) is True
    session = make_session(ids)
    db.add(session)
    db.commit()
    db.delete(session)
    db.commit()
    assert _row(db, ids.seeker_id, QuotaKind.SESSION) == (1, 3)
