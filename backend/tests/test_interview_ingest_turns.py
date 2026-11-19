"""Ingestion of a practice interview's turns (M4 S3a): the contract of `record_turn`.

A real `InterviewEngine` plays the Interview Agent (`Agent` in interview_fixtures.py), so the backend is shown to accept exactly what
the engine emits; the rest feeds it hostile and broken events. Concurrency is exercised here only as deterministic interleavings
on one SQLite connection (a patched step runs another request at the exact point); that shows the logic and proves nothing about real
parallel requests, which test_interview_ingest_concurrency.py covers on PostgreSQL only."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from ai.interview import InterviewPlan, coverage_snapshot
from app.core.config import settings
from app.core.errors import AppError
from app.models import InterviewSession, InterviewTurn, User
from app.services import interview_ingest_service as ingest
from app.services import interview_service as svc
from app.services.interview_plan_service import plan_digest

from .interview_fixtures import Agent, Clock, build_world, new_session, turn_rows

ANSWER = {"answer_type": "answered", "points": {}, "quotes": [], "method": "rules"}


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def world(db):
    return build_world(db)


@pytest.fixture
def sid(db, world, clock):
    return new_session(db, world, clock)


def plan_of(db, session_id):
    return InterviewPlan.from_dict(db.get(InterviewSession, session_id).plan)


def cov(plan, status=None, levels=None, phase="listening", end_reason=None):
    topics = [i.topic_id for i in plan.items]
    base = {t: "not_asked" for t in topics}
    base[topics[0]] = "asked"
    base.update(status or {})
    return {"phase": phase, "end_reason": end_reason, "status": base, "levels": levels or {}}


def ev(plan, seq=1, role="agent", kind="question", index=0, **overrides):
    topic = plan.items[index].topic_id if index is not None and 0 <= index < len(plan.items) else None
    args = {
        "seq": seq, "role": role, "kind": kind, "item_index": index, "topic_id": topic,
        "text": "질문입니다." if role == "agent" else "저는 Java로 API를 개발했습니다.",
        "method": "rules", "analysis": None if role == "agent" else dict(ANSWER), "masked_kinds": None, "coverage": cov(plan),
    }
    args.update(overrides)
    return ingest.TurnEvent(**args)


def rec(db, session_id, event, clock):
    return ingest.record_turn(db, session_id, event, clock=clock)


def refuse(db, session_id, event, clock, http, code, **extra):
    with pytest.raises(AppError) as error:
        rec(db, session_id, event, clock)
    assert (error.value.status_code, error.value.code) == (http, code), error.value.extra
    for key, value in extra.items():
        assert error.value.extra[key] == value
    return error.value


def row(db, session_id):
    db.expire_all()
    return db.get(InterviewSession, session_id)


def started(db, session_id, clock):
    """The session after its first turn, and the plan."""
    plan = plan_of(db, session_id)
    rec(db, session_id, ev(plan), clock)
    return plan


def unchanged(db, session_id, *, status="created", turns=0):
    r = row(db, session_id)
    assert (r.status, r.coverage if turns == 0 else r.coverage is not None, len(turn_rows(db, session_id))) == (status, None if turns == 0 else True, turns)


# ── What a real interview does ──


def test_a_real_interview_is_stored_exactly_as_the_engine_said_it(db, world, clock, sid):
    agent = Agent(db, sid, clock, names=[world.user.display_name])
    agent.start()
    answers = [
        "Java와 Spring Boot로 주문 API를 개발했고 트랜잭션 경계를 정리해서 장애를 줄였습니다 테스트도 작성했습니다",
        "Spring Boot 설정과 JPA 사용 경험이 있고 성능 문제를 해결했습니다 모니터링도 구축했습니다",
        "팀 협업에서는 코드 리뷰와 문서화로 소통하며 갈등을 조정했습니다 일정도 맞추었습니다",
        "지원 동기는 백엔드 개발자로 성장하고 싶어서입니다 그리고 사용자에게 도움이 되는 서비스를 만들고 싶습니다",
    ]
    steps = 0
    while agent.engine.state.phase.value == "listening" and steps < 40:
        agent.answer(answers[steps % len(answers)], 25)
        steps += 1
    assert agent.engine.state.phase.value == "ended"
    r = row(db, sid)
    assert (r.status, r.end_reason) == ("completed", "plan_exhausted")
    engine_turns = agent.engine.state.turns
    stored = turn_rows(db, sid)
    assert [(t.seq, t.role, t.kind, t.item_index, t.text) for t in stored] == [(t.seq, t.role, t.kind, t.item_index, t.text) for t in engine_turns]
    assert all((t.analysis is None) == (t.role == "agent") for t in stored)
    assert r.coverage == coverage_snapshot(agent.engine.state)  # exactly the engine's final snapshot, phase "ended"
    assert r.coverage["phase"] == "ended" and r.coverage["end_reason"] == "plan_exhausted"
    view = svc.detail(db, world.user, sid, clock=clock)
    assert view.status == "completed" and len(view.turns) == len(engine_turns) and {t.status for t in view.topics} <= {"demonstrated", "partial", "not_shown", "asked", "skipped"}


def test_the_first_turn_starts_the_session_and_sets_its_time_budget(db, world, clock, sid):
    plan = plan_of(db, sid)
    result = rec(db, sid, ev(plan), clock)
    assert (result.outcome, result.seq, result.started, result.dropped_quotes) == ("stored", 1, True, 0)
    r = row(db, sid)
    assert (r.status, r.started_at.replace(tzinfo=None), r.active_until.replace(tzinfo=None)) == ("live", clock().replace(tzinfo=None), (clock() + timedelta(seconds=600)).replace(tzinfo=None))
    assert r.coverage == cov(plan)
    second = rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)
    assert (second.outcome, second.started) == ("stored", False)
    assert row(db, sid).started_at == r.started_at  # the start is set once


@pytest.mark.parametrize("seq, index", [(2, 0), (1, 1)])
def test_a_session_starts_with_the_engines_first_question_and_nothing_else(db, clock, sid, seq, index):
    plan = plan_of(db, sid)
    refuse(db, sid, ev(plan, seq, index=index), clock, 422, "INTERVIEW_BAD_TURN", field="first_turn")
    refuse(db, sid, ev(plan, 1, "candidate", "answer"), clock, 422, "INTERVIEW_BAD_TURN", field="first_turn")
    refuse(db, sid, ev(plan, 1, kind="nudge"), clock, 422, "INTERVIEW_BAD_TURN", field="first_turn")
    unchanged(db, sid)


# ── Strict validation: nothing is written for a bad event ──

BAD = [
    ("event of another type", lambda p: None, "event"),
    ("seq zero", lambda p: {"seq": 0}, "seq"),
    ("seq negative", lambda p: {"seq": -1}, "seq"),
    ("seq a bool", lambda p: {"seq": True}, "seq"),
    ("seq a string", lambda p: {"seq": "1"}, "seq"),
    ("unknown role", lambda p: {"role": "interviewer"}, "kind"),
    ("unknown kind", lambda p: {"kind": "monologue"}, "kind"),
    ("the closing line is not a turn", lambda p: {"kind": "closing"}, "kind"),
    ("a candidate speaks an agent kind", lambda p: {"role": "candidate", "kind": "question", "analysis": dict(ANSWER)}, "kind"),
    ("the agent speaks an answer", lambda p: {"kind": "answer"}, "kind"),
    ("no item index", lambda p: {"item_index": None, "topic_id": None}, "item_index"),
    ("a negative item index", lambda p: {"item_index": -1, "topic_id": None}, "item_index"),
    ("an item index past the plan", lambda p: {"item_index": len(p.items), "topic_id": None}, "item_index"),
    ("an item index that is a bool", lambda p: {"item_index": True, "topic_id": p.items[1].topic_id}, "item_index"),
    ("the wrong topic echo", lambda p: {"topic_id": p.items[1].topic_id}, "topic_id"),
    ("no topic echo", lambda p: {"topic_id": None}, "topic_id"),
    ("an unknown topic echo", lambda p: {"topic_id": "c99"}, "topic_id"),
    ("text of another type", lambda p: {"text": 5}, "text"),
    ("an empty line of the interviewer", lambda p: {"text": "   "}, "text"),
    ("an unknown method", lambda p: {"method": "gpt"}, "method"),
    ("masked kinds that are not a mapping", lambda p: {"masked_kinds": ["email"]}, "masked_kinds"),
    ("a masked kind with a bad name", lambda p: {"masked_kinds": {"E-mail!": 1}}, "masked_kinds"),
    ("a negative masked count", lambda p: {"masked_kinds": {"email": -1}}, "masked_kinds"),
    ("a masked count that is a bool", lambda p: {"masked_kinds": {"email": True}}, "masked_kinds"),
    ("an enormous masked count", lambda p: {"masked_kinds": {"email": 10**6}}, "masked_kinds"),
    ("too many masked kinds", lambda p: {"masked_kinds": {f"k{chr(97 + i)}": 1 for i in range(11)}}, "masked_kinds"),
    ("the agent has an analysis", lambda p: {"analysis": dict(ANSWER)}, "analysis"),
]


@pytest.mark.parametrize("name, build, field", BAD, ids=[b[0] for b in BAD])
def test_a_bad_turn_is_refused_whole_and_nothing_is_written(db, clock, sid, name, build, field):
    plan = plan_of(db, sid)
    overrides = build(plan)
    event = "not an event" if overrides is None else ev(plan, **overrides)
    refuse(db, sid, event, clock, 422, "INTERVIEW_BAD_TURN", field=field)
    unchanged(db, sid)


BAD_ANALYSIS = [
    ("none", lambda p: None),
    ("not a mapping", lambda p: ["answered"]),
    ("a key missing", lambda p: {"answer_type": "answered", "points": {}, "quotes": []}),
    ("a key extra", lambda p: {**ANSWER, "suggested_follow_up": "더 말씀해 주세요"}),
    ("an unknown answer type", lambda p: {**ANSWER, "answer_type": "brilliant"}),
    ("an unknown method", lambda p: {**ANSWER, "method": "gpt"}),
    ("points that are not a mapping", lambda p: {**ANSWER, "points": ["p1"]}),
    ("a point of no rubric", lambda p: {**ANSWER, "points": {"p99": "demonstrated"}}),
    ("a point of another topic's rubric only", lambda p: {**ANSWER, "points": {"x1": "demonstrated"}}),
    ("an unknown level", lambda p: {**ANSWER, "points": {"p1": "excellent"}}),
    ("quotes that are not a list", lambda p: {**ANSWER, "quotes": "Java"}),
    ("a quote that is not a string", lambda p: {**ANSWER, "quotes": [5]}),
    ("too many quotes", lambda p: {**ANSWER, "quotes": ["Java"] * 11}),
    ("an enormous quote", lambda p: {**ANSWER, "quotes": ["a" * 501]}),
]


@pytest.mark.parametrize("name, build", BAD_ANALYSIS, ids=[b[0] for b in BAD_ANALYSIS])
def test_a_bad_analysis_is_refused(db, clock, sid, name, build):
    plan = started(db, sid, clock)
    refuse(db, sid, ev(plan, 2, "candidate", "answer", analysis=build(plan)), clock, 422, "INTERVIEW_BAD_TURN", field="analysis")
    assert [t.seq for t in turn_rows(db, sid)] == [1]


def test_missing_coverage_is_refused(db, clock, sid):
    plan = plan_of(db, sid)
    refuse(db, sid, ev(plan, coverage=None), clock, 422, "INTERVIEW_BAD_COVERAGE", field="missing")
    unchanged(db, sid)


# ── Sizes ──


def test_a_turn_of_exactly_the_limit_is_stored_and_one_more_is_refused_never_cut(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer", text="가" * 4000), clock)
    assert len(turn_rows(db, sid)[-1].text) == 4000
    refuse(db, sid, ev(plan, 3, "candidate", "answer", text="가" * 4001), clock, 422, "INTERVIEW_TURN_TOO_LONG")
    assert [t.seq for t in turn_rows(db, sid)] == [1, 2]  # nothing was cut and stored


def test_the_raw_input_is_capped_before_it_is_masked(db, clock, sid, monkeypatch):
    plan = started(db, sid, clock)
    masked = []
    real = ingest.mask_spoken
    monkeypatch.setattr(ingest, "mask_spoken", lambda *a, **k: masked.append(1) or real(*a, **k))
    refuse(db, sid, ev(plan, 2, "candidate", "answer", text="가" * 8001), clock, 422, "INTERVIEW_TURN_TOO_LONG")
    assert masked == []  # refused before any work on it


def test_the_length_limit_is_that_of_the_masked_text(db, clock, sid):
    """Masking can make a text shorter (an address becomes a placeholder) or longer; the stored length is what counts."""
    plan = started(db, sid, clock)
    text = "x " + "kim@example.com " * 260  # about 4200 characters raw, shorter once the addresses are placeholders
    assert len(text) > 4000
    rec(db, sid, ev(plan, 2, "candidate", "answer", text=text), clock)
    assert len(turn_rows(db, sid)[-1].text) <= 4000


def test_the_sequence_number_cap_leaves_the_last_slot_to_the_closing_line(db, clock, sid):
    plan = started(db, sid, clock)
    for seq in range(2, 120):
        db.add(InterviewTurn(session_id=sid, seq=seq, role="agent", kind="nudge", item_index=0, text="네"))
    db.commit()
    assert settings.INTERVIEW_MAX_TURNS == 120
    refuse(db, sid, ev(plan, 120), clock, 409, "INTERVIEW_TURN_LIMIT")  # the 120th is for the closing line
    refuse(db, sid, ev(plan, 121), clock, 409, "INTERVIEW_TURN_LIMIT")
    assert len(turn_rows(db, sid)) == 119


def test_the_last_regular_turn_is_the_119th(db, clock, sid):
    plan = started(db, sid, clock)
    for seq in range(2, 119):
        db.add(InterviewTurn(session_id=sid, seq=seq, role="agent", kind="nudge", item_index=0, text="네"))
    db.commit()
    assert rec(db, sid, ev(plan, 119, "agent", "nudge"), clock).outcome == "stored"
    assert len(turn_rows(db, sid)) == 119


# ── Sequence, duplicates and conflicts ──


def test_a_gap_is_refused_with_the_number_that_is_expected(db, clock, sid):
    plan = started(db, sid, clock)
    error = refuse(db, sid, ev(plan, 3, "candidate", "answer"), clock, 409, "INTERVIEW_SEQ_GAP")
    assert error.extra["expected_seq"] == 2
    assert [t.seq for t in turn_rows(db, sid)] == [1]
    assert rec(db, sid, ev(plan, 2, "candidate", "answer"), clock).outcome == "stored"  # the agent retries the missing event
    assert rec(db, sid, ev(plan, 3, "agent", "follow_up"), clock).outcome == "stored"


def test_the_same_event_again_is_a_duplicate_that_writes_and_changes_nothing(db, clock, sid):
    plan = started(db, sid, clock)
    first = ev(plan, 2, "candidate", "answer", coverage=cov(plan, {plan.items[0].topic_id: "partial"}))
    rec(db, sid, first, clock)
    before = (row(db, sid).coverage, [(t.id, t.seq, t.text) for t in turn_rows(db, sid)])
    # the retry carries another snapshot (it must not be applied) and another analysis (the first write stays)
    retry = ev(plan, 2, "candidate", "answer", coverage=cov(plan, {plan.items[0].topic_id: "demonstrated"}), analysis={**ANSWER, "answer_type": "partial"})
    result = rec(db, sid, retry, clock)
    assert (result.outcome, result.seq, result.started, result.dropped_quotes) == ("duplicate", 2, False, 0)
    assert (row(db, sid).coverage, [(t.id, t.seq, t.text) for t in turn_rows(db, sid)]) == before


@pytest.mark.parametrize(
    "change",
    [{"text": "다른 답변입니다."}, {"role": "agent", "kind": "nudge", "analysis": None}, {"kind": "follow_up", "role": "agent", "analysis": None}, {"index": 1}],
    ids=["text", "role", "kind", "item_index"],
)
def test_another_event_for_the_same_sequence_is_a_conflict_and_the_first_write_stays(db, clock, sid, change):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)
    before = [(t.id, t.role, t.kind, t.item_index, t.text) for t in turn_rows(db, sid)]
    coverage = row(db, sid).coverage
    other = dict(change)
    index = other.pop("index", 0)
    refuse(db, sid, ev(plan, 2, other.pop("role", "candidate"), other.pop("kind", "answer"), index, **other), clock, 409, "INTERVIEW_SEQ_CONFLICT", seq=2)
    assert [(t.id, t.role, t.kind, t.item_index, t.text) for t in turn_rows(db, sid)] == before
    assert row(db, sid).coverage == coverage


def test_the_identity_of_a_turn_is_its_masked_text(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer", text="제 이메일은 a@example.com 입니다"), clock)
    again = rec(db, sid, ev(plan, 2, "candidate", "answer", text="제 이메일은 other@example.org 입니다"), clock)
    assert again.outcome == "duplicate"  # both are the same masked text: "[이메일]"


def test_a_duplicate_is_only_acknowledged_after_the_plan_and_the_topic_echo_are_checked(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)
    refuse(db, sid, ev(plan, 2, "candidate", "answer", topic_id=plan.items[1].topic_id), clock, 422, "INTERVIEW_BAD_TURN", field="topic_id")
    refuse(db, sid, ev(plan, 2, "candidate", "answer", coverage=None), clock, 422, "INTERVIEW_BAD_COVERAGE")
    refuse(db, sid, ev(plan, 2, "candidate", "answer", analysis=None), clock, 422, "INTERVIEW_BAD_TURN", field="analysis")
    db.execute(update(InterviewSession).where(InterviewSession.id == sid).values(plan_sha256="0" * 64))
    db.commit()
    refuse(db, sid, ev(plan, 2, "candidate", "answer"), clock, 409, "INTERVIEW_PLAN_INVALID")  # even for an identical event


def test_a_retry_is_acknowledged_after_the_session_ended_but_a_new_turn_is_not(db, world, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)
    svc.end(db, world.user, sid, clock=clock)  # the seeker ends it
    assert rec(db, sid, ev(plan, 2, "candidate", "answer"), clock).outcome == "duplicate"  # a lost response, then a retry
    refuse(db, sid, ev(plan, 3, "agent", "follow_up"), clock, 409, "INTERVIEW_NOT_ACTIVE", status="aborted")
    refuse(db, sid, ev(plan, 2, "candidate", "answer", text="다른 말"), clock, 409, "INTERVIEW_SEQ_CONFLICT")


# ── The lifecycle, by the backend's clock at receipt ──


def test_a_turn_on_the_deadline_is_stored_and_one_second_later_it_is_refused(db, clock, sid):
    plan = started(db, sid, clock)
    clock.advance(600)  # exactly the end of the time budget
    assert rec(db, sid, ev(plan, 2, "candidate", "answer"), clock).outcome == "stored"
    clock.advance(1)
    for event in (ev(plan, 3, "candidate", "answer"), ev(plan, 3, "agent", "follow_up")):
        error = refuse(db, sid, event, clock, 409, "INTERVIEW_NOT_ACTIVE", status="live", end_grace_open=True)  # only the end event may follow
    assert [t.seq for t in turn_rows(db, sid)] == [1, 2]
    assert row(db, sid).status == "live"  # refusing does not settle


def test_no_turn_is_accepted_in_the_grace_or_after_it(db, clock, sid):
    plan = started(db, sid, clock)
    clock.advance(630)
    refuse(db, sid, ev(plan, 2, "candidate", "answer"), clock, 409, "INTERVIEW_NOT_ACTIVE", end_grace_open=True)
    clock.advance(1)  # past the grace: the session is stale
    refuse(db, sid, ev(plan, 2, "candidate", "answer"), clock, 409, "INTERVIEW_NOT_ACTIVE", status="aborted", end_grace_open=False)


def test_the_first_turn_is_refused_after_the_join_deadline(db, clock, sid):
    plan = plan_of(db, sid)
    clock.advance(301)  # one second past the join deadline
    refuse(db, sid, ev(plan), clock, 409, "INTERVIEW_NOT_ACTIVE", status="aborted")
    unchanged(db, sid)


def test_the_first_turn_on_the_join_deadline_still_starts_the_session(db, clock, sid):
    plan = plan_of(db, sid)
    clock.advance(300)
    assert rec(db, sid, ev(plan), clock).started is True


def test_turns_of_a_session_that_is_not_there_or_not_running_are_refused(db, world, clock, sid):
    plan = plan_of(db, sid)
    refuse(db, 99999, ev(plan), clock, 404, "INTERVIEW_NOT_FOUND")
    svc.delete(db, world.user, sid, clock=clock)
    refuse(db, sid, ev(plan), clock, 404, "INTERVIEW_NOT_FOUND")


def test_an_expired_session_takes_no_turn(db, clock, sid):
    plan = plan_of(db, sid)
    clock.advance(31 * 86400)
    refuse(db, sid, ev(plan), clock, 404, "INTERVIEW_NOT_FOUND")


@pytest.mark.parametrize("status", ["planning", "completed", "aborted"])
def test_a_session_that_is_not_created_or_live_takes_no_turn(db, clock, sid, status):
    plan = plan_of(db, sid)
    db.execute(update(InterviewSession).where(InterviewSession.id == sid).values(status=status, active_until=clock() + timedelta(days=1)))
    db.commit()
    refuse(db, sid, ev(plan), clock, 409, "INTERVIEW_NOT_ACTIVE")


def test_the_clock_must_be_aware(db, clock, sid):
    plan = plan_of(db, sid)
    naive = Clock()
    naive.now = naive.now.replace(tzinfo=None)
    with pytest.raises(ValueError):
        rec(db, sid, ev(plan), naive)


# ── The plan must be the stored canonical one ──


def test_a_plan_that_does_not_match_its_digest_takes_nothing(db, clock, sid):
    plan = plan_of(db, sid)
    stored = row(db, sid).plan
    db.execute(update(InterviewSession).where(InterviewSession.id == sid).values(plan={**stored, "rubric_notice": "changed"}))
    db.commit()
    refuse(db, sid, ev(plan), clock, 409, "INTERVIEW_PLAN_INVALID")
    unchanged(db, sid)


@pytest.mark.parametrize("broken", [{"items": "not a list"}, {"items": []}, {"nothing": 1}], ids=["items", "empty", "keys"])
def test_a_plan_that_cannot_be_read_takes_nothing_even_with_a_matching_digest(db, clock, sid, broken):
    plan = plan_of(db, sid)
    db.execute(update(InterviewSession).where(InterviewSession.id == sid).values(plan=broken, plan_sha256=plan_digest(broken)))
    db.commit()
    refuse(db, sid, ev(plan), clock, 409, "INTERVIEW_PLAN_INVALID")


# ── Masking, quotes and analysis ──


def test_candidate_text_is_masked_again_and_the_counts_are_merged(db, world, clock, sid):
    # A Latin name: the masker's own detection does not know it, only the seeker's display name does
    world.user.display_name = "Jordan Lee"
    db.commit()
    plan = started(db, sid, clock)
    raw = "저는 Jordan Lee입니다. 이메일은 kim@example.com 이고 전화는 010-1234-5678 입니다"
    rec(db, sid, ev(plan, 2, "candidate", "answer", text=raw, masked_kinds={"email": 2, "name": 1}), clock)
    stored = turn_rows(db, sid)[-1]
    assert stored.text == "저는 [이름]입니다. 이메일은 [이메일] 이고 전화는 [전화번호] 입니다"
    assert stored.masked_kinds == {"email": 3, "name": 2, "phone": 1}  # the agent's counts plus what this masking found
    for secret in ("Jordan", "kim@example.com", "010-1234-5678"):
        assert secret not in stored.text


def test_masked_text_is_left_as_it_is_and_the_counts_stay_the_agents(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer", text="이메일은 [이메일] 입니다", masked_kinds={"email": 1}), clock)
    stored = turn_rows(db, sid)[-1]
    assert (stored.text, stored.masked_kinds) == ("이메일은 [이메일] 입니다", {"email": 1})


def test_the_agents_own_lines_are_masked_again_too(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "agent", "follow_up", text="말씀하신 kim@example.com 에 대해 더 설명해 주시겠어요?"), clock)
    stored = turn_rows(db, sid)[-1]
    assert stored.text == "말씀하신 [이메일] 에 대해 더 설명해 주시겠어요?" and stored.masked_kinds == {"email": 1}


def test_a_long_prefixed_line_of_the_interviewer_is_not_cut_by_the_question_limit(db, clock, sid):
    """The engine speaks prefix + question, which can pass the 300 characters a question may have; only the stored limit applies."""
    plan = started(db, sid, clock)
    line = "답변 감사합니다. 다음 질문입니다. " + "자세히 설명해 주세요. " * 30
    assert len(line) > 300
    rec(db, sid, ev(plan, 2, "agent", "follow_up", text=line), clock)
    assert turn_rows(db, sid)[-1].text.startswith("답변 감사합니다.")


def test_an_empty_answer_is_a_valid_event(db, clock, sid):
    plan = started(db, sid, clock)
    rec(db, sid, ev(plan, 2, "candidate", "answer", text="", analysis={**ANSWER, "answer_type": "empty"}), clock)
    assert turn_rows(db, sid)[-1].text == ""
    assert rec(db, sid, ev(plan, 3, "agent", "clarify"), clock).outcome == "stored"  # and the sequence goes on


def test_quotes_are_verified_against_the_masked_answer_again(db, clock, sid):
    plan = started(db, sid, clock)
    analysis = {**ANSWER, "quotes": ["Java로 API를 개발했습니다", "Kotlin으로 서버를 만들었습니다", "이메일은 kim@example.com"]}
    result = rec(db, sid, ev(plan, 2, "candidate", "answer", text="저는 Java로 API를 개발했습니다. 이메일은 kim@example.com 입니다", analysis=analysis), clock)
    assert result.dropped_quotes == 2  # an invented quote, and one that is only in the text before it was masked
    assert turn_rows(db, sid)[-1].analysis["quotes"] == ["Java로 API를 개발했습니다"]


def test_at_most_two_quotes_are_kept_and_a_disclosure_is_never_kept_as_evidence(db, clock, sid):
    plan = started(db, sid, clock)
    text = "저는 Java를 쓰고 Spring Boot를 쓰고 MySQL을 썼습니다. 저는 스물일곱 살입니다"
    analysis = {**ANSWER, "quotes": ["Java를 쓰고", "Spring Boot를 쓰고", "MySQL을 썼습니다", "저는 스물일곱 살입니다"]}
    rec(db, sid, ev(plan, 2, "candidate", "answer", text=text, analysis=analysis), clock)
    assert turn_rows(db, sid)[-1].analysis["quotes"] == ["Java를 쓰고", "Spring Boot를 쓰고"]


def test_the_analysis_is_stored_in_a_fixed_shape(db, clock, sid):
    plan = started(db, sid, clock)
    rubric = [p.id for p in plan.items[0].rubric]
    analysis = {"answer_type": "partial", "points": {rubric[1]: "partial", rubric[0]: "demonstrated"}, "quotes": [], "method": "llm:fake-llm"}
    rec(db, sid, ev(plan, 2, "candidate", "answer", analysis=analysis, method="llm:fake-llm"), clock)
    stored = turn_rows(db, sid)[-1]
    assert stored.analysis == {"answer_type": "partial", "points": {rubric[0]: "demonstrated", rubric[1]: "partial"}, "quotes": [], "method": "llm:fake-llm"}
    assert (stored.method, stored.item_index) == ("llm:fake-llm", 0)


def test_the_analysis_never_changes_the_coverage(db, world, clock, sid):
    """The agent's snapshot is the coverage. An analysis that says `demonstrated` for every point changes nothing."""
    plan = started(db, sid, clock)
    points = {p.id: "demonstrated" for p in plan.items[0].rubric}
    rec(db, sid, ev(plan, 2, "candidate", "answer", analysis={**ANSWER, "points": points}, coverage=cov(plan)), clock)
    stored = row(db, sid).coverage
    assert stored["status"][plan.items[0].topic_id] == "asked" and stored["levels"] == {}
    topics = {t.topic_id: t.status for t in svc.detail(db, world.user, sid, clock=clock).topics}
    assert topics[plan.items[0].topic_id] == "asked"


