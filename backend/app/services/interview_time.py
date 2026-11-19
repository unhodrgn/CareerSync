"""Time of the practice interview: one UTC strategy, and the one function that derives what a session is right now
(docs/DECISIONS.md D53, D57).

Everything is written to the database as an aware UTC datetime. SQLite hands a timezone-aware column back as a naive
datetime (PostgreSQL keeps the zone), so every value read from the database goes through `as_utc` before Python compares it.
A clock is a function returning an aware datetime, so a test can move time; `_now` normalizes whatever it returns.

`derive` is the single answer to "what is this session now" for every read path: detail and history show its result instead
of changing the row, create, end and the purge script settle the row to the same result (`interview_service.settle`), and
the ingest of turns (a later stage) asks it before accepting one. The deadline of each status (`active_until`):

- planning: the planning lease. Past it, the session is lost (`planning_lost`).
- created: the join deadline. Past it, nobody joined (`not_joined`).
- live: the end of the time budget. Candidate answers are accepted up to it and not after. For a further grace period only
  the final end event and the closing agent line are accepted (`end_grace_open`). Past that, the session went stale
  (`stale_live`).

A stale session is `aborted` for every reader, with the deadline as `ended_at`. The deadline belongs to the status it was
written for, so an overlay never moves a session between non-final statuses.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.interview import InterviewStatus

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """An aware UTC datetime. A naive one (SQLite) is taken to be UTC, which is how every value is written."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def now_from(clock: Clock) -> datetime:
    """The clock's time as an aware UTC datetime. A clock that returns a naive time is a bug, not a guess."""
    moment = clock()
    if moment.tzinfo is None:
        raise ValueError("a clock must return an aware datetime")
    return moment.astimezone(UTC)


@dataclass(frozen=True)
class Effective:
    """What a session is at `now`, whatever its row still says."""

    status: str
    end_reason: str | None
    ended_at: datetime | None  # for a stale session: the deadline it missed
    active_until: datetime | None  # None once aborted or completed
    joinable: bool  # created, and the join deadline has not passed
    accepting_turns: bool  # a turn of the interview is accepted now: joinable (the first turn starts it), or live within its budget
    end_grace_open: bool  # live, past the time budget, within the grace: only the final end event and the closing line
    stale: bool  # the row is past its deadline, so create, end or the purge script will settle it to `aborted`


def derive(
    status: str,
    end_reason: str | None,
    ended_at: datetime | None,
    active_until: datetime | None,
    now: datetime,
    grace_seconds: int,
) -> Effective:
    deadline = as_utc(active_until)
    now = as_utc(now)
    grace = timedelta(seconds=grace_seconds)
    stale_reason: str | None = None
    if status == InterviewStatus.PLANNING and (deadline is None or deadline < now):
        stale_reason = "planning_lost"
    elif status == InterviewStatus.CREATED and (deadline is None or deadline < now):
        stale_reason = "not_joined"
    elif status == InterviewStatus.LIVE and (deadline is None or deadline + grace < now):
        stale_reason = "stale_live"
    if stale_reason is not None:
        return Effective(InterviewStatus.ABORTED, stale_reason, deadline or now, None, False, False, False, True)
    joinable = status == InterviewStatus.CREATED
    live_open = status == InterviewStatus.LIVE and deadline >= now  # type: ignore[operator]
    grace_open = status == InterviewStatus.LIVE and not live_open
    return Effective(
        status,
        end_reason,
        as_utc(ended_at),
        deadline if status in InterviewStatus.ACTIVE else None,
        joinable,
        joinable or live_open,
        grace_open,
        False,
    )
