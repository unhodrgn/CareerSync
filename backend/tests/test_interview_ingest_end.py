"""The end of a practice interview (M4 S3a): the contract of `record_end`.

An end event is one final coverage snapshot and, only for a finished interview, the closing line. It is accepted for 30 seconds after
the time budget, for itself alone; the status change, the final coverage and the closing line are one transaction; and a retry is a
duplicate only if every part of the payload is the same. Interleavings are deterministic, on one SQLite connection: the logic, not
real parallelism (test_interview_ingest_concurrency.py, PostgreSQL only, is for that)."""
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from app.core.errors import AppError
from app.models import InterviewQuota, InterviewSession, InterviewTurn
from app.models.interview import QuotaKind
from app.services import interview_ingest_service as ingest
from app.services import interview_quota_service as quota
from app.services import interview_service as svc

from .interview_fixtures import Agent, Clock, build_world, new_session, turn_rows
from .test_interview_ingest_turns import ANSWER, cov, ev, plan_of, rec, refuse, row, started

CLOSING_TEXT = "면접이 모두 끝났습니다. 수고하셨습니다."


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


def ready(db, sid, clock):
    """A live session with a question and an answer for the first item; the plan and the next sequence number."""
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)
    return plan, 3


def closing(plan, seq, text=CLOSING_TEXT, **overrides):
    """The engine's closing line: role agent, kind closing, an index past the last item, and no topic."""
    args = {"seq": seq, "role": "agent", "kind": "closing", "item_index": len(plan.items), "topic_id": None, "text": text, "method": "rules", "analysis": None, "masked_kinds": None, "coverage": None}
    args.update(overrides)
    return ingest.TurnEvent(**args)


def final(plan, phase="ended", reason="plan_exhausted", status=None, levels=None):
    return cov(plan, status, levels, phase, reason)


def end_ev(plan, seq=None, phase="ended", reason="plan_exhausted", status=None, levels=None, **closing_overrides):
    line = None if seq is None else closing(plan, seq, **closing_overrides)
    return ingest.EndEvent(final(plan, phase, reason, status, levels), line)


def end(db, sid, event, clock):
    return ingest.record_end(db, sid, event, clock=clock)


def refuse_end(db, sid, event, clock, http, code, **extra):
    with pytest.raises(AppError) as error:
        end(db, sid, event, clock)
    assert (error.value.status_code, error.value.code) == (http, code), error.value.extra
    for key, value in extra.items():
        assert error.value.extra[key] == value
    return error.value



def closings(db, sid):
    return [t for t in turn_rows(db, sid) if t.kind == "closing"]


def still_live(db, sid, turns):
    r = row(db, sid)
    assert (r.status, r.end_reason, r.ended_at) == ("live", None, None) and r.active_until is not None
    assert len(turn_rows(db, sid)) == turns and not closings(db, sid)


# ── A real interview ends ──


def test_an_interview_that_ran_out_of_questions_is_completed_with_its_closing_line(db, world, clock, sid):
    agent = Agent(db, sid, clock)
    agent.start()
    steps = 0
    while agent.engine.state.phase.value == "listening" and steps < 40:
        agent.answer("Java와 Spring Boot로 API를 개발했고 장애를 줄였습니다 테스트도 작성했고 팀과 소통했습니다", 20)
        steps += 1
    (last,) = agent.last[-1:]
    assert (last.outcome, last.status, last.end_reason) == ("ended", "completed", "plan_exhausted")
    r = row(db, sid)
    assert (r.status, r.end_reason, r.active_until) == ("completed", "plan_exhausted", None)
    assert r.ended_at.replace(tzinfo=None) == clock().replace(tzinfo=None)
    (line,) = closings(db, sid)
    assert (line.role, line.item_index, line.seq) == ("agent", len(agent.plan.items), len(turn_rows(db, sid)))  # the last turn, past the last item
    assert svc.detail(db, world.user, sid, clock=clock).status == "completed"


def test_an_interview_that_ran_out_of_time_ends_with_the_reason_time(db, clock, sid):
    agent = Agent(db, sid, clock)
    agent.start()
    agent.answer("Java와 Spring Boot로 API를 개발했습니다 장애 대응도 했습니다", 560)  # the engine stops asking in the last 45 seconds
    assert agent.engine.state.phase.value == "ended"
    r = row(db, sid)
    assert (r.status, r.end_reason) == ("completed", "time")
    (line,) = closings(db, sid)
    assert line.item_index < len(agent.plan.items)  # it wrapped up in the middle of an item: an index inside the plan, and still no topic


