"""Retention of practice interviews (M4 S2): the lazy purge on create and list (own sessions, and at most 50 of anyone's on create),
purging that never fails a request, expired quota rows only from days before today, the maintenance the script runs
(`--dry-run`, `--batch`), and logs and output that hold counts and nothing else.

Nothing here schedules anything: the app has no scheduler, and these tests do not claim that expired data is deleted automatically.

No test depends on the real date. Every test runs on a clock it sets, at four instants (noon KST, the last and the first second of a KST
day, another year); the days of the quota rows are derived from that clock; and a tripwire makes any read of the wall clock by the time
and quota services fail at once, whatever day the suite runs on (the script tests used to pass on one day only)."""
import contextlib
import importlib.util
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.models import InterviewQuota, InterviewSession, InterviewTurn
from app.models.interview import InterviewStatus as S
from app.services import interview_quota_service as quota_service
from app.services import interview_service as svc
from app.services import interview_time

from .interview_fixtures import Clock, Ids, build_world, make_session

QUOTA = InterviewQuota.__table__
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "purge_interviews.py"
SECRET = "SECRET-MARKER-답변-내용"


INSTANTS = {
    "noon-kst": datetime(2026, 11, 16, 3, 0, tzinfo=UTC),
    "last-second-of-a-kst-day": datetime(2026, 11, 16, 14, 59, 59, tzinfo=UTC),
    "first-second-of-a-kst-day": datetime(2026, 11, 16, 15, 0, 0, tzinfo=UTC),
    "another-year": datetime(2031, 3, 1, 21, 30, tzinfo=UTC),
}


@pytest.fixture(params=list(INSTANTS), ids=list(INSTANTS))
def clock(request):
    return Clock(INSTANTS[request.param])


class _NoWallClock:
    """Stands in for `datetime` in the time and quota services: only `datetime.now(...)` is read from it there."""

    @staticmethod
    def now(*args, **kwargs):
        raise AssertionError("the wall clock was read: pass a clock or an explicit instant")


@pytest.fixture(autouse=True)
def no_wall_clock(monkeypatch):
    monkeypatch.setattr(interview_time, "datetime", _NoWallClock)
    monkeypatch.setattr(quota_service, "datetime", _NoWallClock)


@pytest.fixture
def world(db):
    return build_world(db)


def ids_of(world) -> Ids:
    return Ids(world.user.id, world.job_id, world.cv_profile_id)


def add(db, world, clock, status=S.COMPLETED, *, expires_in=86400, turns=1, **overrides):
    now = clock()
    row = make_session(ids_of(world), status=status, created_at=now, expires_at=now + timedelta(seconds=expires_in), **overrides)
    db.add(row)
    db.flush()
    for seq in range(1, turns + 1):
        db.add(InterviewTurn(session_id=row.id, seq=seq, role="candidate", kind="answer", text=f"{SECRET} {seq}"))
    db.commit()
    return row.id


def count(db, model=InterviewSession):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


def quota_row(db, seeker_id, day, kind="session", used=1):
    db.execute(insert(QUOTA).values(seeker_id=seeker_id, kst_day=day, kind=kind, used=used, quota_limit=3))
    db.commit()


def physical_status(db):
    db.expire_all()
    rows = db.execute(select(InterviewSession.status, func.count()).group_by(InterviewSession.status)).all()
    return {status: n for status, n in rows}


def create(db, world, clock):
    return svc.create_session(db, world.user, world.job_id, consent_transcript=True, consent_version="2026-11-16", clock=clock)


class Boom:
    """A purge that fails the way a database fails."""

    def __call__(self, *args, **kwargs):
        raise OperationalError("DELETE", {}, Exception("connection lost"))


# ── Lazy purge on create, history and delete ──


