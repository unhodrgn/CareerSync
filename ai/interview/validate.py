"""Validation of an interview plan (docs/DECISIONS.md D61): one path for every plan, whoever made it.

`validate_plan` is the last step of `plan.build_plan` and the first step of `InterviewEngine.__init__`, so a plan from the
builder, one built by hand and one loaded from storage (`InterviewPlan.from_dict`) are all checked by the same function
before anything is spoken or sent to a model. It does not trust the question bank, the rubric, the intent, the tips or the
quote of any item:

- every spoken text (question, rephrase) passes `screen_spoken` (URL, placeholder, verdict word, the age, gender and
  military-service vocabulary, both blocklists); a question that fails drops the item, and a criterion item that is dropped
  is listed in `plan.uncovered`, never lost;
- every other text (intent, tips, rubric points, keywords, criterion name) must not match the vocabulary or the blocklists,
  nor contain a whole line that `clean_cv` removed from the CV (`CleanCv.mentions_removed`), whatever its wording; what
  fails is dropped, or replaced by the generic text of its kind (a rubric);
- `cv_quote` survives only when the CV text is given and the quote is found in the cleaned CV; without the CV (the realtime
  agent has none) it is dropped, because nothing can show where it came from;
- ids, kinds, importance labels and sizes are checked, so a malformed or forged plan cannot carry an unknown topic, a weight
  or an unbounded text.

Cleaning is idempotent: validating a validated plan changes nothing. Issues are codes, never text of the plan.
"""
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ai.career.interview import allowed
from ai.embedding.skills import SkillDictionary
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.evidence import verify_quotes
from ai.interview import rules
from ai.interview.cv_context import CleanCv, clean_cv
from ai.interview.guards import screen_spoken
from ai.interview.sensitive import is_sensitive
from ai.interview.types import (
    AI_GENERATED,
    IMPORTANCE_RANK,
    MAX_RUBRIC_POINTS,
    MIN_RUBRIC_POINTS,
    RUBRIC_NOTICE,
    InterviewPlan,
    PlanItem,
    RubricPoint,
    UncoveredCriterion,
)

_TOPIC = re.compile(r"^(?:warmup|behavioral|c(\d{1,9}))$")
_POINT_ID = re.compile(r"^p\d{1,2}$")
_KEYWORD = re.compile(r"^[0-9A-Za-z가-힣+#.\-]{2,24}$")
_BANK_METHOD = re.compile(r"^(?:rules|llm:[\w.:/\-]{1,80})$")
_KINDS = frozenset({"technical", "experience", "behavioral"})
_CATEGORY_OF_KIND = {"technical": "skill", "experience": "experience", "behavioral": "other"}
_REASONS = frozenset({"no_slot", "no_question"})
_DEPTHS = frozenset({1, 2, 3})
DEFAULT_DEPTH = 2
MAX_NAME_CHARS, MAX_INTENT_CHARS, MAX_TIP_CHARS, MAX_TIPS = 80, 200, 150, 3
MAX_POINT_CHARS, MAX_KEYWORDS, MAX_QUOTE_CHARS = 120, 8, 300
EXCLUDED = "(제외됨)"  # shown in place of a criterion name that could not be kept


@dataclass(frozen=True)
class PlanReport:
    plan: InterviewPlan
    issues: tuple[str, ...]  # codes such as "c3:question" or "warmup:cv_quote"; never text of the plan


