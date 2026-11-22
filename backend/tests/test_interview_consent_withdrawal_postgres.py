"""A turn racing the withdrawal of the AI consent (M5 S3; docs/DECISIONS.md D81): PostgreSQL only.

These need `TEST_DATABASE_URL=postgresql+psycopg://…` (a throwaway database: the fixture drops every table) and are SKIPPED without it.
The withdrawal and the agent's turn run in two threads with a session each, released together. Whichever wins, the end state is one
consistent thing: the session is `aborted` with the reason `consent_withdrawn`, the consent is withdrawn, and a turn is either stored
before that or refused with `INTERVIEW_NOT_ACTIVE`, never stored after it. The SQLite tests of D81 show the logic; only these show it
under real parallel requests, and only when they run."""
import pytest

from app.models import User
from app.services import consent_service
from app.services import interview_ingest_service as ingest

from .interview_fixtures import Clock, build_world, new_session
from .test_interview_ingest_concurrency import PG, attempt, parallel, state
from .test_interview_ingest_turns import cov, ev, started


@PG
@pytest.mark.parametrize("round_", range(5))
def test_pg_a_turn_racing_the_withdrawal_leaves_one_consistent_state(db, round_):
    clock = Clock()
    world = build_world(db)
    sid = new_session(db, world, clock)
    plan = started(db, sid, clock)
    event = ev(plan, 2, "candidate", "answer", coverage=cov(plan, {"c1": "partial"}))
    user_id = world.user.id

    def work(session, index):
        if index == 0:
            return attempt(lambda: ingest.record_turn(session, sid, event, clock=clock))
        consent_service.withdraw_ai(session, session.get(User, user_id), now=clock.now)
        return ("withdrawn", "")

    turn, withdrawn = parallel(db, 2, work)
    row, turns = state(db, sid)
    assert withdrawn == ("withdrawn", "")
    assert (row.status, row.end_reason, row.active_until) == ("aborted", "consent_withdrawn", None)
    db.expire_all()
    assert db.get(User, user_id).consent_ai_at is None
    if turn == ("stored", ""):
        assert [t.seq for t in turns] == [1, 2]  # it won the race: stored, then the session ended
    else:
        assert turn == ("refused", "INTERVIEW_NOT_ACTIVE") and [t.seq for t in turns] == [1]