def test_create_removes_the_seekers_expired_sessions_and_at_most_fifty_of_anyone_elses(db, world, clock):
    stranger = build_world(db, email="stranger@interview.test")
    mine = [add(db, world, clock, expires_in=-1) for _ in range(3)]
    theirs = [add(db, stranger, clock, expires_in=-1, turns=2) for _ in range(60)]
    kept = add(db, stranger, clock, expires_in=86400)
    assert count(db) == 64 and count(db, InterviewTurn) == 3 + 120 + 1
    create(db, world, clock)
    remaining = {r for r in db.scalars(select(InterviewSession.id))}
    assert not remaining & set(mine)  # the seeker's own expired ones: all
    assert len(set(theirs) & remaining) == 10  # anyone's: a batch of 50, not all 60
    assert kept in remaining  # a session that has not expired is never touched
    left_turns = db.scalar(select(func.count()).select_from(InterviewTurn).where(InterviewTurn.session_id.in_(mine + theirs)))
    assert left_turns == 10 * 2  # the turns went with their sessions; only the 10 left have theirs


def test_a_second_create_continues_the_global_purge(db, world, clock):
    stranger = build_world(db, email="stranger@interview.test")
    for _ in range(60):
        add(db, stranger, clock, expires_in=-1)
    svc.end(db, world.user, create(db, world, clock).view.id, clock=clock)
    assert count(db) == 10 + 1
    create(db, world, clock)
    assert count(db) == 1 + 1  # the rest of the expired ones, and this seeker's two sessions


def test_history_removes_only_the_seekers_own_expired_sessions(db, world, clock):
    stranger = build_world(db, email="stranger@interview.test")
    own_expired = add(db, world, clock, expires_in=-1)
    other_expired = add(db, stranger, clock, expires_in=-1)
    fresh = add(db, world, clock)
    page = svc.history(db, world.user, clock=clock)
    assert [i.id for i in page.items] == [fresh]
    remaining = set(db.scalars(select(InterviewSession.id)))
    assert own_expired not in remaining and other_expired in remaining and fresh in remaining


def test_a_detail_is_hidden_when_expired_but_does_not_delete(db, world, clock):
    from app.core.errors import AppError

    expired = add(db, world, clock, expires_in=-1)
    with pytest.raises(AppError):
        svc.detail(db, world.user, expired, clock=clock)
    assert count(db) == 1  # a GET of one session does no maintenance


def test_delete_of_an_expired_session_removes_it_and_says_not_found(db, world, clock):
    from app.core.errors import AppError

    expired = add(db, world, clock, expires_in=-1)
    with pytest.raises(AppError) as error:
        svc.delete(db, world.user, expired, clock=clock)
    assert error.value.status_code == 404 and count(db) == 0 and count(db, InterviewTurn) == 0


def test_the_purge_takes_the_oldest_ids_first_and_honours_the_batch(db, world, clock):
    ids = [add(db, world, clock, expires_in=-1) for _ in range(5)]
    assert svc.purge_expired(db, now=clock(), seeker_id=None, batch=2) == 2
    assert set(db.scalars(select(InterviewSession.id))) == set(ids[2:])
    assert svc.purge_expired(db, now=clock(), seeker_id=world.user.id, batch=50) == 3
    assert svc.purge_expired(db, now=clock(), seeker_id=None, batch=50) == 0


def test_a_session_is_purged_from_the_moment_it_expires_and_not_before(db, world, clock):
    add(db, world, clock, expires_in=100)
    assert svc.purge_expired(db, now=clock() + timedelta(seconds=99), seeker_id=None, batch=50) == 0
    assert svc.purge_expired(db, now=clock() + timedelta(seconds=100), seeker_id=None, batch=50) == 1


# ── Maintenance never fails the request ──


@pytest.mark.parametrize("call", ["create", "history", "delete"])
def test_a_failing_purge_does_not_fail_the_request(db, world, clock, monkeypatch, caplog, call):
    monkeypatch.setattr(svc, "purge_expired", Boom())
    session_id = add(db, world, clock, S.ABORTED)
    caplog.set_level(logging.WARNING, logger=svc.log.name)
    if call == "create":
        assert create(db, world, clock).view.status == "created"
    elif call == "history":
        assert [i.id for i in svc.history(db, world.user, clock=clock).items] == [session_id]
    else:
        svc.delete(db, world.user, session_id, clock=clock)
        assert count(db) == 0
    assert "OperationalError" in caplog.text and "connection lost" not in caplog.text  # the type only
    assert "retention maintenance failed" in caplog.text


# ── Expired quota rows ──