def test_what_is_stored_is_the_sanitized_snapshot_and_nothing_the_agent_added(db, clock, sid):
    plan = plan_of(db, sid)
    rec(db, sid, ev(plan), clock)
    assert set(row(db, sid).coverage) == {"phase", "end_reason", "status", "levels"}


# ── Atomicity ──


def test_a_failed_insert_leaves_no_trace_not_even_the_start_of_the_session(db, clock, sid, monkeypatch):
    plan = plan_of(db, sid)

    def boom(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("disk full"))

    monkeypatch.setattr(ingest, "_insert_turn", boom)
    with pytest.raises(OperationalError):
        rec(db, sid, ev(plan), clock)
    r = row(db, sid)
    assert (r.status, r.started_at, r.coverage, len(turn_rows(db, sid))) == ("created", None, None, 0)  # the start was rolled back with it
    monkeypatch.undo()
    assert rec(db, sid, ev(plan), clock).started is True  # and the event can be sent again


def test_a_failed_insert_does_not_keep_the_coverage_of_that_turn(db, clock, sid, monkeypatch):
    plan = started(db, sid, clock)
    before = row(db, sid).coverage
    monkeypatch.setattr(ingest, "_insert_turn", lambda *a, **k: (_ for _ in ()).throw(OperationalError("INSERT", {}, Exception("x"))))
    with pytest.raises(OperationalError):
        rec(db, sid, ev(plan, 2, "candidate", "answer", coverage=cov(plan, {plan.items[0].topic_id: "partial"})), clock)
    assert row(db, sid).coverage == before and len(turn_rows(db, sid)) == 1