def test_a_candidate_who_leaves_ends_the_session_as_aborted_without_a_closing_line(db, clock, sid):
    agent = Agent(db, sid, clock)
    agent.start()
    agent.answer("Java와 Spring Boot로 API를 개발했습니다 장애 대응도 했습니다", 20)
    results = agent.abort("candidate_left")
    assert (results[-1].outcome, results[-1].status, results[-1].end_reason) == ("ended", "aborted", "candidate_left")
    assert (row(db, sid).status, row(db, sid).end_reason) == ("aborted", "candidate_left") and not closings(db, sid)


# ── The reason is one of a short list ──


@pytest.mark.parametrize("phase", ["ended", "aborted"])
@pytest.mark.parametrize(
    "given, stored",
    [
        ("plan_exhausted", "plan_exhausted"), ("time", "time"), ("candidate_left", "candidate_left"), ("empty_plan", "empty_plan"),
        ("session_closed:participant_removed", "session_closed"), ("Time", "time"), (" TIME ", "time"), ("plan_exhausted:extra", "plan_exhausted"),
        ("a free text reason", "agent_ended"), ("", "agent_ended"), (None, "agent_ended"), (123, "agent_ended"), ("x" * 500, "agent_ended"),
        ("김철수가 나갔습니다", "agent_ended"), (["time"], "agent_ended"),
    ],
)
def test_the_end_reason_is_normalized_never_stored_as_the_agent_wrote_it(db, clock, sid, phase, given, stored):
    plan, seq = ready(db, sid, clock)
    event = ingest.EndEvent(final(plan, phase, given), None)
    result = end(db, sid, event, clock)
    assert result.end_reason == stored and row(db, sid).end_reason == stored and row(db, sid).coverage["end_reason"] == stored


def test_the_normalizer_alone():
    assert ingest.normalize_end_reason("session_closed:x") == "session_closed"
    assert ingest.normalize_end_reason("anything else") == ingest.DEFAULT_END_REASON == "agent_ended"
    assert ingest.END_REASONS == {"plan_exhausted", "empty_plan", "time", "candidate_left", "session_closed", "agent_error", "agent_ended"}


# ── The closing line ──

BAD_CLOSING = [
    ("a candidate", lambda p, s: {"role": "candidate", "analysis": dict(ANSWER)}, "kind"),
    ("another kind", lambda p, s: {"kind": "question"}, "kind"),
    ("a coverage of its own", lambda p, s: {"coverage": cov(p)}, "coverage"),
    ("an analysis", lambda p, s: {"analysis": dict(ANSWER)}, "analysis"),
    ("a negative index", lambda p, s: {"item_index": -1}, "item_index"),
    ("an index two past the plan", lambda p, s: {"item_index": len(p.items) + 1}, "item_index"),
    ("an index that is a bool", lambda p, s: {"item_index": True}, "item_index"),
    ("another topic than the index has", lambda p, s: {"item_index": 0, "topic_id": p.items[1].topic_id}, "topic_id"),
    ("a topic past the plan", lambda p, s: {"topic_id": "c1"}, "topic_id"),
    ("an empty line", lambda p, s: {"text": " "}, "text"),
    ("a bad method", lambda p, s: {"method": "gpt"}, "method"),
]


@pytest.mark.parametrize("name, build, field", BAD_CLOSING, ids=[b[0] for b in BAD_CLOSING])
def test_a_bad_closing_line_refuses_the_whole_end_and_the_session_goes_on(db, clock, sid, name, build, field):
    plan, seq = ready(db, sid, clock)
    event = ingest.EndEvent(final(plan), closing(plan, seq, **build(plan, seq)))
    refuse_end(db, sid, event, clock, 422, "INTERVIEW_BAD_TURN", field=field)
    still_live(db, sid, 2)