def test_only_quota_rows_of_days_before_today_are_deleted(db, world, clock):
    seeker = world.user.id
    today = quota_service.kst_day(clock())
    yesterday, tomorrow = today - timedelta(days=1), today + timedelta(days=1)
    for day in (yesterday, today, tomorrow):
        quota_row(db, seeker, day)
    assert svc.purge_old_quota(db, now=clock(), dry_run=True) == 1 and count(db, InterviewQuota) == 3
    assert svc.purge_old_quota(db, now=clock()) == 1
    assert sorted(d for (d,) in db.execute(select(QUOTA.c.kst_day))) == [today, tomorrow]  # today's reservation stays
    assert svc.purge_old_quota(db, now=clock()) == 0


def test_the_day_boundary_is_kst(db, world, clock):
    seeker = world.user.id
    quota_row(db, seeker, date(2026, 11, 16))
    late = datetime(2026, 11, 16, 14, 59, tzinfo=UTC)  # 23:59 KST: Nov 16 is still today
    assert svc.purge_old_quota(db, now=late) == 0
    after_midnight = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)  # 00:00 KST on Nov 17
    assert svc.purge_old_quota(db, now=after_midnight) == 1


# ── The maintenance the script runs ──


def stale_and_expired(db, world, clock):
    stale = add(db, world, clock, S.CREATED, active_until=clock() - timedelta(seconds=1))
    expired = [add(db, world, clock, S.COMPLETED, expires_in=-1, turns=2) for _ in range(5)]
    today = quota_service.kst_day(clock())  # derived from the clock: yesterday's row is past, today's is the reservation that stays
    quota_row(db, world.user.id, today - timedelta(days=1))
    quota_row(db, world.user.id, today)
    return stale, expired


def test_a_dry_run_only_counts(db, world, clock):
    stale_and_expired(db, world, clock)
    report = svc.maintenance(db, clock=clock, dry_run=True)
    assert (report.settled, report.purged_sessions, report.purged_quota_rows, report.dry_run) == (1, 5, 1, True)
    assert (count(db), count(db, InterviewTurn), count(db, InterviewQuota)) == (6, 11, 2)  # nothing deleted, 10 turns of the expired ones + 1
    assert physical_status(db) == {S.CREATED: 1, S.COMPLETED: 5}  # and nothing settled


def test_maintenance_settles_purges_in_batches_and_keeps_todays_quota(db, world, clock):
    stale, _ = stale_and_expired(db, world, clock)
    report = svc.maintenance(db, clock=clock, batch=2)
    assert (report.settled, report.purged_sessions, report.purged_quota_rows, report.dry_run) == (1, 5, 1, False)
    db.expire_all()
    row = db.get(InterviewSession, stale)
    assert (row.status, row.end_reason) == (S.ABORTED, "not_joined")
    assert (count(db), count(db, InterviewTurn), count(db, InterviewQuota)) == (1, 1, 1)  # the stale session and its turn stay: it has not expired
    again = svc.maintenance(db, clock=clock)
    assert (again.settled, again.purged_sessions, again.purged_quota_rows) == (0, 0, 0)


def test_the_maintenance_report_and_log_hold_counts_only(db, world, clock, caplog):
    add(db, world, clock, S.COMPLETED, expires_in=-1, feedback={"strengths": [SECRET]}, feedback_method="rules")
    add(db, world, clock, S.COMPLETED, expires_in=86400, turns=3)
    caplog.set_level(logging.INFO, logger=svc.log.name)
    svc.maintenance(db, clock=clock)
    assert SECRET not in caplog.text and "interview maintenance: settled=0 purged_sessions=1 purged_quota_rows=0 dry_run=False" in caplog.text


