"""Sanitized views of an interview, the form in which later code (the feedback generator) must read one for a model
(docs/DECISIONS.md D61, D62, D63). That is a rule for future code, enforced only in part (see the last sentence).

`state.turns` holds the masked transcript as it was said, and a plan holds whatever the plan builder or a deserializer put
in it. Neither is model input. These views return every string as `SafeText` (what `sensitive.for_model` leaves), drop what
becomes empty, and carry codes (statuses, levels, answer types, topic ids) as they are, so the data a model gets about an
interview is exactly what `boundary.compose` accepts. An architecture test fails if a module of `ai/interview/` other than
the engine, the state and this one reads `state.turns` or `state.plan`.

Two ways to make the same views. `transcript_view(state)` and `plan_view(state)` read a running or finished interview.
`transcript_view_from(turns, topic_ids)` and `plan_view_from(plan, snapshot)` rebuild them from what a backend persisted:
the turns, the plan the engine ran, and the coverage snapshot (`coverage_snapshot(state)`: codes only, no text). The first
pair is written with the second, so there is one code path. A persisted plan goes through `validate_plan` again, and a
snapshot is read defensively (an unknown status or level is ignored, a missing topic is `not_asked`).
"""
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai.guardrails.blocklist import Blocklist
from ai.interview.sensitive import SafeText, safe_text
from ai.interview.state import InterviewState
from ai.interview.types import LEVEL_RANK, InterviewPlan, TopicStatus, Turn
from ai.interview.validate import validate_plan

_STATUSES = frozenset(s.value for s in TopicStatus)
_LEVELS = frozenset(LEVEL_RANK)
_PHASES = frozenset({"new", "listening", "ended", "aborted"})
_CODE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")  # a reason code, never text of the interview


@dataclass(frozen=True)
class SafeTurn:
    seq: int
    role: str
    kind: str
    text: SafeText
    answer_type: str | None = None
    points: tuple[tuple[str, str], ...] = ()  # (rubric point id, level) of an analysed answer
    quotes: tuple[SafeText, ...] = ()
    topic_id: str | None = None  # the plan topic this line belongs to, from the item index of the turn


@dataclass(frozen=True)
class SafeItem:
    topic_id: str
    kind: str
    question: SafeText
    criterion_name: SafeText
    importance: str | None
    rubric: tuple[tuple[str, SafeText], ...]
    status: str
    levels: tuple[tuple[str, str], ...]  # (rubric point id, best level so far)
    depth: int | None = None


@dataclass(frozen=True)
class SafeUncovered:
    criterion_id: int
    name: SafeText
    importance: str
    reason: str


@dataclass(frozen=True)
class SafePlan:
    items: tuple[SafeItem, ...]
    uncovered: tuple[SafeUncovered, ...]
    phase: str = "ended"  # new | listening | ended | aborted
    end_reason: str | None = None  # a code such as "time" or "plan_exhausted"; None when unknown
    issues: tuple[str, ...] = ()  # what `validate_plan` changed in a persisted plan (codes); empty for a plan the engine ran
    depth: int = 2

    @property
    def topic_ids(self) -> tuple[str, ...]:
        """The topic ids in plan order: the list that the item index of a persisted turn points into."""
        return tuple(item.topic_id for item in self.items)


def _code(value: object) -> str | None:
    return value if isinstance(value, str) and _CODE.match(value) else None


def coverage_snapshot(state: InterviewState) -> dict[str, Any]:
    """What a backend persists to rebuild `plan_view` later: the phase, the end reason, each topic's status and each rubric
    point's best level. Codes only: no question, no answer, no name. JSON-friendly."""
    return {
        "phase": state.phase.value,
        "end_reason": state.end_reason,
        "status": {topic: status.value for topic, status in state.status.items()},
        "levels": {topic: dict(levels) for topic, levels in state.levels.items()},
    }


def transcript_view_from(turns: Iterable[Turn], topic_ids: Sequence[str] = ()) -> tuple[SafeTurn, ...]:
    """The transcript as SafeText. A line that is empty after the cut is left out, and so is a quote that is. `topic_ids`:
    the topic ids of the plan the engine ran, in order (`SafePlan.topic_ids`); a turn whose item index points outside it has
    no topic. Persisted turns are read defensively."""
    out: list[SafeTurn] = []
    for turn in turns:
        if turn.role not in ("agent", "candidate") or not isinstance(turn.text, str):
            continue
        text = safe_text(turn.text)
        if not text:
            continue
        analysis = turn.analysis if isinstance(turn.analysis, Mapping) else {}
        raw_quotes = analysis.get("quotes")
        quotes = tuple(q for q in (safe_text(raw) for raw in raw_quotes if isinstance(raw, str)) if q) if isinstance(raw_quotes, (list, tuple)) else ()
        raw_points = analysis.get("points")
        points = (
            tuple(sorted((str(pid), str(level)) for pid, level in raw_points.items() if level in _LEVELS)) if isinstance(raw_points, Mapping) else ()
        )
        index = turn.item_index
        topic = topic_ids[index] if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(topic_ids) else None
        out.append(SafeTurn(int(turn.seq), turn.role, _code(turn.kind) or "other", text, _code(analysis.get("answer_type")), points, quotes, topic))
    return tuple(out)


def plan_view_from(plan: InterviewPlan, snapshot: Mapping[str, Any] | None = None, *, blocklists: Sequence[Blocklist] = ()) -> SafePlan:
    """The plan with its statuses and levels, every string as SafeText. `plan` is validated again (`validate_plan`, without
    the CV text), so a persisted plan takes the same path as any other; pass the blocklists to apply them too."""
    report = validate_plan(plan, blocklists=blocklists)
    snap = snapshot if isinstance(snapshot, Mapping) else {}
    statuses = snap.get("status") if isinstance(snap.get("status"), Mapping) else {}
    levels = snap.get("levels") if isinstance(snap.get("levels"), Mapping) else {}

    def status_of(topic: str) -> str:
        value = statuses.get(topic)
        return value if isinstance(value, str) and value in _STATUSES else TopicStatus.NOT_ASKED.value

    def levels_of(topic: str) -> tuple[tuple[str, str], ...]:
        raw = levels.get(topic)
        if not isinstance(raw, Mapping):
            return ()
        return tuple(sorted((str(pid), level) for pid, level in raw.items() if isinstance(level, str) and level in _LEVELS))

    items = tuple(
        SafeItem(
            item.topic_id,
            item.kind,
            safe_text(item.question),
            safe_text(item.criterion_name),
            item.importance,
            tuple((p.id, safe_text(p.text)) for p in item.rubric),
            status_of(item.topic_id),
            levels_of(item.topic_id),
            item.depth,
        )
        for item in report.plan.items
    )
    uncovered = tuple(SafeUncovered(u.criterion_id, safe_text(u.name), u.importance, u.reason) for u in report.plan.uncovered)
    phase = snap.get("phase")
    return SafePlan(
        items,
        uncovered,
        phase if isinstance(phase, str) and phase in _PHASES else "ended",
        _code(snap.get("end_reason")),
        report.issues,
        report.plan.depth,
    )


def transcript_view(state: InterviewState) -> tuple[SafeTurn, ...]:
    """The transcript of a running or finished interview as SafeText, each line with its topic."""
    return transcript_view_from(state.turns, [item.topic_id for item in state.plan.items])


def plan_view(state: InterviewState) -> SafePlan:
    """The plan the engine runs (already validated) with its statuses and levels, every string as SafeText."""
    return plan_view_from(state.plan, coverage_snapshot(state))
