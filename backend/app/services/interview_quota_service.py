"""The daily quota ledger of the practice interview (docs/DECISIONS.md D57).

Three independent limits per seeker per KST day: session reservations, planning model attempts and feedback model attempts
(`Settings.INTERVIEW_DAILY_*`). Each lives in one row of `interview_quota`, keyed by (seeker, KST day, kind).

`claim` takes one reservation and says whether there was one left. Why no request can take more than the limit:

1. The database keeps `used` within `quota_limit` (`ck_interview_quota_used`), whatever the code does.
2. The only increment is one conditional UPDATE (`... WHERE used < quota_limit`). PostgreSQL locks the row, and a concurrent
   UPDATE that waited re-checks the condition against the committed row; SQLite has one writer at a time.
3. The row is created once: the primary key makes a concurrent creation fail for the loser, who then updates the winner's row.
4. There is no way to give a reservation back: no decrement, no delete, no reset, and no foreign key to a session.
5. The caller commits `claim` together with whatever the reservation is for, before any model call. A request that
   is refused and rolled back takes nothing; one that committed keeps its reservation whatever happens next.

`claim` neither commits nor rolls back the caller's transaction; it uses a savepoint only to create a missing row. It assumes
the default READ COMMITTED isolation of PostgreSQL. The time is injected (`now`), so a test can cross midnight.
"""
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.interview import InterviewQuota, QuotaKind

KST = timezone(timedelta(hours=9))  # no daylight saving in Korea
MAX_LIMIT = 32767  # the column is a SMALLINT

_LIMIT_SETTING = {
    QuotaKind.SESSION: "INTERVIEW_DAILY_SESSIONS",
    QuotaKind.PLAN_MODEL: "INTERVIEW_DAILY_PLAN_MODEL_CALLS",
    QuotaKind.FEEDBACK_MODEL: "INTERVIEW_DAILY_FEEDBACK_MODEL_CALLS",
}
_QUOTA = InterviewQuota.__table__


def limit_for(kind: str) -> int:
    """The daily limit of a kind, read from the settings now (a row keeps the limit it was created with)."""
    name = _LIMIT_SETTING.get(kind)
    if name is None:
        raise ValueError(f"unknown quota kind {kind!r}; expected one of {', '.join(QuotaKind.ALL)}")
    value = getattr(settings, name)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_LIMIT:
        raise ValueError(f"{name} must be an integer from 0 to {MAX_LIMIT}")
    return value


def kst_day(now: datetime | None = None) -> date:
    """The KST calendar day of `now` (an aware datetime; default: the current time)."""
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return moment.astimezone(KST).date()


def used(db: Session, seeker_id: int, kind: str, *, now: datetime | None = None) -> int:
    """Reservations taken today (KST) in this kind; 0 when there is no row yet."""
    _check(seeker_id, kind)
    return db.scalar(_used_of(seeker_id, kst_day(now), kind)) or 0


def claim(db: Session, seeker_id: int, kind: str, *, now: datetime | None = None) -> bool:
    """Take one reservation of today's quota (KST) in `kind`. True: taken, in the caller's transaction. False: none left.

    Raises ValueError for an unknown kind or a naive `now`, and lets every database error through, except the one that
    means another request created today's row first.
    """
    _check(seeker_id, kind)
    cap = limit_for(kind)
    day = kst_day(now)
    if _increment(db, seeker_id, day, kind):
        return True
    if _exists(db, seeker_id, day, kind):
        return False  # the row is there and used == quota_limit
    _create(db, seeker_id, day, kind, cap)
    return _increment(db, seeker_id, day, kind)


def _check(seeker_id: int, kind: str) -> None:
    if isinstance(seeker_id, bool) or not isinstance(seeker_id, int):
        raise TypeError("seeker_id must be an int")
    if kind not in _LIMIT_SETTING:
        raise ValueError(f"unknown quota kind {kind!r}; expected one of {', '.join(QuotaKind.ALL)}")


def _used_of(seeker_id: int, day: date, kind: str):
    return select(_QUOTA.c.used).where(_QUOTA.c.seeker_id == seeker_id, _QUOTA.c.kst_day == day, _QUOTA.c.kind == kind)


def _exists(db: Session, seeker_id: int, day: date, kind: str) -> bool:
    return db.scalar(_used_of(seeker_id, day, kind)) is not None


def _increment(db: Session, seeker_id: int, day: date, kind: str) -> bool:
    """The one increment: it takes a reservation only while `used < quota_limit`, in one statement."""
    result = db.execute(
        update(_QUOTA)
        .where(_QUOTA.c.seeker_id == seeker_id, _QUOTA.c.kst_day == day, _QUOTA.c.kind == kind, _QUOTA.c.used < _QUOTA.c.quota_limit)
        .values(used=_QUOTA.c.used + 1)
    )
    return result.rowcount == 1


def _create(db: Session, seeker_id: int, day: date, kind: str, cap: int) -> None:
    """Create today's row with the limit now in force. If a concurrent request created it first the insert fails on the
    primary key, and that is fine; any other database error (a missing seeker, a bad value) is not hidden."""
    try:
        with db.begin_nested():
            db.execute(insert(_QUOTA).values(seeker_id=seeker_id, kst_day=day, kind=kind, used=0, quota_limit=cap))
    except IntegrityError:
        if not _exists(db, seeker_id, day, kind):
            raise
