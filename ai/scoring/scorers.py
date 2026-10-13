"""One scorer per criterion category. Each returns a CriterionResult with evidence from the CV.

Rule scorers (skill, experience, certificate, education) are deterministic: the same CV and
criterion always give the same score. Only project and other criteria use the LLM rubric, and
they fall back to keyword + similarity retrieval when no LLM is configured.

Seekers can edit the structured profile, but not the masked CV text. Rule scorers therefore give
points only for what is found in `candidate.text`; the profile only says what to look for, and
evidence is always a line of the text (PROJECT_DOCUMENTATION.md issue 3).
"""
import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from ai.embedding.model import Embedder, cosine
from ai.embedding.skills import SkillDictionary
from ai.guardrails.evidence import verify_quotes
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import _RANGE, PROMPT_DIR, line_in_text, verified_experience
from ai.parsing.sections import Chunk, split_sections
from ai.scoring.retrieval import best_lines, cv_chunks, retrieve
from ai.scoring.types import Candidate, Criterion, CriterionResult, JobContext, nearest_level

log = logging.getLogger(__name__)

NO_EVIDENCE = "근거를 찾지 못함"

# Skill scoring
SKILL_LISTED = 70  # the skill is on the CV
SKILL_USE_BONUS = 10  # per experience or project that uses it
SIMILAR_STRONG, SIMILAR_WEAK = 0.85, 0.80  # embedding similarity to a related skill
PARTIAL_STRONG, PARTIAL_WEAK = 50, 30
# Certificates that say nothing about job skills
_LANGUAGE_CERTS = {"TOEIC", "OPIc"}
# Education: only majors the criterion names count as related; 이공계/STEM criteria use this list
_STEM_MAJOR = (
    "공학", "수학", "물리", "화학", "과학", "컴퓨터", "소프트웨어", "전산", "통계", "생명", "생물",
    "engineering", "science", "math",
)
_STEM_WORDS = ("이공계", "이공", "stem")
# Education criteria saved before a major was required ("관련 전공"): same score for everyone
EDUCATION_NEUTRAL_SCORE = 50
_MAJOR_SUFFIXES = ("공학", "학과", "학부", "전공", "학")
_NOT_MAJORS = {"관련", "유관", "해당", "동등", "전공", "학과", "학부", "대학", "입학", "재학", "휴학", "이공계", "이공"}


@dataclass
class ScoringContext:
    job: JobContext
    skills: SkillDictionary
    embedder: Embedder
    llm: LLMClient | None
    today: str  # YYYY-MM, for ongoing roles
    _chunks: list[Chunk] | None = None

    def chunks(self, candidate: Candidate) -> list[Chunk]:
        if self._chunks is None:
            self._chunks = cv_chunks(candidate.text)
        return self._chunks


def _result(
    c: Criterion, score: float, reason: str, evidence: list[str], method: str, evidence_required: bool = True
) -> CriterionResult:
    s = max(0, min(100, round(score)))
    if s > 0 and not evidence and evidence_required:
        # Every non-zero score carries evidence (explainability target)
        s, reason = 0, NO_EVIDENCE
    return CriterionResult(c.id, s, nearest_level(s), reason, tuple(evidence[:3]), method)


# ── skill ──


def _entries(text: str) -> list[list[str]]:
    """Entries of the 경력 and 프로젝트 sections of the CV text: a line with a period
    (YYYY.MM ~ …) starts a new entry; a section without periods is one entry."""
    entries = []
    for s in split_sections(text):
        if s.key not in ("experience", "project"):
            continue
        cur: list[str] = []
        for line in (raw.strip() for raw in s.text.splitlines()):
            if not line:
                continue
            if cur and _RANGE.search(line):
                entries.append(cur)
                cur = []
            cur.append(line)
        if cur:
            entries.append(cur)
    return entries


def _uses(skill: str, candidate: Candidate, ctx: ScoringContext) -> list[str]:
    """First line of each 경력/프로젝트 entry of the CV text that mentions the skill."""
    return [e[0] for e in _entries(candidate.text) if ctx.skills.lines_mentioning(skill, "\n".join(e))]


