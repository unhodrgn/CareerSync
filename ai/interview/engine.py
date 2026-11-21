"""The interview engine: plan + state + rules, one answer at a time (docs/DECISIONS.md D51–D54, D57).

Sans-IO and model-agnostic. The caller speaks each returned `Action`, listens, and calls back with the transcribed answer
and the elapsed seconds; the engine never speaks, listens, reads a clock or calls a model, so a scripted dialog replays
identically. In `AI_MODE=rules` the whole interview is this class with `analysis=None`. A model-made `TurnAnalysis`
(prepared and checked by `llm.py`) goes through the same `guards.sanitize_analysis` gate, and a model failure just means
passing `None` again (D54).

    engine = InterviewEngine(plan, blocklists=..., names=[display_name])
    action = engine.start()                              # speak action.text
    action = engine.on_answer(transcript, now)           # speak action.text; stop when action.done
    action = engine.on_silence(seconds_silent, now)      # a nudge, a skip, or None

Privacy: `on_answer` masks the transcript first (`spoken_pii.mask_spoken`), stores only the masked text, and
`turn_context` is the only thing a model is ever given about an answer (AI rule 3, D53).
"""
from collections.abc import Sequence

from ai.guardrails.blocklist import Blocklist
from ai.interview import rules
from ai.interview.decide import decide, time_is_short
from ai.interview.guards import is_duplicate, sanitize_analysis, screen_spoken
from ai.interview.spoken_pii import SpokenMaskResult, mask_spoken
from ai.interview.state import InterviewState
from ai.interview.validate import validate_plan
from ai.interview.types import (
    DEFAULT_LIMITS,
    Action,
    ActionKind,
    AnswerType,
    DecisionKind,
    InterviewLimits,
    STRUCTURAL_ANSWER_TYPES,
    InterviewPlan,
    Phase,
    PlanItem,
    TopicStatus,
    TurnAnalysis,
    TurnContext,
)

_CONTEXT_TURNS = 4  # masked lines before the answer that a model may see: two exchanges
_FINAL_FALLBACK = "수고하셨습니다."
_REPEAT_PREFIX = "질문을 다시 말씀드리겠습니다."


class InterviewStateError(RuntimeError):
    """A call that does not fit the phase: an answer before `start`, or anything after the interview ended."""