def test_a_coverage_that_breaks_the_rules_does_not_start_the_session(db, clock, sid):
    plan = plan_of(db, sid)
    refuse(db, sid, ev(plan, coverage=cov(plan, {plan.items[0].topic_id: "demonstrated"})), clock, 422, "INTERVIEW_BAD_COVERAGE", field="status_transition")
    unchanged(db, sid)  # the start was rolled back with the refused turn


def test_a_turn_and_its_coverage_are_stored_together_or_not_at_all(db, clock, sid):
    plan = started(db, sid, clock)
    refuse(db, sid, ev(plan, 2, "candidate", "answer", coverage=cov(plan, {plan.items[0].topic_id: "asked"}, levels={plan.items[1].topic_id: {}})), clock, 422, "INTERVIEW_BAD_COVERAGE")
    assert [t.seq for t in turn_rows(db, sid)] == [1] and row(db, sid).coverage == cov(plan)


# ── Interleavings, one connection: the point is the logic, not real parallelism ──


def test_a_second_request_that_stored_the_same_turn_in_between_makes_this_one_a_duplicate(db, clock, sid, monkeypatch):
    """The pre-check saw nothing; another request then stored the same turn; the guard and the checks under its lock find it."""
    plan = started(db, sid, clock)
    event = ev(plan, 2, "candidate", "answer")
    real = ingest._is_duplicate
    calls = []

    def pre_check_sees_nothing_then_the_rival_stores_it(session, session_id, turn):
        calls.append(1)
        if len(calls) == 1:
            ingest.record_turn(session, session_id, event, clock=clock)  # the other request, whole
            return False
        return real(session, session_id, turn)

    monkeypatch.setattr(ingest, "_is_duplicate", pre_check_sees_nothing_then_the_rival_stores_it)
    assert rec(db, sid, event, clock).outcome == "duplicate"
    assert [t.seq for t in turn_rows(db, sid)] == [1, 2]