class _Checker:
    def __init__(self, blocklists: Sequence[Blocklist], clean: CleanCv | None, skills: SkillDictionary | None) -> None:
        self.blocklists, self.clean, self.skills = tuple(blocklists), clean, skills
        self.issues: list[str] = []

    def text_ok(self, text: object, limit: int) -> bool:
        """A text that is not spoken: short enough, not the vocabulary, not a removed CV line, not a blocklist hit."""
        if not isinstance(text, str) or not 0 < len(text.strip()) <= limit:
            return False
        if is_sensitive(text) or (self.clean is not None and self.clean.mentions_removed(text)):
            return False
        return allowed(text, "", (), self.blocklists)

    def spoken_ok(self, text: object, kind: str = "statement") -> bool:
        if not isinstance(text, str) or screen_spoken(text, self.blocklists, kind) is None:  # type: ignore[arg-type]
            return False
        return self.clean is None or not self.clean.mentions_removed(text)

    def keywords(self, words: object) -> tuple[str, ...]:
        if not isinstance(words, Iterable) or isinstance(words, str):
            return ()
        kept = [w for w in words if isinstance(w, str) and _KEYWORD.match(w) and self.text_ok(w, 24)]
        return tuple(dict.fromkeys(kept))[:MAX_KEYWORDS]

    def rubric(self, item: PlanItem, name: str | None, tag: str) -> tuple[RubricPoint, ...]:
        points: list[RubricPoint] = []
        seen: set[str] = set()
        rubric = item.rubric if isinstance(item.rubric, Iterable) else ()
        for p in rubric:
            words = self.keywords(p.keywords) if isinstance(p, RubricPoint) else ()
            if not (isinstance(p, RubricPoint) and _POINT_ID.match(str(p.id)) and p.id not in seen and words and self.text_ok(p.text, MAX_POINT_CHARS)):
                points = []
                break
            seen.add(p.id)
            hits = p.min_hits if isinstance(p.min_hits, int) and not isinstance(p.min_hits, bool) else rules.min_hits(len(words))
            points.append(RubricPoint(p.id, p.text.strip(), words, max(1, min(hits, len(words))), AI_GENERATED))
        if MIN_RUBRIC_POINTS <= len(points) <= MAX_RUBRIC_POINTS:
            return tuple(points)
        self.issues.append(f"{tag}:rubric")
        generic = rules.make_rubric(name or "이 질문", _CATEGORY_OF_KIND.get(item.kind, "experience"), "", self.skills)
        if not all(self.text_ok(p.text, MAX_POINT_CHARS) for p in generic):  # the name itself is the problem
            generic = rules.make_rubric("이 질문", "other", "", self.skills)
        return generic

    def item(self, item: object) -> PlanItem | None:
        if not isinstance(item, PlanItem):
            self.issues.append("item:type")
            return None
        m = _TOPIC.match(item.topic_id) if isinstance(item.topic_id, str) else None
        tag = item.topic_id if m else "item"
        if m is None or item.kind not in _KINDS:
            self.issues.append(f"{tag}:topic_or_kind")
            return None
        criterion = m.group(1) is not None
        if criterion and (item.criterion_id != int(m.group(1)) or item.importance not in IMPORTANCE_RANK):
            self.issues.append(f"{tag}:criterion")
            return None
        if not self.spoken_ok(item.question, "question"):
            self.issues.append(f"{tag}:question")
            return None
        name = item.criterion_name if criterion and self.text_ok(item.criterion_name, MAX_NAME_CHARS) else None
        if item.criterion_name and name is None:
            self.issues.append(f"{tag}:criterion_name")
        raw_tips = tuple(item.answer_tips) if isinstance(item.answer_tips, Iterable) and not isinstance(item.answer_tips, str) else ()
        tips = tuple(t.strip() for t in raw_tips if self.text_ok(t, MAX_TIP_CHARS))
        intent = item.intent.strip() if self.text_ok(item.intent, MAX_INTENT_CHARS) else ""
        if (item.intent and not intent) or len(tips) != len(raw_tips):
            self.issues.append(f"{tag}:intent_or_tips")
        quote = item.cv_quote
        if quote is not None:
            grounded = self.clean is not None and self.text_ok(quote, MAX_QUOTE_CHARS) and bool(verify_quotes([quote], self.clean.text))
            if not grounded:
                self.issues.append(f"{tag}:cv_quote")
            quote = quote.strip() if grounded else None
        rephrase = item.rephrase if self.spoken_ok(item.rephrase) else rules.GENERIC_REPHRASE
        if rephrase is not item.rephrase:
            self.issues.append(f"{tag}:rephrase")
        depth = item.depth
        valid_depth = type(depth) is int and depth in _DEPTHS
        if criterion:
            if depth is not None and not valid_depth:
                self.issues.append(f"{tag}:depth")
                depth = None
        elif depth is not None:
            self.issues.append(f"{tag}:depth")
            depth = None
        return PlanItem(
            topic_id=item.topic_id,
            kind=item.kind,
            question=item.question,
            rephrase=rephrase,
            rubric=self.rubric(item, name, tag),
            topic_keywords=self.keywords(item.topic_keywords),
            criterion_id=int(m.group(1)) if criterion else None,
            criterion_name=name,
            importance=item.importance if criterion else None,
            intent=intent,
            answer_tips=tips[:MAX_TIPS],
            cv_quote=quote,
            depth=depth,
        )

    def uncovered(self, entries: object) -> list[UncoveredCriterion]:
        out: list[UncoveredCriterion] = []
        for u in entries if isinstance(entries, Iterable) and not isinstance(entries, str) else ():
            if not isinstance(u, UncoveredCriterion) or not isinstance(u.criterion_id, int) or u.importance not in IMPORTANCE_RANK:
                self.issues.append("uncovered:entry")
                continue
            name = u.name.strip() if self.text_ok(u.name, MAX_NAME_CHARS) else EXCLUDED
            out.append(UncoveredCriterion(u.criterion_id, name, u.importance, u.reason if u.reason in _REASONS else "no_question"))
        return out


