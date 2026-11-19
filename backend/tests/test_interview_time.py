"""The time strategy of the practice interview (M4 S2): UTC everywhere, SQLite's naive datetimes, and `derive`, the one answer
to "what is this session now" (joinable, accepting_turns, end_grace_open, and the stale overlay)."""
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models.interview import InterviewStatus as S
from app.services.interview_time import as_utc, derive, now_from, utcnow

KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
GRACE = 30


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


# ── UTC ──


def test_as_utc_takes_a_naive_value_as_utc_and_converts_an_aware_one():
    assert as_utc(None) is None
    assert as_utc(datetime(2026, 11, 16, 3, 0)) == T0  # what SQLite returns for a timezone-aware column
    assert as_utc(datetime(2026, 11, 16, 3, 0)).tzinfo is UTC
    assert as_utc(T0) == T0
    kst = datetime(2026, 11, 16, 12, 0, tzinfo=KST)
    assert as_utc(kst) == T0 and as_utc(kst).utcoffset() == timedelta(0)


def test_a_clock_must_return_an_aware_time_and_is_normalized_to_utc():
    assert now_from(lambda: datetime(2026, 11, 16, 12, 0, tzinfo=KST)) == T0
    assert now_from(lambda: datetime(2026, 11, 16, 12, 0, tzinfo=KST)).tzinfo == UTC
    with pytest.raises(ValueError):
        now_from(lambda: datetime(2026, 11, 16, 3, 0))
    assert utcnow().tzinfo is UTC


# ── derive: the statuses at their deadlines ──

# (status, deadline offset from T0, now offset) -> (status, reason, joinable, accepting_turns, end_grace_open, stale)
CASES = [
    # planning: the lease
    (S.PLANNING, 120, 0, (S.PLANNING, None, False, False, False, False)),
    (S.PLANNING, 120, 120, (S.PLANNING, None, False, False, False, False)),  # on the deadline it is still valid
    (S.PLANNING, 120, 121, (S.ABORTED, "planning_lost", False, False, False, True)),
    # created: the join deadline
    (S.CREATED, 300, 0, (S.CREATED, None, True, True, False, False)),
    (S.CREATED, 300, 300, (S.CREATED, None, True, True, False, False)),
    (S.CREATED, 300, 301, (S.ABORTED, "not_joined", False, False, False, True)),
    # live: 600 seconds, then 30 seconds for the end event only
    (S.LIVE, 600, 599, (S.LIVE, None, False, True, False, False)),
    (S.LIVE, 600, 600, (S.LIVE, None, False, True, False, False)),  # candidate answers are still accepted on the deadline
    (S.LIVE, 600, 601, (S.LIVE, None, False, False, True, False)),  # not after it: only the end event and the closing line
    (S.LIVE, 600, 630, (S.LIVE, None, False, False, True, False)),
    (S.LIVE, 600, 631, (S.ABORTED, "stale_live", False, False, False, True)),
]


@pytest.mark.parametrize("status, deadline, now, expected", CASES)
@pytest.mark.parametrize("naive", [False, True], ids=["aware", "sqlite-naive"])
def test_derive_at_the_deadlines(status, deadline, now, expected, naive):
    stored = at(deadline).replace(tzinfo=None) if naive else at(deadline)  # SQLite hands back naive values
    eff = derive(status, None, None, stored, at(now), GRACE)
    assert (eff.status, eff.end_reason, eff.joinable, eff.accepting_turns, eff.end_grace_open, eff.stale) == expected
    if eff.stale:
        assert eff.ended_at == at(deadline) and eff.active_until is None  # the deadline it missed, not the time it was noticed
    elif status in S.ACTIVE:
        assert eff.active_until == at(deadline)
    assert eff.active_until is None or eff.active_until.tzinfo is not None  # always aware on the way out


@pytest.mark.parametrize("status", [S.COMPLETED, S.ABORTED])
def test_a_finished_session_is_what_it_says_whatever_the_time(status):
    ended = at(50)
    for now in (0, 1_000_000):
        eff = derive(status, "seeker_ended", ended, None, at(now), GRACE)
        assert (eff.status, eff.end_reason, eff.ended_at, eff.active_until) == (status, "seeker_ended", ended, None)
        assert not (eff.joinable or eff.accepting_turns or eff.end_grace_open or eff.stale)


@pytest.mark.parametrize("status, reason", [(S.PLANNING, "planning_lost"), (S.CREATED, "not_joined"), (S.LIVE, "stale_live")])
def test_an_active_row_without_a_deadline_is_stale(status, reason):
    eff = derive(status, None, None, None, at(0), GRACE)
    assert (eff.status, eff.end_reason, eff.stale) == (S.ABORTED, reason, True)


def test_the_flags_agree_with_each_other_at_every_moment():
    """joinable implies accepting_turns, the end grace never accepts turns, a stale session is aborted and nothing else,
    and at most one way of being open is true at a time."""
    for status, deadline in ((S.PLANNING, 120), (S.CREATED, 300), (S.LIVE, 600)):
        for now in range(-5, 700, 7):
            eff = derive(status, None, None, at(deadline), at(now), GRACE)
            assert not eff.joinable or eff.accepting_turns
            assert not eff.end_grace_open or not eff.accepting_turns
            assert not eff.stale or (eff.status == S.ABORTED and not (eff.joinable or eff.accepting_turns or eff.end_grace_open))
            assert not eff.joinable or status == S.CREATED
            assert not eff.end_grace_open or status == S.LIVE
            assert sum([eff.joinable, eff.accepting_turns and not eff.joinable, eff.end_grace_open]) <= 1


def test_the_grace_follows_the_setting_given():
    assert derive(S.LIVE, None, None, at(600), at(640), 60).end_grace_open is True
    assert derive(S.LIVE, None, None, at(600), at(640), 5).stale is True