def test_a_unique_violation_on_the_sequence_is_classified_not_hidden(db, clock, sid, monkeypatch):
    """The backstop: if the checks under the lock were skipped, UNIQUE (session_id, seq) still stops a second row, and the error is
    classified (duplicate or conflict) by looking at what is stored, not swallowed."""
    plan = started(db, sid, clock)
    event = ev(plan, 2, "candidate", "answer")
    rec(db, sid, event, clock)
    real_state, real_dup = ingest._stored_state, ingest._is_duplicate
    calls = []

    def blind_pre_check(session, session_id, turn):
        calls.append(1)
        return False if len(calls) == 1 else real_dup(session, session_id, turn)  # only the first look is blind

    monkeypatch.setattr(ingest, "_is_duplicate", blind_pre_check)
    monkeypatch.setattr(ingest, "_stored_state", lambda session, session_id: (1, *real_state(session, session_id)[1:]))  # "seq 2 is free"
    assert rec(db, sid, event, clock).outcome == "duplicate"  # the insert hit the unique index; the stored turn is the same
    calls.clear()
    with pytest.raises(AppError) as error:
        rec(db, sid, ev(plan, 2, "candidate", "answer", text="다른 답변입니다."), clock)
    assert error.value.code == "INTERVIEW_SEQ_CONFLICT"
    assert [t.text for t in turn_rows(db, sid)][1] == "저는 Java로 API를 개발했습니다."  # the first write stays


