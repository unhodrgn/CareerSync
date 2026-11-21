"""The decision rules (ai/interview/decide.py, D51, D54) in their documented order, and the approved limits (D57)."""
import pytest

from ai.interview.decide import decide, time_is_short
from ai.interview.types import (
    DEFAULT_LIMITS,
    AnswerType,
    DecisionKind,
    InterviewLimits,
    RubricPoint,
    TurnAnalysis,
)

LIMITS = DEFAULT_LIMITS
P1, P2 = RubricPoint("p1", "첫째", ("a",)), RubricPoint("p2", "둘째", ("b",))


def run(answer_type, *, now=100.0, followups=0, clarifies=0, repeats=0, missing=(P1, P2), limits=LIMITS):
    return decide(
        TurnAnalysis(answer_type), now=now, limits=limits, followups_used=followups, clarifies_used=clarifies, repeats_used=repeats, missing=missing
    )


def test_the_approved_defaults():
    assert (LIMITS.max_questions, LIMITS.max_seconds) == (5, 600)
    assert (LIMITS.max_followups_per_item, LIMITS.max_clarifies_per_item) == (2, 1)
    assert (LIMITS.silence_nudge_seconds, LIMITS.silence_skip_seconds, LIMITS.turn_llm_deadline_seconds) == (20, 45, 8)


@pytest.mark.parametrize(
    "bad",
    [
        {"max_questions": 0},
        {"max_seconds": 0},
        {"max_followups_per_item": -1},
        {"silence_nudge_seconds": 45, "silence_skip_seconds": 45},
        {"silence_nudge_seconds": 50},
    ],
)
def test_nonsense_limits_are_rejected(bad):
    with pytest.raises(ValueError):
        InterviewLimits(**bad)


def test_time_is_short_below_the_reserve_only():
    reserve = LIMITS.wrap_reserve_seconds
    assert not time_is_short(LIMITS.max_seconds - reserve, LIMITS)
    assert time_is_short(LIMITS.max_seconds - reserve + 0.1, LIMITS)
    assert time_is_short(LIMITS.max_seconds + 5, LIMITS)


@pytest.mark.parametrize("answer_type", list(AnswerType))
def test_insufficient_time_wraps_whatever_the_answer_was(answer_type):
    d = run(answer_type, now=LIMITS.max_seconds - 10)
    assert d.kind is DecisionKind.WRAP and d.reason == "time"


def test_nothing_said_is_clarified_once_then_the_item_is_skipped():
    assert run(AnswerType.EMPTY, clarifies=0).kind is DecisionKind.CLARIFY
    skipped = run(AnswerType.EMPTY, clarifies=1)
    assert skipped.kind is DecisionKind.SKIP and skipped.reason == "empty_again"


def test_very_little_said_is_asked_about_once_then_accepted_and_never_skipped():
    """Length is a soft heuristic (D59): a brief answer that stays brief is taken as given, it does not skip the item."""
    first = run(AnswerType.TOO_SHORT, clarifies=0)
    assert first.kind is DecisionKind.CLARIFY and first.reason == "too_short"
    second = run(AnswerType.TOO_SHORT, clarifies=1)
    assert second.kind is DecisionKind.NEXT and second.reason == "too_short_again"


@pytest.mark.parametrize("answer_type", [AnswerType.REPEAT_REQUEST, AnswerType.CLARIFICATION_REQUEST])
def test_a_repeat_request_is_repeated_once_then_skipped(answer_type):
    first = run(answer_type, repeats=0)
    assert first.kind is DecisionKind.REPEAT and first.rephrase is (answer_type is AnswerType.CLARIFICATION_REQUEST)
    assert run(answer_type, repeats=1).kind is DecisionKind.SKIP


def test_a_candidate_request_and_the_interviewers_clarify_have_separate_budgets():
    assert run(AnswerType.EMPTY, clarifies=1, repeats=0).kind is DecisionKind.SKIP  # the clarify budget is spent
    assert run(AnswerType.REPEAT_REQUEST, clarifies=1, repeats=0).kind is DecisionKind.REPEAT  # the request budget is not
    assert run(AnswerType.TOO_SHORT, clarifies=0, repeats=1).kind is DecisionKind.CLARIFY  # and the other way round


def test_off_topic_is_redirected_once_then_skipped():
    assert run(AnswerType.OFF_TOPIC, clarifies=0).kind is DecisionKind.REDIRECT
    assert run(AnswerType.OFF_TOPIC, clarifies=1).kind is DecisionKind.SKIP


def test_dont_know_moves_on_without_pressure():
    d = run(AnswerType.DONT_KNOW, followups=0, clarifies=0)
    assert d.kind is DecisionKind.NEXT and d.reason == "dont_know"


def test_a_partial_answer_gets_a_follow_up_on_the_highest_priority_missing_point():
    d = run(AnswerType.PARTIAL, missing=(P2, P1))
    assert d.kind is DecisionKind.FOLLOW_UP and d.point_id == "p2"  # the first of `missing`, which is in priority order


def test_follow_ups_stop_at_the_limit():
    assert run(AnswerType.PARTIAL, followups=1).kind is DecisionKind.FOLLOW_UP
    spent = run(AnswerType.PARTIAL, followups=LIMITS.max_followups_per_item)
    assert spent.kind is DecisionKind.NEXT and spent.reason == "followups_spent"


def test_a_partial_answer_with_nothing_left_missing_is_complete():
    assert run(AnswerType.PARTIAL, missing=()).kind is DecisionKind.NEXT


def test_a_complete_answer_moves_to_the_next_item():
    d = run(AnswerType.ANSWERED, missing=())
    assert d.kind is DecisionKind.NEXT and d.reason == "answered"


def test_a_zero_follow_up_budget_never_follows_up():
    limits = InterviewLimits(max_followups_per_item=0)
    assert run(AnswerType.PARTIAL, limits=limits).kind is DecisionKind.NEXT
