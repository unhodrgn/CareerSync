"""The running state of one interview: transcript, coverage, counters (docs/DECISIONS.md D51, D53).

Plain data plus small helpers; the engine mutates it. The transcript holds masked text only (D53). Statuses follow the
documented set: not_asked, asked, demonstrated, partial, not_shown, skipped.
"""
from dataclasses import dataclass, field
from typing import Any

from ai.interview.types import (
    InterviewLimits,
    InterviewPlan,
    Phase,
    PlanItem,
    PointLevel,
    RubricPoint,
    TopicStatus,
    Turn,
)


def item_status(item: PlanItem, levels: dict[str, PointLevel], *, skipped: bool, no_evidence: bool) -> TopicStatus:
    """The status of an item that was asked, from what its answers showed.

    skipped -> skipped; every rubric point demonstrated -> demonstrated; some point shown -> partial; answers that
    showed nothing, a "don't know" or a brief answer accepted as it was (`no_evidence`) -> not_shown; no usable answer
    yet -> asked."""
    if skipped:
        return TopicStatus.SKIPPED
    if levels:
        values = [levels.get(p.id, "not_shown") for p in item.rubric]
        if values and all(v == "demonstrated" for v in values):
            return TopicStatus.DEMONSTRATED
        if any(v in ("demonstrated", "partial") for v in values):
            return TopicStatus.PARTIAL
        return TopicStatus.NOT_SHOWN
    return TopicStatus.NOT_SHOWN if no_evidence else TopicStatus.ASKED


@dataclass
class InterviewState:
    plan: InterviewPlan
    limits: InterviewLimits
    phase: Phase = Phase.NEW
    item_index: int = -1
    elapsed: float = 0.0
    end_reason: str | None = None
    turns: list[Turn] = field(default_factory=list)
    status: dict[str, TopicStatus] = field(default_factory=dict)  # topic id -> status
    levels: dict[str, dict[str, PointLevel]] = field(default_factory=dict)  # topic id -> rubric point id -> best level so far
    followups_used: dict[str, int] = field(default_factory=dict)
    clarifies_used: dict[str, int] = field(default_factory=dict)  # the interviewer's re-prompts: clarify and redirect
    repeats_used: dict[str, int] = field(default_factory=dict)  # the candidate's requests: repeat and explain
    nudged: set[str] = field(default_factory=set)
    dont_know: set[str] = field(default_factory=set)
    insufficient: set[str] = field(default_factory=set)  # a brief answer that stayed brief after one request for more
    asked: list[str] = field(default_factory=list)  # every question and follow-up spoken, for the duplicate check

    def __post_init__(self) -> None:
        for item in self.plan.items:
            self.status.setdefault(item.topic_id, TopicStatus.NOT_ASKED)

    @property
    def current(self) -> PlanItem | None:
        items = self.plan.items
        return items[self.item_index] if 0 <= self.item_index < len(items) else None

    def missing(self, item: PlanItem) -> list[RubricPoint]:
        """The item's rubric points no answer has shown yet, highest priority (first) first."""
        levels = self.levels.get(item.topic_id, {})
        return [p for p in item.rubric if levels.get(p.id, "not_shown") == "not_shown"]

    def refresh(self, item: PlanItem, *, skipped: bool = False) -> TopicStatus:
        no_evidence = item.topic_id in self.dont_know or item.topic_id in self.insufficient
        status = item_status(item, self.levels.get(item.topic_id, {}), skipped=skipped, no_evidence=no_evidence)
        self.status[item.topic_id] = status
        return status

    def add_turn(self, role: str, kind: str, text: str, **extra: Any) -> Turn:
        turn = Turn(seq=len(self.turns) + 1, role=role, kind=kind, item_index=self.item_index if self.item_index >= 0 else None, text=text, **extra)  # type: ignore[arg-type]
        self.turns.append(turn)
        return turn

    def coverage(self) -> list[dict[str, Any]]:
        """One row per planned topic, then one per criterion the plan could not cover (status not_asked)."""
        rows = [
            {
                "topic_id": i.topic_id,
                "criterion_id": i.criterion_id,
                "criterion_name": i.criterion_name,
                "importance": i.importance,
                "status": self.status[i.topic_id].value,
            }
            for i in self.plan.items
        ]
        rows += [
            {
                "topic_id": f"c{u.criterion_id}",
                "criterion_id": u.criterion_id,
                "criterion_name": u.name,
                "importance": u.importance,
                "status": TopicStatus.NOT_ASKED.value,
            }
            for u in self.plan.uncovered
        ]
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "item_index": self.item_index,
            "elapsed": round(self.elapsed, 3),
            "end_reason": self.end_reason,
            "coverage": self.coverage(),
            "followups_used": dict(self.followups_used),
            "clarifies_used": dict(self.clarifies_used),
            "repeats_used": dict(self.repeats_used),
            "turns": [t.to_dict() for t in self.turns],
        }