def test_a_unique_violation_that_is_not_the_sequence_is_not_hidden(db, clock, sid, monkeypatch):
    plan = started(db, sid, clock)
    from sqlalchemy.exc import IntegrityError

    def other_violation(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("another constraint"))

    monkeypatch.setattr(ingest, "_insert_turn", other_violation)
    with pytest.raises(IntegrityError):
        rec(db, sid, ev(plan, 2, "candidate", "answer"), clock)  # nothing is stored at seq 2, so it is not a lost race
    assert [t.seq for t in turn_rows(db, sid)] == [1]


def test_the_seeker_ending_the_session_between_the_checks_and_the_write_wins_cleanly(db, world, clock, sid, monkeypatch):
    plan = started(db, sid, clock)
    real = ingest._is_duplicate

    def the_seeker_ends_it_now(session, session_id, turn):
        out = real(session, session_id, turn)
        svc.end(session, world.user, session_id, clock=clock)
        return out

    monkeypatch.setattr(ingest, "_is_duplicate", the_seeker_ends_it_now)
    refuse(db, sid, ev(plan, 2, "candidate", "answer"), clock, 409, "INTERVIEW_NOT_ACTIVE", status="aborted")
    assert [t.seq for t in turn_rows(db, sid)] == [1] and row(db, sid).end_reason == "seeker_ended"


