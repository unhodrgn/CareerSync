"""Real parallel requests against the internal agent API (M5 S1; docs/DECISIONS.md D80): PostgreSQL only.

These need `TEST_DATABASE_URL=postgresql+psycopg://…` (a throwaway database: the fixture drops every table) and are SKIPPED without it.
Each request gets its own database session, as in production, and the threads are released together. The ingestion service's own races
are covered by test_interview_ingest_concurrency.py; these show that the HTTP layer keeps them: the same event posted twice at once is
stored once, and an event racing the seeker's delete is either stored before the delete or refused with a 404, never left behind."""
import os
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.v1.interview_sessions import get_clock
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import InterviewSession

from .conftest import auth
from .interview_fixtures import Agent, Clock, build_world, new_session, turn_rows
from .test_interview_internal_api import SECRET, event, turn_body

PG = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"), reason="needs TEST_DATABASE_URL on PostgreSQL")


@pytest.fixture
def parallel_api(db, monkeypatch):
    """A client whose every request opens its own session on the test database, like the real `get_db`."""
    monkeypatch.setattr(settings, "INTERVIEW_AGENT_SECRET", SECRET)
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    clock = Clock()

    def own_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = own_session
    app.dependency_overrides[get_clock] = lambda: clock
    yield TestClient(app, raise_server_exceptions=False), clock
    app.dependency_overrides.clear()


def together(*calls):
    barrier = threading.Barrier(len(calls))
    results = [None] * len(calls)

    def run(index):
        barrier.wait(30)
        results[index] = calls[index]()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)
    return results


@PG
def test_the_same_event_posted_twice_at_once_is_stored_once(db, parallel_api):
    api, clock = parallel_api
    sid = new_session(db, build_world(db), clock)
    agent = Agent(db, sid, clock)
    agent.engine.start()
    body = turn_body(agent.turn_events()[0])
    first, second = together(lambda: event(api, sid, body), lambda: event(api, sid, body))
    assert {first.status_code, second.status_code} == {200}
    assert sorted(r.json()["outcome"] for r in (first, second)) == ["duplicate", "stored"]
    assert len(turn_rows(db, sid)) == 1


@PG
def test_an_event_racing_the_seekers_delete_leaves_nothing_behind(db, parallel_api):
    api, clock = parallel_api
    world = build_world(db)
    sid = new_session(db, world, clock)
    agent = Agent(db, sid, clock)
    agent.engine.start()
    body = turn_body(agent.turn_events()[0])
    posted, deleted = together(lambda: event(api, sid, body), lambda: api.delete(f"/api/interview-sessions/{sid}", headers=auth(world.user)))
    assert deleted.status_code == 204 and posted.status_code in (200, 404)
    db.rollback()
    assert db.get(InterviewSession, sid) is None and turn_rows(db, sid) == []
