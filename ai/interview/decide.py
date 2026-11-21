"""What to do after one answer: a pure function of the analysis and the counters (docs/DECISIONS.md D51, D54, D57).

The order is the documented one and the first rule that applies wins:
1. not enough time left            -> wrap up
2. nothing said (empty)            -> clarify once, then skip the item
   very little said (too short)    -> ask for more once, then accept it as a brief answer: the item moves on as not_shown,
                                      never as skipped (length alone never skips a meaningful short answer, D59)
3. request to repeat or explain    -> repeat or rephrase once, then skip
4. off topic                       -> redirect once, then skip
5. "don't know"                    -> mark not_shown and continue
6. partial, a point still missing  -> follow up on the highest-priority missing point while the budget lasts
7. otherwise                       -> the next item
`max_clarifies_per_item` is two independent budgets per item (D59): one for the interviewer's own re-prompts (clarify,
ask for more, redirect), one for the candidate's requests (repeat, explain). A candidate who answers "네" and is asked
again may still ask for the question to be repeated; the global time budget (rule 1) is what bounds an item overall.
"""
from collections.abc import Sequence

from ai.interview.types import AnswerType, Decision, DecisionKind, InterviewLimits, RubricPoint, TurnAnalysis


def time_is_short(now: float, limits: InterviewLimits) -> bool:
    """True when fewer than `wrap_reserve_seconds` of the interview are left: no new question, no follow-up."""
    return limits.max_seconds - now < limits.wrap_reserve_seconds


def decide(
    analysis: TurnAnalysis,
    *,
    now: float,
    limits: InterviewLimits,
    followups_used: int,
    clarifies_used: int,
    repeats_used: int,
    missing: Sequence[RubricPoint],
) -> Decision:
    """`missing`: the item's rubric points no answer has shown yet, highest priority first."""
    if time_is_short(now, limits):
        return Decision(DecisionKind.WRAP, "time")
    kind = analysis.answer_type
    can_clarify = clarifies_used < limits.max_clarifies_per_item
    if kind is AnswerType.EMPTY:
        return Decision(DecisionKind.CLARIFY, kind.value) if can_clarify else Decision(DecisionKind.SKIP, "empty_again")
    if kind is AnswerType.TOO_SHORT:
        return Decision(DecisionKind.CLARIFY, kind.value) if can_clarify else Decision(DecisionKind.NEXT, "too_short_again")
    if kind in (AnswerType.REPEAT_REQUEST, AnswerType.CLARIFICATION_REQUEST):
        if repeats_used < limits.max_clarifies_per_item:
            return Decision(DecisionKind.REPEAT, kind.value, rephrase=kind is AnswerType.CLARIFICATION_REQUEST)
        return Decision(DecisionKind.SKIP, f"{kind.value}_again")
    if kind is AnswerType.OFF_TOPIC:
        return Decision(DecisionKind.REDIRECT, kind.value) if can_clarify else Decision(DecisionKind.SKIP, "off_topic_again")
    if kind is AnswerType.DONT_KNOW:
        return Decision(DecisionKind.NEXT, "dont_know")
    if kind is AnswerType.PARTIAL and missing and followups_used < limits.max_followups_per_item:
        return Decision(DecisionKind.FOLLOW_UP, "missing_point", point_id=missing[0].id)
    return Decision(DecisionKind.NEXT, "followups_spent" if kind is AnswerType.PARTIAL and missing else "answered")