def test_settlement_between_the_checks_and_the_write_wins_cleanly(db, clock, sid, monkeypatch):
    plan = started(db, sid, clock)
    real = ingest._is_duplicate

    def time_runs_out_and_a_settle_runs(session, session_id, turn):
        out = real(session, session_id, turn)
        clock.advance(700)  # past the budget and the grace
        svc.settle(session, None, clock())
        return out

    monkeypatch.setattr(ingest, "_is_duplicate", time_runs_out_and_a_settle_runs)
    refuse(db, sid, ev(plan, 2, "candidate", "answer"), clock, 409, "INTERVIEW_NOT_ACTIVE")
    assert [t.seq for t in turn_rows(db, sid)] == [1] and row(db, sid).end_reason == "stale_live"


# ── Who can call it ──


def test_the_ingest_functions_take_no_user_and_the_session_alone_identifies_the_target(db):
    import inspect

    for call in (ingest.record_turn, ingest.record_end):
        assert list(inspect.signature(call).parameters) == ["db", "session_id", "event", "clock"]


def test_a_seekers_other_data_is_never_read_except_the_display_name_for_masking(db, world, clock, sid):
    plan = plan_of(db, sid)
    from .test_interview_create import capture, touching

    with capture(db) as log:
        rec(db, sid, ev(plan), clock)
    assert touching(log, "cv_documents", "job_criteria", "applications", "evaluations", "career_contents") == []
    users = touching(log, "FROM users")
    assert all("users.display_name" in s for s in users)
    assert db.scalar(select(func.count()).select_from(User)) >= 1