class InterviewEngine:
    def __init__(
        self,
        plan: InterviewPlan,
        *,
        blocklists: Sequence[Blocklist] = (),
        limits: InterviewLimits = DEFAULT_LIMITS,
        names: Sequence[str] = (),
        cv_text: str | None = None,
    ) -> None:
        """`plan` may come from anywhere (the builder, a deserializer, a test): it is validated here, by the same
        `validate_plan` the builder ends with, and the engine runs the validated plan (D61). `cv_text`: the stored masked CV
        the plan was made from, if the caller has it; without it a `cv_quote` cannot be shown to come from the CV and is
        dropped. `plan_issues` lists what validation changed (codes only)."""
        self._blocklists = tuple(blocklists)
        self._names = tuple(names)
        report = validate_plan(plan, blocklists=self._blocklists, cv_text=cv_text)
        self.plan_issues = report.issues
        self.state = InterviewState(report.plan, limits)

    @property
    def blocklists(self) -> tuple[Blocklist, ...]:
        """The blocklists every spoken line and every model suggestion is screened with."""
        return self._blocklists

    # ── What a model may see ──

    def mask_answer(self, text: str) -> SpokenMaskResult:
        return mask_spoken(text, self._names)

    def turn_context(self, answer: str) -> TurnContext:
        """The model input for the current item: masked text and the plan's own words, nothing else (AI rule 3).

        `answer` is masked again here (masking is idempotent), so a caller that passes the raw transcript by mistake still
        cannot put personal data into the model input."""
        item = self._require_item()
        recent = tuple(t.text for t in self.state.turns[-_CONTEXT_TURNS:])
        return TurnContext(
            question=item.question,
            criterion_name=item.criterion_name,
            importance=item.importance,
            rubric=tuple((p.id, p.text) for p in item.rubric),
            answer=self.mask_answer(answer).text,
            previous=recent,
            asked=tuple(self.state.asked),
        )

    # ── The interview ──

    def start(self) -> Action:
        """The first question (or a closing line when the plan is empty). Speak the greeting and the AI disclosure first."""
        if self.state.phase is not Phase.NEW:
            raise InterviewStateError("start() was already called")
        self.state.phase = Phase.LISTENING
        return self._advance("", "start")

    def on_answer(self, text: str, now: float, analysis: TurnAnalysis | None = None) -> Action:
        """One finished candidate turn. `now`: seconds since the interview began. `analysis`: a model's analysis, if any."""
        state = self.state
        item = self._require_item()
        state.elapsed = max(state.elapsed, now)
        masked = self.mask_answer(text)
        structural = rules.analyze(masked.text, item)
        if analysis is None or structural.answer_type in STRUCTURAL_ANSWER_TYPES or analysis.answer_type in STRUCTURAL_ANSWER_TYPES:
            # Nothing said, almost nothing said, or a request to hear the question again: the rules decide, never a model,
            # whether it calls an answer empty or calls an empty one an answer
            analysis = structural
        else:
            analysis = sanitize_analysis(analysis, item, masked.text, state.asked, self._blocklists)
        state.add_turn("candidate", "answer", masked.text, method=analysis.method, analysis=analysis.to_dict(), masked_kinds=dict(masked.kinds))

        topic = item.topic_id
        if analysis.answer_type is AnswerType.DONT_KNOW:
            state.dont_know.add(topic)
        state.levels[topic] = rules.best_levels(state.levels.get(topic, {}), analysis.points)
        state.refresh(item)

        decision = decide(
            analysis,
            now=now,
            limits=state.limits,
            followups_used=state.followups_used.get(topic, 0),
            clarifies_used=state.clarifies_used.get(topic, 0),
            repeats_used=state.repeats_used.get(topic, 0),
            missing=state.missing(item),
        )
        if decision.kind is DecisionKind.WRAP:
            return self._wrap(decision.reason)
        if decision.kind in (DecisionKind.CLARIFY, DecisionKind.REPEAT, DecisionKind.REDIRECT):
            counter = state.repeats_used if decision.kind is DecisionKind.REPEAT else state.clarifies_used
            counter[topic] = counter.get(topic, 0) + 1
            return self._clarify(item, decision.kind, decision.rephrase, decision.reason)
        if decision.kind is DecisionKind.FOLLOW_UP:
            action = self._follow_up(item, analysis, decision.point_id)
            if action is not None:
                state.followups_used[topic] = state.followups_used.get(topic, 0) + 1
                return action
            return self._finish_item(item, skipped=False, bridge=rules.BRIDGE_TEXT, reason="no_new_follow_up")
        if decision.kind is DecisionKind.SKIP:
            return self._finish_item(item, skipped=True, bridge=rules.SKIP_BRIDGE_TEXT, reason=f"skipped:{decision.reason}")
        if decision.reason == "too_short_again":  # a brief answer that stayed brief: accepted as given, not skipped (D59)
            state.insufficient.add(topic)
        bridge = rules.SKIP_BRIDGE_TEXT if decision.reason == "dont_know" else rules.BRIDGE_TEXT
        return self._finish_item(item, skipped=False, bridge=bridge, reason=decision.reason)

    def on_silence(self, silent_seconds: float, now: float) -> Action | None:
        """The candidate has said nothing for `silent_seconds`: a nudge once per item, a skip after the longer wait."""
        state = self.state
        if state.phase is not Phase.LISTENING:
            return None
        item = self._require_item()
        state.elapsed = max(state.elapsed, now)
        if time_is_short(now, state.limits):
            return self._wrap("time")
        if silent_seconds >= state.limits.silence_skip_seconds:
            return self._finish_item(item, skipped=True, bridge=rules.SKIP_BRIDGE_TEXT, reason="skipped:silence")
        if silent_seconds >= state.limits.silence_nudge_seconds and item.topic_id not in state.nudged:
            state.nudged.add(item.topic_id)
            return self._say(ActionKind.NUDGE, "nudge", rules.NUDGE_TEXT, "silence", item)
        return None

    def abort(self, reason: str, now: float | None = None) -> None:
        """The session ended from outside (the candidate left). No more speech; the coverage so far stays."""
        state = self.state
        if state.phase in (Phase.ENDED, Phase.ABORTED):
            return
        if now is not None:
            state.elapsed = max(state.elapsed, now)
        if item := state.current:
            state.refresh(item)
        state.phase, state.end_reason = Phase.ABORTED, reason

    # ── Steps ──

    def _require_item(self) -> PlanItem:
        if self.state.phase is not Phase.LISTENING or (item := self.state.current) is None:
            raise InterviewStateError(f"no question is waiting for an answer (phase: {self.state.phase.value})")
        return item

    def _say(self, kind: ActionKind, turn_kind: str, text: str, reason: str, item: PlanItem | None) -> Action:
        """Record and return one spoken line that has already passed the screens."""
        self.state.add_turn("agent", turn_kind, text)
        index = self.state.item_index if item is not None else None
        return Action(kind, text, index, item.topic_id if item else None, reason)

    def _ask_text(self, item: PlanItem, prefix: str) -> str | None:
        question = screen_spoken(item.question, self._blocklists, "question")
        if question is None:
            return None
        return f"{prefix} {question}".strip()

    def _advance(self, prefix: str, reason: str) -> Action:
        """Ask the next item that passes the screens, or wrap up when there is none."""
        state = self.state
        while True:
            state.item_index += 1
            item = state.current
            if item is None:
                return self._wrap("plan_exhausted" if state.plan.items else "empty_plan")
            text = self._ask_text(item, prefix)
            if text is None:  # a blocklist (possibly newer than the plan) now rejects the question: skip it
                state.status[item.topic_id] = TopicStatus.SKIPPED
                continue
            state.status[item.topic_id] = TopicStatus.ASKED
            state.asked.append(item.question)
            return self._say(ActionKind.ASK, "question", text, reason, item)

    def _finish_item(self, item: PlanItem, *, skipped: bool, bridge: str, reason: str) -> Action:
        self.state.refresh(item, skipped=skipped)
        return self._advance(bridge, reason)

    def _clarify(self, item: PlanItem, kind: DecisionKind, rephrase: bool, reason: str) -> Action:
        bl = self._blocklists
        if kind is DecisionKind.CLARIFY:  # nothing heard: ask again; very little said: ask for more
            text = rules.ELABORATE_TEXT if reason == AnswerType.TOO_SHORT.value else rules.CLARIFY_TEXT
            return self._say(ActionKind.CLARIFY, "clarify", text, reason, item)
        if kind is DecisionKind.REDIRECT:
            text = screen_spoken(rules.redirect_text(item.criterion_name), bl) or rules.GENERIC_REDIRECT
            return self._say(ActionKind.REDIRECT, "redirect", text, reason, item)
        # A repeat says the same question again (or its shorter wording); it is the one line the duplicate check allows
        if rephrase and (short := screen_spoken(item.rephrase, bl)) is not None:
            return self._say(ActionKind.REPEAT, "repeat", short, reason, item)
        question = screen_spoken(item.question, bl, "question") or item.question
        return self._say(ActionKind.REPEAT, "repeat", f"{_REPEAT_PREFIX} {question}", reason, item)

    def _follow_up(self, item: PlanItem, analysis: TurnAnalysis, point_id: str | None) -> Action | None:
        """A follow-up on the missing point: the model's suggestion if it survived the screens, else the template, else the
        template of another missing point. None when every candidate repeats something already asked."""
        state = self.state
        missing = state.missing(item)
        ordered = sorted(missing, key=lambda p: p.id != point_id)  # the chosen point first, the others in rubric order
        candidates = [analysis.suggested_follow_up] if analysis.suggested_follow_up else []
        candidates += [rules.follow_up_text(p) for p in ordered] + [rules.GENERIC_FOLLOW_UP]
        for text in candidates:
            line = screen_spoken(text, self._blocklists, "question")
            # A model's suggestion already passed the fuzzy check in sanitize_analysis; templates of different rubric points
            # share their wording by construction, so only an exact repeat counts here
            if line is None or is_duplicate(line, state.asked, ratio=1.0):
                continue
            state.asked.append(line)
            return self._say(ActionKind.FOLLOW_UP, "follow_up", line, f"missing_point:{point_id}", item)
        return None

    def _wrap(self, reason: str) -> Action:
        state = self.state
        if item := state.current:
            state.refresh(item)
        state.phase, state.end_reason = Phase.ENDED, reason
        text = screen_spoken(rules.closing_text(reason), self._blocklists, "closing") or _FINAL_FALLBACK
        state.add_turn("agent", "closing", text)
        return Action(ActionKind.WRAP, text, None, None, reason, done=True)
