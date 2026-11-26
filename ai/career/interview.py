"""Interview practice questions for one job (docs/DECISIONS.md D21). LLM when configured, templates otherwise.

The LLM sees the JD, the criteria (no weights) and up to 4 excerpts of the masked CV. Its output is checked:
`criterion_id` must be a criterion of the job (else null), `cv_quote` must be in the masked CV
(`verify_quotes`, else null), URLs are stripped. Every question — LLM or template — must pass the criteria
guardrail (data/blocklist.yaml) and then the interview blocklist (data/interview_blocklist.yaml, written for
questions: marriage, children, dating, religion, age, appearance, origin, family, politics, health), checked
on the question, its intent and its tips; a hit drops the question. Fewer than MIN_QUESTIONS left → the template.
"""
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ai.embedding.model import Embedder
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.criteria import check_criterion
from ai.guardrails.evidence import verify_quotes
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import PROMPT_DIR
from ai.scoring.retrieval import cv_chunks, retrieve

log = logging.getLogger(__name__)

MIN_QUESTIONS, MAX_QUESTIONS, MAX_BANK_QUESTIONS, MAX_EXCERPTS = 3, 10, 45, 4
DEPTHS: tuple[int, ...] = (1, 2, 3)
Depth = Literal[1, 2, 3]
Kind = Literal["technical", "experience", "behavioral"]
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|io|dev|net|kr)/\S*", re.IGNORECASE)


@dataclass(frozen=True)
class CriterionInfo:
    id: int
    name: str
    category: str
    description: str = ""


@dataclass(frozen=True)
class Question:
    question: str
    criterion_id: int | None
    criterion_name: str | None
    kind: str
    intent: str
    answer_tips: tuple[str, ...]
    cv_quote: str | None = None
    depth: int | None = None


class _LlmQuestion(BaseModel):
    question: str = Field(max_length=300)
    criterion_id: int | None = None
    kind: Kind
    intent: str = Field(max_length=200)
    answer_tips: list[str] = Field(default_factory=list, max_length=3)
    cv_quote: str | None = Field(None, max_length=300)
    depth: Depth | None = None

    @field_validator("depth", mode="before")
    @classmethod
    def _coerce_depth(cls, value: object) -> int | None:
        # Coerce invalid model depths to None so validation can keep the question or fill missing depths from templates.
        return value if type(value) is int and value in DEPTHS else None


class InterviewLlmOut(BaseModel):
    questions: list[_LlmQuestion] = Field(max_length=MAX_BANK_QUESTIONS)


def _clean(text: str, limit: int) -> str:
    return " ".join(_URL.sub("", text).split())[:limit]


# ── Template (AI_MODE=rules) ──