def score_skill(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    wanted = ctx.skills.find_in_text(f"{c.name}\n{c.description}")
    if not wanted:
        # No known technology named: judge it like a free-text criterion
        return score_retrieval(c, candidate, ctx)
    # Skills the CV text mentions; the seeker-edited `profile.skills` is not trusted
    have = set(ctx.skills.find_in_text(candidate.text))
    scores, reasons, evidence = [], [], []
    for skill in wanted:
        lines = ctx.skills.lines_mentioning(skill, candidate.text)
        if lines:
            uses = _uses(skill, candidate, ctx)
            scores.append(min(100, SKILL_LISTED + SKILL_USE_BONUS * len(uses)))
            reasons.append(f"{skill} 보유" + (f", 경력·프로젝트 {len(uses)}건에서 사용" if uses else ""))
            evidence.extend(lines[:2])
            continue
        related = _most_similar(skill, sorted(have), ctx.embedder)
        if related and related[1] >= SIMILAR_WEAK:
            name, sim = related
            scores.append(PARTIAL_STRONG if sim >= SIMILAR_STRONG else PARTIAL_WEAK)
            reasons.append(f"{skill} 직접 경험은 없으나 유사 기술 {name} 보유")
            evidence.extend(ctx.skills.lines_mentioning(name, candidate.text)[:1])
        else:
            scores.append(0)
            reasons.append(f"{skill} 경험 확인 안 됨")
    evidence = list(dict.fromkeys(evidence))
    return _result(c, sum(scores) / len(scores), "; ".join(reasons), evidence, "rule:skill")


def _most_similar(skill: str, have: list[str], embedder: Embedder) -> tuple[str, float] | None:
    if not have:
        return None
    vecs = embedder.embed([skill, *have])
    sims = [(name, cosine(vecs[0], v)) for name, v in zip(have, vecs[1:], strict=True)]
    return max(sims, key=lambda x: x[1])


# ── experience ──

# "3년", "10년차", "3~5년" (lower bound), "5+ years", "1년 6개월"; not a year like "2020년"
_YEARS = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:[~\-–]\s*\d{1,2}\s*)?\+?\s*(?:년|years?)(?:\s*(\d{1,2})\s*(?:개월|months?))?", re.IGNORECASE
)
_MONTHS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:개월|months?)", re.IGNORECASE)


def required_years(text: str) -> float | None:
    """Years of experience a criterion asks for: months count as fractions, 신입 is 0, None if not stated."""
    if m := _YEARS.search(text):
        return int(m.group(1)) + int(m.group(2) or 0) / 12
    if m := _MONTHS.search(text):
        return int(m.group(1)) / 12
    if "신입" in text:
        return 0
    return None


def _span(months: int) -> str:
    years, rest = divmod(months, 12)
    if not years:
        return f"{rest}개월"
    return f"{years}년 {rest}개월" if rest else f"{years}년"