def test_the_closing_line_may_name_no_topic_or_the_topic_at_its_index(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    assert end(db, sid, ingest.EndEvent(final(plan), closing(plan, seq, item_index=1, topic_id=plan.items[1].topic_id)), clock).outcome == "ended"
    assert closings(db, sid)[0].item_index == 1


def test_the_closing_line_of_a_wrap_in_the_middle_of_an_item_may_leave_the_topic_out(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    assert end(db, sid, ingest.EndEvent(final(plan), closing(plan, seq, item_index=0, topic_id=None)), clock).outcome == "ended"


def test_an_aborted_end_has_no_closing_line(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    refuse_end(db, sid, ingest.EndEvent(final(plan, "aborted", "candidate_left"), closing(plan, seq)), clock, 422, "INTERVIEW_BAD_TURN", field="closing")
    still_live(db, sid, 2)


def test_an_end_without_a_closing_line_is_valid(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    assert end(db, sid, ingest.EndEvent(final(plan), None), clock).status == "completed"
    assert not closings(db, sid)


def test_the_closing_line_is_masked_and_never_cut_or_oversized(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    refuse_end(db, sid, end_ev(plan, seq, text="가" * 4001), clock, 422, "INTERVIEW_TURN_TOO_LONG")
    refuse_end(db, sid, end_ev(plan, seq, text="가" * 8001), clock, 422, "INTERVIEW_TURN_TOO_LONG")
    still_live(db, sid, 2)
    end(db, sid, end_ev(plan, seq, text="연락은 kim@example.com 으로 드리겠습니다"), clock)
    assert closings(db, sid)[0].text == "연락은 [EMAIL] 으로 드리겠습니다"


def test_the_closing_line_follows_the_last_turn_exactly(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    refuse_end(db, sid, end_ev(plan, seq + 1), clock, 409, "INTERVIEW_SEQ_GAP", expected_seq=seq)
    refuse_end(db, sid, end_ev(plan, seq - 1), clock, 409, "INTERVIEW_SEQ_CONFLICT", seq=seq - 1)
    still_live(db, sid, 2)
    assert end(db, sid, end_ev(plan, seq), clock).outcome == "ended"


def test_the_closing_line_may_take_the_last_slot_of_the_120_and_no_more(db, clock, sid):
    plan = started(db, sid, clock)
    for number in range(2, 120):
        db.add(InterviewTurn(session_id=sid, seq=number, role="agent", kind="nudge", item_index=0, text="네"))
    db.commit()
    refuse_end(db, sid, end_ev(plan, 121), clock, 409, "INTERVIEW_TURN_LIMIT")
    assert end(db, sid, end_ev(plan, 120), clock).outcome == "ended"
    assert len(turn_rows(db, sid)) == 120 and closings(db, sid)[0].seq == 120


def test_the_closing_line_is_not_a_turn(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    refuse(db, sid, closing(plan, seq), clock, 422, "INTERVIEW_BAD_TURN", field="kind")  # it goes with the end event only


# ── Time: the grace is for the end event alone ──


def test_the_end_event_is_accepted_in_the_grace_with_its_closing_line_while_a_turn_is_not(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    clock.advance(600 + 30)  # the last second of the grace
    refuse(db, sid, ev(plan, seq, "candidate", "answer"), clock, 409, "INTERVIEW_NOT_ACTIVE", end_grace_open=True)
    assert end(db, sid, end_ev(plan, seq), clock).outcome == "ended"
    assert (row(db, sid).status, len(closings(db, sid))) == ("completed", 1)


def test_the_end_event_is_refused_once_the_grace_is_over(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    clock.advance(631)
    refuse_end(db, sid, end_ev(plan, seq), clock, 409, "INTERVIEW_NOT_ACTIVE", status="aborted")
    assert row(db, sid).status == "live"  # refusing does not settle
    svc.settle(db, None, clock())
    refuse_end(db, sid, end_ev(plan, seq), clock, 409, "INTERVIEW_ALREADY_ENDED")  # now it is over, as stale
    assert (row(db, sid).end_reason, len(closings(db, sid))) == ("stale_live", 0)


def test_the_end_event_before_the_deadline_is_accepted_too(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    clock.advance(100)
    assert end(db, sid, end_ev(plan, seq), clock).status == "completed"


@pytest.mark.parametrize("status", ["planning", "created"])
def test_only_a_live_session_can_be_ended_by_an_end_event(db, clock, sid, status):
    plan = plan_of(db, sid)
    if status == "planning":
        db.execute(update(InterviewSession).where(InterviewSession.id == sid).values(status="planning"))
        db.commit()
    refuse_end(db, sid, ingest.EndEvent(final(plan, "aborted", "candidate_left"), None), clock, 409, "INTERVIEW_NOT_ACTIVE")


def test_an_end_for_a_session_that_is_not_there(db, world, clock, sid):
    plan = plan_of(db, sid)
    refuse_end(db, 99999, ingest.EndEvent(final(plan), None), clock, 404, "INTERVIEW_NOT_FOUND")
    svc.delete(db, world.user, sid, clock=clock)
    refuse_end(db, sid, ingest.EndEvent(final(plan), None), clock, 404, "INTERVIEW_NOT_FOUND")


def test_an_end_is_checked_against_the_stored_plan(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    db.execute(update(InterviewSession).where(InterviewSession.id == sid).values(plan_sha256="0" * 64))
    db.commit()
    refuse_end(db, sid, end_ev(plan, seq), clock, 409, "INTERVIEW_PLAN_INVALID")


# ── The final snapshot ──


@pytest.mark.parametrize("phase", ["listening", "running", None, 5])
def test_the_final_snapshot_must_be_an_end_phase(db, clock, sid, phase):
    plan, seq = ready(db, sid, clock)
    refuse_end(db, sid, ingest.EndEvent({**final(plan), "phase": phase}, None), clock, 422, "INTERVIEW_BAD_COVERAGE", field="phase")
    still_live(db, sid, 2)


def test_the_final_snapshot_obeys_the_same_rules_as_every_other(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    refuse_end(db, sid, end_ev(plan, seq, status={"c1": "asked", "c2": "demonstrated"}), clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_transition")
    refuse_end(db, sid, end_ev(plan, seq, status={"c1": "skipped", "c2": "asked", "c3": "partial"}), clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_transition")
    still_live(db, sid, 2)  # no closing line, no status change
    assert end(db, sid, end_ev(plan, seq, status={"c1": "partial", "c2": "asked"}), clock).outcome == "ended"


def test_the_final_snapshot_is_stored_as_the_coverage_and_the_topics_follow_it(db, world, clock, sid):
    plan, seq = ready(db, sid, clock)
    p1 = plan.items[0].rubric[0].id
    end(db, sid, end_ev(plan, seq, status={"c1": "partial", "c2": "asked"}, levels={"c1": {p1: "partial"}}), clock)
    stored = row(db, sid).coverage
    assert stored["phase"] == "ended" and stored["status"]["c1"] == "partial" and stored["levels"] == {"c1": {p1: "partial"}}
    topics = {t.topic_id: t.status for t in svc.detail(db, world.user, sid, clock=clock).topics}
    assert topics["c1"] == "partial" and topics["c2"] == "asked" and topics["c3"] == "not_asked"


def test_an_end_event_of_the_wrong_type_is_refused(db, clock, sid):
    ready(db, sid, clock)
    refuse_end(db, sid, "not an event", clock, 422, "INTERVIEW_BAD_TURN", field="event")


# ── Idempotent, with an immutable payload ──


def test_the_same_end_again_is_a_duplicate_that_changes_nothing(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    event = end_ev(plan, seq, status={"c1": "partial"})
    first = end(db, sid, event, clock)
    before = (row(db, sid).ended_at, row(db, sid).coverage, [(t.id, t.seq, t.text) for t in turn_rows(db, sid)])
    clock.advance(5000)  # a retry long after, even past the grace
    again = end(db, sid, event, clock)
    assert (first.outcome, again.outcome, again.status, again.end_reason) == ("ended", "duplicate", "completed", "plan_exhausted")
    assert (row(db, sid).ended_at, row(db, sid).coverage, [(t.id, t.seq, t.text) for t in turn_rows(db, sid)]) == before
    assert len(closings(db, sid)) == 1


def test_an_aborted_end_is_idempotent_too(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    event = ingest.EndEvent(final(plan, "aborted", "candidate_left"), None)
    assert end(db, sid, event, clock).outcome == "ended" and end(db, sid, event, clock).outcome == "duplicate"


def test_a_retry_that_normalizes_to_the_same_reason_is_the_same_payload(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    end(db, sid, ingest.EndEvent(final(plan, "aborted", "session_closed:participant_removed"), None), clock)
    again = end(db, sid, ingest.EndEvent(final(plan, "aborted", "session_closed:another_detail"), None), clock)
    assert again.outcome == "duplicate" and again.end_reason == "session_closed"


@pytest.mark.parametrize(
    "different",
    [
        # each differs from the first end in one thing only: the status of the first was {"c1": "partial"}
        pytest.param(lambda p, s: end_ev(p, s, status={"c1": "partial"}, text="다른 마무리 인사입니다."), id="another closing text"),
        pytest.param(lambda p, s: end_ev(p, s, status={"c1": "partial"}, item_index=1), id="another closing index"),
        pytest.param(lambda p, s: end_ev(p, None, status={"c1": "partial"}), id="no closing line where there was one"),
        pytest.param(lambda p, s: end_ev(p, s, status={"c1": "partial"}, reason="time"), id="another reason"),
        pytest.param(lambda p, s: end_ev(p, s, status={"c1": "partial", "c2": "asked"}), id="another coverage"),
        pytest.param(lambda p, s: ingest.EndEvent(final(p, "aborted", "plan_exhausted"), None), id="another phase"),
    ],
)
def test_a_different_payload_for_a_session_that_is_over_is_refused_whole(db, clock, sid, different):
    plan, seq = ready(db, sid, clock)
    end(db, sid, end_ev(plan, seq, status={"c1": "partial"}), clock)
    before = (row(db, sid).status, row(db, sid).end_reason, row(db, sid).coverage, [(t.id, t.seq, t.text) for t in turn_rows(db, sid)])
    refuse_end(db, sid, different(plan, seq), clock, 409, "INTERVIEW_ALREADY_ENDED")
    assert (row(db, sid).status, row(db, sid).end_reason, row(db, sid).coverage, [(t.id, t.seq, t.text) for t in turn_rows(db, sid)]) == before


def test_an_end_without_a_closing_line_is_not_acknowledged_as_one_with_it(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    end(db, sid, ingest.EndEvent(final(plan), None), clock)
    refuse_end(db, sid, end_ev(plan, seq), clock, 409, "INTERVIEW_ALREADY_ENDED")  # never silently treated as the same
    assert not closings(db, sid)


def test_an_end_after_the_seeker_ended_the_session_is_refused_and_writes_nothing(db, world, clock, sid):
    plan, seq = ready(db, sid, clock)
    svc.end(db, world.user, sid, clock=clock)
    refuse_end(db, sid, end_ev(plan, seq), clock, 409, "INTERVIEW_ALREADY_ENDED", status="aborted")
    assert (row(db, sid).end_reason, len(closings(db, sid))) == ("seeker_ended", 0)


def test_the_seekers_end_after_the_agents_changes_nothing(db, world, clock, sid):
    plan, seq = ready(db, sid, clock)
    end(db, sid, end_ev(plan, seq), clock)
    view = svc.end(db, world.user, sid, clock=clock)
    assert (view.status, view.end_reason) == ("completed", "plan_exhausted")


# ── One transaction ──


def test_a_closing_line_that_cannot_be_stored_leaves_the_session_live_and_unchanged(db, clock, sid, monkeypatch):
    plan, seq = ready(db, sid, clock)
    before = row(db, sid).coverage
    real = ingest._insert_turn

    def boom(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("disk full"))

    monkeypatch.setattr(ingest, "_insert_turn", boom)
    with pytest.raises(OperationalError):
        end(db, sid, end_ev(plan, seq, status={"c1": "partial"}), clock)
    still_live(db, sid, 2)
    assert row(db, sid).coverage == before  # not the final coverage either
    monkeypatch.setattr(ingest, "_insert_turn", real)
    assert end(db, sid, end_ev(plan, seq, status={"c1": "partial"}), clock).outcome == "ended"  # and the event can be sent again


def test_the_end_does_not_touch_the_quota(db, world, clock, sid):
    plan, seq = ready(db, sid, clock)
    rows = lambda: sorted(tuple(r) for r in db.execute(select(InterviewQuota.kind, InterviewQuota.used, InterviewQuota.quota_limit)))  # noqa: E731
    before = rows()
    end(db, sid, end_ev(plan, seq), clock)
    assert rows() == before and quota.used(db, world.user.id, QuotaKind.SESSION, now=clock()) == 1


# ── Interleavings on one connection: the logic of the compare-and-set, not real parallelism ──


def test_the_seeker_ending_the_session_just_before_the_agents_end_wins_and_no_closing_line_is_written(db, world, clock, sid, monkeypatch):
    plan, seq = ready(db, sid, clock)
    real = ingest._clean_end

    def seeker_ends_after_the_checks(event, p, names):
        out = real(event, p, names)
        svc.end(db, world.user, sid, clock=clock)
        return out

    monkeypatch.setattr(ingest, "_clean_end", seeker_ends_after_the_checks)
    refuse_end(db, sid, end_ev(plan, seq), clock, 409, "INTERVIEW_ALREADY_ENDED")
    assert (row(db, sid).end_reason, len(closings(db, sid))) == ("seeker_ended", 0)


def test_two_identical_end_events_in_a_row_end_the_session_once(db, clock, sid, monkeypatch):
    plan, seq = ready(db, sid, clock)
    event = end_ev(plan, seq)
    real = ingest._clean_end
    results, busy = [], []

    def the_rival_ends_first(e, p, names):
        out = real(e, p, names)
        if not busy:
            busy.append(1)
            results.append(ingest.record_end(db, sid, event, clock=clock))  # the same event from another request, whole
        return out

    monkeypatch.setattr(ingest, "_clean_end", the_rival_ends_first)
    mine = end(db, sid, event, clock)
    assert (results[0].outcome, mine.outcome) == ("ended", "duplicate")
    assert len(closings(db, sid)) == 1 and row(db, sid).status == "completed"


def test_a_turn_stored_between_the_checks_and_the_end_makes_the_closing_line_conflict(db, clock, sid, monkeypatch):
    """The closing line's number was computed before a rival turn took it; under the guard's lock the end sees that and refuses."""
    plan, seq = ready(db, sid, clock)
    event = end_ev(plan, seq)
    real = ingest._clean_end

    def a_turn_arrives_first(e, p, names):
        out = real(e, p, names)
        rec(db, sid, ev(plan, seq, "agent", "follow_up"), clock)
        return out

    monkeypatch.setattr(ingest, "_clean_end", a_turn_arrives_first)
    refuse_end(db, sid, event, clock, 409, "INTERVIEW_SEQ_CONFLICT")
    assert row(db, sid).status == "live" and not closings(db, sid)
    monkeypatch.setattr(ingest, "_clean_end", real)
    assert end(db, sid, end_ev(plan, seq + 1), clock).outcome == "ended"  # the agent resends with the right number


def test_an_end_stored_between_the_checks_and_a_turn_refuses_the_turn(db, clock, sid, monkeypatch):
    plan, seq = ready(db, sid, clock)
    real = ingest._is_duplicate

    busy = []

    def the_end_arrives_first(session, session_id, turn):
        out = real(session, session_id, turn)
        if not busy:
            busy.append(1)
            ingest.record_end(session, session_id, ingest.EndEvent(final(plan), None), clock=clock)
        return out

    monkeypatch.setattr(ingest, "_is_duplicate", the_end_arrives_first)
    refuse(db, sid, ev(plan, seq, "agent", "follow_up"), clock, 409, "INTERVIEW_NOT_ACTIVE", status="completed")
    assert [t.seq for t in turn_rows(db, sid)] == [1, 2] and row(db, sid).status == "completed"  # no turn after the end


def test_a_settlement_between_the_checks_and_the_end_refuses_it_cleanly(db, clock, sid, monkeypatch):
    plan, seq = ready(db, sid, clock)
    real = ingest._clean_end

    def time_runs_out(event, p, names):
        out = real(event, p, names)
        clock.advance(700)
        svc.settle(db, None, clock())
        return out

    monkeypatch.setattr(ingest, "_clean_end", time_runs_out)
    refuse_end(db, sid, end_ev(plan, seq), clock, 409, "INTERVIEW_ALREADY_ENDED")
    assert (row(db, sid).end_reason, len(closings(db, sid))) == ("stale_live", 0)


def test_no_turn_row_is_ever_written_after_the_status_change(db, clock, sid):
    plan, seq = ready(db, sid, clock)
    end(db, sid, end_ev(plan, seq), clock)
    for event in (ev(plan, seq + 1, "agent", "nudge"), ev(plan, seq + 1, "candidate", "answer")):
        refuse(db, sid, event, clock, 409, "INTERVIEW_NOT_ACTIVE", status="completed")
    assert db.scalar(select(func.count()).select_from(InterviewTurn).where(InterviewTurn.session_id == sid)) == 3