_TIPS_EXPERIENCE = ("상황과 본인의 역할을 먼저 설명하기", "어려웠던 점과 해결 과정을 구체적으로", "결과와 배운 점으로 마무리하기")
_TIPS_BY_DEPTH: dict[tuple[str, int], tuple[str, ...]] = {
    ("technical", 1): ("핵심 개념의 정의를 먼저 말하기", "왜 필요한지 목적과 장점을 설명하기", "간단한 활용 예시 하나 덧붙이기"),
    ("technical", 2): ("실무나 프로젝트에서 적용한 구체적 사례를 들기", "사용하며 겪은 문제와 해결 과정을 설명하기", "결과나 주의할 점으로 마무리하기"),
    ("technical", 3): ("설계 선택의 이유와 트레이드오프를 비교하기", "트러블슈팅 또는 확장성 고려 사항 설명하기", "대안 기술과 비교한 판단 근거 제시하기"),
    ("other", 1): ("핵심 배경과 중요하다고 보는 이유를 먼저 말하기", "본인의 생각이나 기준을 간결히 정리하기", "간단한 관련 경험으로 연결하기"),
    ("other", 2): _TIPS_EXPERIENCE,
    ("other", 3): ("당시 고려했던 선택지와 트레이드오프를 설명하기", "문제·갈등의 원인과 해결 과정을 구체적으로", "재발 방지나 구조·방식 개선점으로 마무리하기"),
}
_BY_CATEGORY: dict[str, dict[int, tuple[str, Kind, str]]] = {
    # category: {depth: (question template, kind, intent template)}
    "skill": {
        1: ("{name}의 핵심 개념은 무엇이고 왜 사용하나요?", "technical", "{name}의 기본 개념과 사용 이유 이해 확인"),
        2: ("{name}을(를) 실무나 프로젝트에서 어떻게 사용했는지 구체적인 사례로 설명해 주세요.", "technical", "{name} 활용 경험과 이해 수준 확인"),
        3: ("{name}을(를) 도입하거나 설계할 때 고려해야 할 트레이드오프, 성능·확장성 이슈 또는 대안은 무엇인가요?", "technical", "{name}의 심화 설계, 트러블슈팅 및 대안 비교 역량 확인"),
    },
    "experience": {
        1: ("'{name}'와(과) 같은 직무 역량이 실무에서 왜 중요하다고 생각하시나요?", "experience", "'{name}' 관련 기본 직무 이해와 필요성 인식 확인"),
        2: ("지금까지의 경력 중 '{name}'와(과) 가장 관련 있는 경험을 소개해 주세요.", "experience", "직무 관련 경력의 깊이 확인"),
        3: ("'{name}'와(과) 관련된 업무에서 복잡한 문제나 장애를 해결하고 구조·프로세스를 개선한 경험을 설명해 주세요.", "experience", "심화 문제 해결, 의사결정 트레이드오프 및 개선 역량 확인"),
    },
    "project": {
        1: ("'{name}'와(과) 같은 프로젝트를 수행할 때 가장 중요한 기본 원칙은 무엇이라고 생각하나요?", "experience", "'{name}' 관련 프로젝트 기본 이해와 접근 방식 확인"),
        2: ("'{name}'와(과) 관련해 진행한 프로젝트에서 맡은 역할과 성과를 설명해 주세요.", "experience", "프로젝트 수행 방식과 기여도 확인"),
        3: ("'{name}'와(과) 관련된 프로젝트에서 아키텍처·기술 선택의 트레이드오프, 병목 해결 또는 확장성 개선 경험을 말씀해 주세요.", "experience", "프로젝트 설계 트레이드오프와 트러블슈팅·확장 역량 확인"),
    },
    "certificate": {
        1: ("{name}의 핵심 지식 체계는 무엇이고 이 직무에 왜 도움이 된다고 생각하나요?", "technical", "{name} 핵심 개념과 직무 연관성 이해 확인"),
        2: ("{name} 준비 과정에서 익힌 지식을 이 직무에 어떻게 적용할 수 있을까요?", "technical", "자격 관련 지식의 실무 적용 능력 확인"),
        3: ("{name}에서 다루는 원리를 실제 시스템 설계나 트러블슈팅, 대안 비교에 적용한다면 어떻게 활용하시겠어요?", "technical", "자격 지식 기반 심화 설계 및 문제 해결 적용력 확인"),
    },
    "education": {
        1: ("전공의 핵심 기초 개념 중 이 직무의 바탕이 되는 것은 무엇이고 왜 중요한가요?", "experience", "전공 기초 지식의 이해와 필요성 확인"),
        2: ("전공에서 배운 내용 중 이 직무에 가장 도움이 되는 것은 무엇인가요?", "experience", "전공 지식과 직무의 연결 확인"),
        3: ("전공 지식을 바탕으로 실제 문제나 설계의 한계를 분석하고 대안을 비교해 해결해 본 경험이 있나요?", "experience", "전공 지식의 심화 응용, 설계 및 트레이드오프 사고력 확인"),
    },
    "other": {
        1: ("'{name}'이(가) 팀과 업무에서 왜 중요하다고 생각하시나요?", "behavioral", "'{name}'의 의미와 중요성에 대한 기본 이해 확인"),
        2: ("'{name}'에 해당하는 본인의 경험을 사례로 설명해 주세요.", "behavioral", "'{name}' 관련 태도와 경험 확인"),
        3: ("'{name}'과(와) 관련해 이해관계나 기술·업무 방식이 충돌했을 때 어떤 기준으로 트레이드오프를 조율하고 해결했나요?", "behavioral", "'{name}' 관련 복합 상황 판단과 갈등·문제 해결 역량 확인"),
    },
}
_GENERAL = (
    Question("이 회사와 직무에 지원한 이유는 무엇인가요?", None, None, "behavioral", "지원 동기와 직무 이해도 확인",
             ("회사와 직무에서 끌린 점을 구체적으로", "본인의 경험과 연결하기")),
    Question("팀에서 의견이 달랐던 경험과 어떻게 해결했는지 말씀해 주세요.", None, None, "behavioral", "협업과 소통 방식 확인",
             _TIPS_EXPERIENCE),
    Question("최근에 새로 배운 기술과 학습 방법을 소개해 주세요.", None, None, "behavioral", "학습 태도와 성장 가능성 확인",
             ("무엇을 왜 배웠는지", "어떻게 적용해 봤는지")),
)