def validate_plan(
    plan: InterviewPlan,
    *,
    blocklists: Sequence[Blocklist] = (),
    cv_text: str | None = None,
    skills: SkillDictionary | None = None,
) -> PlanReport:
    """The plan the engine may run: see the module doc. `cv_text`: the stored masked CV the plan was made from, if the caller
    has it (the backend does, the realtime agent does not); it is cleaned here, and only a `cv_quote` found in it is kept."""
    if not isinstance(plan, InterviewPlan):
        raise TypeError("validate_plan expects an InterviewPlan")
    check = _Checker(blocklists, clean_cv(cv_text) if cv_text is not None else None, skills)
    items: list[PlanItem] = []
    dropped: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for raw in plan.items if isinstance(plan.items, Iterable) else ():
        item = check.item(raw)
        if item is None:
            if isinstance(raw, PlanItem) and isinstance(raw.criterion_id, int) and raw.importance in IMPORTANCE_RANK:
                dropped.append((raw.criterion_id, raw.criterion_name or "", raw.importance))
            continue
        if item.topic_id in seen:
            check.issues.append(f"{item.topic_id}:duplicate")
            continue
        seen.add(item.topic_id)
        items.append(item)
    uncovered = check.uncovered(plan.uncovered)
    listed = {u.criterion_id for u in uncovered} | {i.criterion_id for i in items if i.criterion_id is not None}
    for cid, name, importance in dropped:  # a criterion whose question was refused is still reported as not covered
        if cid not in listed:
            listed.add(cid)
            uncovered.append(UncoveredCriterion(cid, name.strip() if check.text_ok(name, MAX_NAME_CHARS) else EXCLUDED, importance, "no_question"))  # type: ignore[arg-type]
    method = plan.bank_method if isinstance(plan.bank_method, str) and _BANK_METHOD.match(plan.bank_method) else "rules"
    raw_depth = plan.depth
    depth = raw_depth if type(raw_depth) is int and raw_depth in _DEPTHS else DEFAULT_DEPTH
    if depth != raw_depth or type(raw_depth) is not int:
        check.issues.append("plan:depth")
    return PlanReport(InterviewPlan(tuple(items), tuple(uncovered), RUBRIC_NOTICE, method, depth), tuple(check.issues))