def score_experience(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    required = required_years(f"{c.name} {c.description}")
    if required is None:
        # The job's min_experience_years; NULL means 신입 가능 (0 years)
        required = ctx.job.min_experience_years or 0
    # Periods read from the CV text, not the seeker-edited dates
    months, evidence = verified_experience(candidate.text, candidate.profile.experiences, ctx.today)
    if required == 0:
        # No experience required (신입): everyone meets it, so no CV evidence is needed
        reason = "경력 요건 없음(신입)" + (f", 확인된 경력 약 {_span(months)}" if months else "")
        return _result(c, 100, reason, evidence, "rule:experience", evidence_required=False)
    if not months:
        return _result(c, 0, "확인된 경력 없음", [], "rule:experience")
    target_months = round(12 * required)
    reason = f"확인된 경력 약 {_span(months)} (요구 {_span(target_months)})"
    return _result(c, 100 * months / target_months, reason, evidence, "rule:experience")


# ── certificate ──


def score_certificate(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    named = [name for name, _ in ctx.skills.find_certificates(f"{c.name}\n{c.description}")]
    # Profile certificates count only when their line is in the CV text and names them
    certs = [
        x
        for x in candidate.profile.certificates
        if x.name and line_in_text(x.source, candidate.text) and x.name.casefold() in x.source.casefold()
    ]
    known = {name: line for name, line in ctx.skills.find_certificates(candidate.text)}
    if named:
        scores, reasons, evidence = [], [], []
        for name in dict.fromkeys(named):
            if name in known:
                scores.append(100)
                reasons.append(f"{name} 보유")
                evidence.append(known[name].strip())
            else:
                scores.append(0)
                reasons.append(f"{name} 확인 안 됨")
        return _result(c, sum(scores) / len(scores), "; ".join(reasons), evidence, "rule:certificate")
    # Generic "관련 자격증": count job-related certificates
    related = [n for n in known if n not in _LANGUAGE_CERTS]
    others = [x for x in certs if x.name and not any(x.name in n or n in x.name for n in known)]
    points = len(related) + 0.5 * len(others)
    score = 0 if points == 0 else 35 if points < 1 else 70 if points < 2 else 100
    names = related + [x.name for x in others]
    evidence = [known[n].strip() for n in related] + [x.source.strip() for x in others]
    reason = f"자격증 {len(names)}개 확인: {', '.join(names[:3])}" if names else "확인된 자격증 없음"
    return _result(c, score, reason, evidence, "rule:certificate")


# ── education ──


def wanted_majors(text: str) -> list[str]:
    """Majors named in a criterion, e.g. "컴퓨터공학 관련 전공" → ["컴퓨터공학"], "경영학과" → ["경영"]."""
    majors = []
    for word in re.findall(r"[가-힣]{2,}", text):
        if word in _NOT_MAJORS or not word.endswith(_MAJOR_SUFFIXES):
            continue
        core = word.removesuffix("전공").removesuffix("학과").removesuffix("학부")
        if len(core) >= 2 and core not in _NOT_MAJORS:
            majors.append(core)
    return list(dict.fromkeys(majors))


def education_target(name: str, description: str) -> tuple[list[str], bool]:
    """(majors named, whether 이공계/STEM is asked). An education criterion must name one of them;
    criteria_service rejects the save otherwise."""
    text = f"{name}\n{description}"
    return wanted_majors(text), any(w in text.lower() for w in _STEM_WORDS)


def score_education(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    """Major relevance against the majors the criterion names; no built-in list of related majors.
    School names are never scored (blocked by the guardrail as a criterion too)."""
    wanted, stem = education_target(c.name, c.description)
    if not wanted and not stem:
        # Saved before a major was required: nothing to compare, so the same neutral score for everyone
        reason = "전공 미지정: 평가 기준에 전공이 없어 중립 점수"
        return _result(c, EDUCATION_NEUTRAL_SCORE, reason, [], "rule:education", evidence_required=False)
    best, best_line, best_reason = 0, "", "확인된 전공 정보 없음"
    for e in candidate.profile.education:
        major = e.major.lower()
        # The major counts only when its line is in the CV text and names it
        if not major or not line_in_text(e.source, candidate.text) or major not in e.source.lower():
            continue
        if any(w.lower() in major for w in wanted):
            s, why = 100, f"요구 전공과 일치하는 {e.major}"
        elif stem and any(k in major for k in _STEM_MAJOR):
            s, why = 100, f"이공계 전공 {e.major}"
        else:
            s, why = 30, f"요구 전공과 다른 전공 {e.major}"
        if s > best:
            best, best_line, best_reason = s, e.source.strip(), why
    return _result(c, best, best_reason, [best_line] if best_line else [], "rule:education")


# ── project / other: LLM rubric, retrieval fallback ──


class RubricOut(BaseModel):
    level: Literal[0, 25, 50, 75, 100]
    reason: str = Field(max_length=300)
    evidence: list[str] = Field(default_factory=list, max_length=3)


def _query(c: Criterion, ctx: ScoringContext) -> str:
    q = f"{c.name}. {c.description}"
    if c.category == "other" and ctx.job.talent_profile:
        q += f" {ctx.job.talent_profile}"
    return q


def score_llm(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    assert ctx.llm is not None
    passages = retrieve(_query(c, ctx), ctx.chunks(candidate), ctx.embedder, k=4, prefer=("project", "experience"))
    if not passages:
        return _result(c, 0, NO_EVIDENCE, [], f"llm:{ctx.llm.model}")
    excerpts = "\n---\n".join(p.chunk.text for p in passages)
    company = f"회사: {ctx.job.company_name}\n인재상: {ctx.job.talent_profile}\n" if ctx.job.talent_profile else ""
    user = (
        f"{company}공고: {ctx.job.title}\n"
        f"평가 항목: {c.name}\n평가 기준: {c.description or '(설명 없음)'}\n\n"
        f"<cv_excerpts>\n{excerpts}\n</cv_excerpts>"
    )
    system = (PROMPT_DIR / "rubric_score.md").read_text(encoding="utf-8")
    for _attempt in range(2):
        try:
            out = ctx.llm.complete_json(system, user, RubricOut, max_tokens=2000)
        except LLMError as e:
            log.warning("rubric scoring failed for criterion %s: %s", c.id, e)
            break
        if out.level == 0:
            return _result(c, 0, out.reason or "관련 내용 없음", [], f"llm:{ctx.llm.model}")
        verified = verify_quotes(out.evidence, candidate.text)
        if verified:
            return _result(c, out.level, out.reason, verified, f"llm:{ctx.llm.model}")
        log.info("criterion %s: no evidence quote survived the check, retrying once", c.id)
    return score_retrieval(c, candidate, ctx)


# Relevance (0..1, see retrieval.Passage) → score, without an LLM
_RETRIEVAL_STEPS = ((0.6, 75), (0.4, 50), (0.2, 25))


def score_retrieval(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    query = _query(c, ctx)
    passages = retrieve(query, ctx.chunks(candidate), ctx.embedder, k=1, prefer=("project", "experience"))
    if not passages:
        return _result(c, 0, NO_EVIDENCE, [], "retrieval")
    top = passages[0]
    score = next((s for t, s in _RETRIEVAL_STEPS if top.relevance >= t), 0)
    lines = best_lines(top.chunk.text, query)
    if not score or not lines:
        return _result(c, 0, "관련 내용을 찾지 못함", [], "retrieval")
    return _result(c, score, f"관련 내용 확인 (키워드·유사도 기반 추정): {lines[0][:60]}", lines, "retrieval")


def score_one(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    match c.category:
        case "skill":
            return score_skill(c, candidate, ctx)
        case "experience":
            return score_experience(c, candidate, ctx)
        case "certificate":
            return score_certificate(c, candidate, ctx)
        case "education":
            return score_education(c, candidate, ctx)
        case _:
            return score_llm(c, candidate, ctx) if ctx.llm is not None else score_retrieval(c, candidate, ctx)