def _template_question(c: CriterionInfo, depth: int) -> Question:
    by_depth = _BY_CATEGORY.get(c.category, _BY_CATEGORY["other"])
    template, kind, intent = by_depth[depth]
    tip_group = "technical" if kind == "technical" else "other"
    tips = _TIPS_BY_DEPTH[(tip_group, depth)]
    return Question(template.format(name=c.name), c.id, c.name, kind, intent.format(name=c.name), tips, depth=depth)


def allowed(question: str, intent: str, tips: Sequence[str], blocklists: Sequence[Blocklist]) -> bool:
    """False when any blocklist matches the question, its intent or a tip."""
    detail = " ".join([intent, *tips])
    return all(check_criterion(question, detail, bl).allowed for bl in blocklists)


def _log_dropped(reason: str, source: str, criterion_id: int | None) -> None:
    """What may be logged about a question that was dropped: why, where it came from and which criterion it was for (a number of the
    job's own criteria). Never its text, which can quote the CV (D65)."""
    log.info("interview question dropped: reason=%s source=%s criterion_id=%s", reason, source, criterion_id)


def screen(questions: list[Question], blocklists: Sequence[Blocklist]) -> list[Question]:
    kept = [q for q in questions if allowed(q.question, q.intent, q.answer_tips, blocklists)]
    for q in questions:
        if q not in kept:
            _log_dropped("blocklist", "template", q.criterion_id)
    return kept


def interview_rules(
    criteria: list[CriterionInfo],
    blocklists: Sequence[Blocklist] = (),
    *,
    depths: Sequence[int] = DEPTHS,
    max_questions: int = MAX_BANK_QUESTIONS,
) -> list[Question]:
    """Template questions, screened like LLM ones (a criterion name could carry a blocked word)."""
    out = [_template_question(c, d) for c in criteria for d in depths]
    seen, unique = set(), []
    for q in [*out, *_GENERAL]:  # education/experience templates do not depend on the name: keep one each
        if q.question not in seen:
            seen.add(q.question)
            unique.append(q)
    return screen(unique, blocklists)[:max_questions]


# ── LLM ──


def cv_excerpts(masked_text: str, query: str, embedder: Embedder) -> list[str]:
    """Up to MAX_EXCERPTS chunks of the masked CV most relevant to the job."""
    passages = retrieve(query, cv_chunks(masked_text), embedder, k=MAX_EXCERPTS, prefer=("project", "experience"))
    return [p.chunk.text for p in passages]


def _llm_input(job_title: str, job_text: str, criteria: list[CriterionInfo], excerpts: list[str]) -> str:
    lines = [f"{c.id} | {c.name} | {c.category} | {c.description}" for c in criteria]
    parts = ["<job>", job_title, job_text, "</job>", "<criteria>", *lines, "</criteria>"]
    parts += ["<cv_excerpts>", "\n---\n".join(excerpts), "</cv_excerpts>"]
    return "\n".join(parts)


def _select_single_per_criterion(questions: list[Question], preferred_depth: int, limit: int) -> list[Question]:
    """Keep at most one question per criterion (preferring `preferred_depth`, then untagged/nearest) plus general questions."""
    rank = {preferred_depth: 0, None: 1}
    for idx, d in enumerate((2, 1, 3), start=2):
        rank.setdefault(d, idx)
    by_cid: dict[int, list[Question]] = {}
    order: list[int | None] = []
    general: list[Question] = []
    for q in questions:
        if q.criterion_id is None:
            general.append(q)
        else:
            if q.criterion_id not in by_cid:
                order.append(q.criterion_id)
            by_cid.setdefault(q.criterion_id, []).append(q)
    selected: list[Question] = []
    for cid in order:
        best = min(by_cid[cid], key=lambda item: rank.get(item.depth, 99))
        selected.append(best)
    selected.extend(general)
    if len(selected) < MIN_QUESTIONS:
        picked = set(id(q) for q in selected)
        for q in questions:
            if id(q) not in picked:
                selected.append(q)
                if len(selected) >= MIN_QUESTIONS:
                    break
    return selected[:limit]


