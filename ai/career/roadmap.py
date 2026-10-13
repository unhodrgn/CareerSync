"""Skill roadmap for one job: one step per gap. LLM text when configured, a template otherwise.

The LLM writes only `goal` and `activities` for gaps computed in code; steps for any other skill are
dropped, URLs are stripped, and resources come only from data/learning_resources.yaml (D21).
"""
import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ai.career.gaps import Gap
from ai.career.resources import Resource, Resources
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import PROMPT_DIR

log = logging.getLogger(__name__)

MAX_STEPS = 6
# Links the model might add anyway: a scheme or www, or a domain followed by a path ("Node.js" stays)
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|io|dev|net|kr)/\S*", re.IGNORECASE)


@dataclass(frozen=True)
class Step:
    order: int
    skill: str
    kind: str
    goal: str
    activities: tuple[str, ...]
    resources: tuple[Resource, ...] = field(default=())


class _LlmStep(BaseModel):
    skill: str = Field(max_length=100)
    goal: str = Field(max_length=300)
    activities: list[str] = Field(min_length=1, max_length=4)


class RoadmapLlmOut(BaseModel):
    steps: list[_LlmStep] = Field(max_length=MAX_STEPS)


def _clean(text: str, limit: int) -> str:
    return " ".join(_URL.sub("", text).split())[:limit]


def _rules_text(gap: Gap) -> tuple[str, tuple[str, ...]]:
    if gap.kind == "certificate":
        return f"{gap.name} 취득", ("시험 일정과 출제 기준 확인하기", "기출 문제로 준비하기", "취득 후 이력서에 추가하기")
    return (
        f"{gap.name} 실무 기초 역량 갖추기",
        (
            f"공식 문서로 {gap.name}의 기본 개념과 사용법 익히기",
            f"{gap.name}을(를) 사용한 작은 프로젝트 만들어 보기",
            "결과물을 정리해 이력서와 포트폴리오에 반영하기",
        ),
    )


def roadmap_rules(gaps: list[Gap], resources: Resources) -> list[Step]:
    steps = []
    for i, gap in enumerate(gaps[:MAX_STEPS], start=1):
        goal, activities = _rules_text(gap)
        steps.append(Step(i, gap.name, gap.kind, goal, activities, tuple(resources.for_gap(gap.name, gap.kind))))
    return steps


def _llm_input(job_title: str, job_text: str, criteria: list[str], gaps: list[Gap], have: list[str]) -> str:
    gap_lines = [f"{g.kind}: {g.name}" for g in gaps[:MAX_STEPS]]
    parts = ["<job>", job_title, job_text, "</job>", "<criteria>", *criteria, "</criteria>"]
    parts += ["<gaps>", *gap_lines, "</gaps>", "<have>", ", ".join(have), "</have>"]
    return "\n".join(parts)


def roadmap_llm(
    gaps: list[Gap], job_title: str, job_text: str, criteria: list[str], have: list[str], resources: Resources, llm: LLMClient
) -> list[Step]:
    """LLM steps, validated. Raises LLMError when nothing usable comes back."""
    prompt = (PROMPT_DIR / "roadmap.md").read_text(encoding="utf-8")
    out = llm.complete_json(prompt, _llm_input(job_title, job_text, criteria, gaps, have), RoadmapLlmOut, max_tokens=2000)
    by_name = {g.name.casefold(): g for g in gaps[:MAX_STEPS]}
    written: dict[str, tuple[str, tuple[str, ...]]] = {}
    for s in out.steps:
        gap = by_name.get(s.skill.strip().casefold())
        if gap is None or gap.name in written:
            continue  # a skill that is not a computed gap, or a repeat
        goal = _clean(s.goal, 200)
        activities = tuple(a for a in (_clean(x, 150) for x in s.activities) if a)
        if goal and activities:
            written[gap.name] = (goal, activities)
    if not written:
        raise LLMError("roadmap: no usable step")
    steps = []
    for i, gap in enumerate(gaps[:MAX_STEPS], start=1):
        # Gaps the model skipped keep the template, so every gap gets a step
        goal, activities = written.get(gap.name) or _rules_text(gap)
        steps.append(Step(i, gap.name, gap.kind, goal, activities, tuple(resources.for_gap(gap.name, gap.kind))))
    return steps


def make_roadmap(
    gaps: list[Gap],
    job_title: str,
    job_text: str,
    criteria: list[str],
    have: list[str],
    resources: Resources,
    llm: LLMClient | None,
) -> tuple[list[Step], str]:
    """(steps, method); method is "llm:<model>" or "rules". LLM failures fall back to the template."""
    if llm is not None and gaps:
        try:
            return roadmap_llm(gaps, job_title, job_text, criteria, have, resources, llm), f"llm:{llm.model}"
        except LLMError as e:
            log.warning("roadmap by LLM failed, using the template: %s", e)
    return roadmap_rules(gaps, resources), "rules"