# ── scripts/purge_interviews.py ──


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("purge_interviews_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_runs_the_maintenance_and_prints_counts_only(db, world, clock, script, capsys, caplog):
    stale_and_expired(db, world, clock)
    caplog.set_level(logging.INFO)
    assert script.main(["--batch", "2"], session_factory=lambda: contextlib.nullcontext(db), clock=clock) == 0
    out = capsys.readouterr().out
    assert out.strip() == "settled=1 purged_sessions=5 purged_quota_rows=1"
    assert SECRET not in out and SECRET not in caplog.text
    assert count(db) == 1


def test_the_script_dry_run_changes_nothing(db, world, clock, script, capsys):
    stale_and_expired(db, world, clock)
    assert script.main(["--dry-run"], session_factory=lambda: contextlib.nullcontext(db), clock=clock) == 0
    assert capsys.readouterr().out.strip() == "dry run, nothing changed: would_settle=1 would_purge_sessions=5 would_purge_quota_rows=1"
    assert (count(db), count(db, InterviewTurn), count(db, InterviewQuota)) == (6, 11, 2)
    assert physical_status(db) == {S.CREATED: 1, S.COMPLETED: 5}


def test_the_script_passes_a_clock_on_only_when_it_is_given(script, monkeypatch, clock):
    seen = []

    def fake(db, **kwargs):
        seen.append(kwargs)
        return svc.MaintenanceReport(0, 0, 0, kwargs["dry_run"])

    monkeypatch.setattr(svc, "maintenance", fake)
    assert script.main([], session_factory=lambda: contextlib.nullcontext(None)) == 0
    assert script.main(["--dry-run", "--batch", "7"], session_factory=lambda: contextlib.nullcontext(None), clock=clock) == 0
    assert seen[0] == {"batch": 500, "dry_run": False}  # the command line: no clock, so the real one
    assert seen[1] == {"batch": 7, "dry_run": True, "clock": clock}


def test_the_wall_clock_tripwire_fires_on_a_default_clock_and_not_on_an_explicit_instant(db, world, script):
    with pytest.raises(AssertionError, match="wall clock"):
        interview_time.utcnow()
    with pytest.raises(AssertionError, match="wall clock"):
        quota_service.kst_day()
    with pytest.raises(AssertionError, match="wall clock"):  # the script without a clock reads the real one: the old defect, now loud
        script.main([], session_factory=lambda: contextlib.nullcontext(db))
    assert quota_service.kst_day(datetime(2026, 11, 16, 15, 0, tzinfo=UTC)) == date(2026, 11, 17)


@pytest.mark.parametrize("batch", ["0", "-1", "many"])
def test_the_script_refuses_a_bad_batch(script, batch):
    with pytest.raises(SystemExit) as stop:
        script.main(["--batch", batch], session_factory=lambda: contextlib.nullcontext(None))
    assert stop.value.code == 2


def test_the_script_default_batch_and_documentation():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "default=500" in source and "--dry-run" in source and "--batch" in source
    assert "do not say that deleted-after-30-days happens automatically" in source  # the scheduler requirement is stated in the script
    assert settings.INTERVIEW_LAZY_PURGE_BATCH == 50  # what a create removes besides the seeker's own


# ── What the documentation may say ──


def test_the_documentation_states_the_scheduler_requirement_and_claims_no_automatic_deletion():
    import re

    doc = (Path(__file__).resolve().parents[2] / "PROJECT_DOCUMENTATION.md").read_text(encoding="utf-8")
    assert "Nothing in the app or Compose runs it on a schedule" in doc and "purge_interviews.py" in doc
    assert "Until it does, expired data is hidden, but not all of it is deleted" in doc
    claim = re.compile(r"automatic\w*\s+(?:\w+\s+){0,3}(?:delet|purg|remov)|(?:delet|purg|remov)\w*\s+(?:\w+\s+){0,3}automatic", re.IGNORECASE)
    assert claim.search(doc) is None, claim.search(doc)


def test_an_expired_session_stays_hidden_even_when_the_purge_fails(db, world, clock, monkeypatch):
    """Hiding does not depend on deleting: the read paths filter on `expires_at` themselves."""
    from app.core.errors import AppError

    expired = add(db, world, clock, S.COMPLETED, expires_in=-1)
    fresh = add(db, world, clock, S.COMPLETED, expires_in=86400)
    monkeypatch.setattr(svc, "purge_expired", Boom())
    assert [i.id for i in svc.history(db, world.user, clock=clock).items] == [fresh]
    assert [i.id for i in svc.history(db, world.user, job_id=world.job_id, clock=clock).items] == [fresh]
    with pytest.raises(AppError):
        svc.detail(db, world.user, expired, clock=clock)
    assert count(db) == 2  # and the failed purge deleted nothing
