"""Per-criterion scoring and the Fit score, shared by applicant evaluation and job recommendation.

`score_candidate` is the single entry point: one company's criteria set, one candidate.
Fit is computed from stored per-criterion scores and the current weights, so a weight edit
re-ranks without another AI call.
"""
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date

from ai.embedding.model import Embedder
from ai.embedding.skills import SkillDictionary
from ai.llm.client import LLMClient
from ai.scoring.scorers import ScoringContext, score_one
from ai.scoring.types import Candidate, Criterion, CriterionResult, JobContext

LLM_CATEGORIES = ("project", "other")
STRONG_SCORE = 75


def score_candidate(
    criteria: Iterable[Criterion],
    candidate: Candidate,
    job: JobContext,
    *,
    skills: SkillDictionary,
    embedder: Embedder,
    llm: LLMClient | None,
    today: date | None = None,
) -> list[CriterionResult]:
    """Scores in the order of `criteria`. LLM criteria run in parallel."""
    criteria = list(criteria)
    ctx = ScoringContext(job, skills, embedder, llm, (today or date.today()).strftime("%Y-%m"))
    ctx.chunks(candidate)  # build once before threads share it
    results: dict[int, CriterionResult] = {}
    llm_items = [c for c in criteria if c.category in LLM_CATEGORIES and llm is not None]
    for c in criteria:
        if c not in llm_items:
            results[c.id] = score_one(c, candidate, ctx)
    if llm_items:
        with ThreadPoolExecutor(max_workers=min(4, len(llm_items))) as pool:
            for c, r in zip(llm_items, pool.map(lambda c: score_one(c, candidate, ctx), llm_items), strict=True):
                results[c.id] = r
    return [results[c.id] for c in criteria]


def aggregate_fit(scores: Mapping[int, int], weights: Mapping[int, float]) -> float:
    """Weighted mean on a 0-100 scale; criteria without a score count as 0."""
    total = sum(weights.values())
    if not total:
        return 0.0
    return round(sum(w * scores.get(cid, 0) for cid, w in weights.items()) / total, 1)


@dataclass(frozen=True)
class RankItem:
    key: int  # application id (or any candidate key)
    fit: float
    strong_count: int  # criteria scored >= STRONG_SCORE
    applied_order: float  # earlier first, e.g. a timestamp


def rank(items: Iterable[RankItem]) -> list[RankItem]:
    """Fit desc, then more strong criteria, then who applied first."""
    return sorted(items, key=lambda r: (-r.fit, -r.strong_count, r.applied_order))


def summary_comment(names: Mapping[int, str], scores: Mapping[int, int], weights: Mapping[int, float]) -> str:
    """Neutral one-paragraph summary built from the scores (no extra model call, nothing invented)."""
    ordered = sorted(weights, key=lambda cid: -weights[cid])
    strong = [names[cid] for cid in ordered if scores.get(cid, 0) >= STRONG_SCORE]
    weak = [names[cid] for cid in ordered if scores.get(cid, 0) < 40]
    parts = []
    if strong:
        parts.append(f"{', '.join(strong[:3])} 항목에서 근거가 충분합니다.")
    if weak:
        parts.append(f"{', '.join(weak[:3])} 항목은 이력서에서 근거가 부족하여 면접 등에서 확인이 필요합니다.")
    if not parts:
        parts.append("모든 항목이 중간 수준으로 평가되었습니다.")
    return " ".join(parts)