def interview_llm(
    job_title: str,
    job_text: str,
    criteria: list[CriterionInfo],
    excerpts: list[str],
    masked_text: str,
    blocklists: Sequence[Blocklist],
    llm: LLMClient,
    *,
    depths: Sequence[int] = DEPTHS,
    fill_missing: bool = True,
    max_questions: int = MAX_BANK_QUESTIONS,
    single_depth: int | None = None,
) -> list[Question]:
    """Validated LLM questions. Raises LLMError when fewer than MIN_QUESTIONS survive the checks."""
    prompt = (PROMPT_DIR / "interview_questions.md").read_text(encoding="utf-8")
    out = llm.complete_json(prompt, _llm_input(job_title, job_text, criteria, excerpts), InterviewLlmOut, max_tokens=8000)
    names = {c.id: c.name for c in criteria}
    kept, seen = [], set()
    for q in out.questions:
        text = _clean(q.question, 300)
        if not text or text in seen:
            continue
        intent = _clean(q.intent, 200)
        tips = tuple(t for t in (_clean(x, 150) for x in q.answer_tips) if t)
        cid = q.criterion_id if q.criterion_id in names else None
        # Questions about protected attributes (age, family, origin, …) are dropped
        if not allowed(text, intent, tips, blocklists):
            _log_dropped("blocklist", "llm", cid)
            continue
        depth = q.depth if cid is not None and type(q.depth) is int and q.depth in DEPTHS else None
        verified = verify_quotes([q.cv_quote], masked_text) if q.cv_quote else []
        seen.add(text)
        kept.append(Question(text, cid, names.get(cid), q.kind, intent, tips, verified[0] if verified else None, depth))
    if len(kept) < MIN_QUESTIONS:
        raise LLMError(f"interview: only {len(kept)} usable questions")
    if fill_missing:
        covered = {(q.criterion_id, q.depth) for q in kept if q.criterion_id is not None and q.depth is not None}
        for c in criteria:
            for d in depths:
                if (c.id, d) in covered:
                    continue
                tq = _template_question(c, d)
                if tq.question in seen:
                    continue
                if not allowed(tq.question, tq.intent, tq.answer_tips, blocklists):
                    _log_dropped("blocklist", "template", c.id)
                    continue
                seen.add(tq.question)
                kept.append(tq)
                covered.add((c.id, d))
    if single_depth is not None:
        return _select_single_per_criterion(kept, single_depth, max_questions)
    return kept[:max_questions]


def make_questions(
    job_title: str,
    job_text: str,
    criteria: list[CriterionInfo],
    masked_text: str,
    embedder: Embedder,
    blocklists: Sequence[Blocklist],
    llm: LLMClient | None,
    *,
    depths: Sequence[int] = DEPTHS,
    fill_missing: bool = True,
    max_questions: int = MAX_BANK_QUESTIONS,
    single_depth: int | None = None,
) -> tuple[list[Question], str]:
    """`blocklists`: the criteria guardrail first, then the interview blocklist.
    (questions, method); method is "llm:<model>" or "rules". LLM failures fall back to the template."""
    if llm is not None:
        query = " ".join([job_title, *(c.name for c in criteria)])
        try:
            excerpts = cv_excerpts(masked_text, query, embedder)
            return (
                interview_llm(
                    job_title,
                    job_text,
                    criteria,
                    excerpts,
                    masked_text,
                    blocklists,
                    llm,
                    depths=depths,
                    fill_missing=fill_missing,
                    max_questions=max_questions,
                    single_depth=single_depth,
                ),
                f"llm:{llm.model}",
            )
        except LLMError as e:
            # The type only: the message of an LLM error can quote the model's output, which can quote CV lines (D65)
            log.warning("interview questions by LLM failed, using the template: %s", type(e).__name__)
    return interview_rules(criteria, blocklists, depths=depths, max_questions=max_questions), "rules"
