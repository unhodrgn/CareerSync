"""One scorer per criterion category. Each returns a CriterionResult with evidence from the CV.

Rule scorers (skill, experience, certificate, education) are deterministic: the same CV and
criterion always give the same score. Only project and other criteria use the LLM rubric. Without an
LLM (AI_MODE=rules, D28): project criteria are scored from the entries of the 프로젝트 section, other
criteria by keyword + similarity retrieval, with a neutral score when retrieval finds nothing to judge.
In AI_MODE=llm an LLM failure still falls back to retrieval. Skill criteria naming no skill of the
dictionary are looked up in the CV text by name (0 when absent), in both modes.

Seekers can edit the structured profile, but not the masked CV text. Rule scorers therefore give
points only for what is found in `candidate.text`; the profile only says what to look for, and
evidence is always a line of the text (PROJECT_DOCUMENTATION.md issue 3).
"""
import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from ai.embedding.model import Embedder
from ai.embedding.skills import SkillDictionary
from ai.guardrails.evidence import verify_quotes
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import _RANGE, PROMPT_DIR, line_in_text, stated_experience, verified_experience
from ai.parsing.sections import Chunk, split_sections
from ai.scoring.retrieval import best_lines, cv_chunks, keywords, retrieve
from ai.scoring.types import Candidate, Criterion, CriterionResult, JobContext, nearest_level

log = logging.getLogger(__name__)

NO_EVIDENCE = "No evidence found"

# Skill scoring
SKILL_LISTED = 70  # the skill is on the CV
SKILL_USE_BONUS = 10  # per experience or project that uses it
# A missing skill whose `related` group in data/skills.yaml has a skill on the CV (D27); no embedding similarity
RELATED_SCORE = 50
# Certificates that say nothing about job skills
_LANGUAGE_CERTS = {"TOEIC", "OPIc"}
# Education: only majors the criterion names count as related; 이공계/STEM criteria use this list
_STEM_MAJOR = (
    "공학", "수학", "물리", "화학", "과학", "컴퓨터", "소프트웨어", "전산", "통계", "생명", "생물",
    "engineering", "science", "math", "statistics", "physics", "chemistry", "biology", "computing", "informatics",
)
_STEM_WORDS = ("이공계", "이공", "stem")
# Education criteria saved before a major was required ("관련 전공"): same score for everyone
EDUCATION_NEUTRAL_SCORE = 50
# AI_MODE=rules (D27): project entries of the CV text; same neutral score when a free-text criterion cannot be judged
PROJECT_LISTED, PROJECT_RELEVANT, PROJECT_RELEVANT_MANY = 25, 50, 75
RULES_NEUTRAL_SCORE = 50
RULES_NEUTRAL_REASON = "Cannot be evaluated by rules alone"
# Skill criteria naming no skill of the dictionary (D28): found on the CV → at least this; not found → 0
UNLISTED_SKILL_FOUND = 50
UNLISTED_SKILL_MISSING = "Not confirmed in CV"
_MAJOR_SUFFIXES = ("공학", "학과", "학부", "전공", "학")
_NOT_MAJORS = {"관련", "유관", "해당", "동등", "전공", "학과", "학부", "대학", "입학", "재학", "휴학", "이공계", "이공"}
_EN_NON_MAJORS = frozenset({
    "related", "relevant", "equivalent", "similar", "any", "other", "preferred", "required",
    "must", "have", "with", "from", "an", "a", "the", "or", "and", "of", "in", "for", "to", "at",
    "major", "majors", "degree", "degrees", "field", "fields", "discipline", "disciplines",
    "bachelor", "bachelors", "master", "masters", "doctorate", "phd", "associate",
    "graduate", "graduated", "diploma", "year", "years", "university", "college", "school",
    "education", "academic", "background", "stem",
})
_EN_MAJOR_HEADS = (
    "engineering", "science", "sciences", "mathematics", "math", "statistics",
    "physics", "chemistry", "biology", "economics", "administration", "management",
    "finance", "accounting", "design", "architecture", "analytics", "informatics",
    "computing", "security",
)


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


def _entries(text: str, keys: tuple[str, ...] = ("experience", "project")) -> list[list[str]]:
    """Entries of the 경력 and 프로젝트 sections of the CV text (or of `keys`): a line with a period
    (YYYY.MM ~ …) starts a new entry; a section without periods is one entry."""
    entries = []
    for s in split_sections(text):
        if s.key not in keys:
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


def _skill_uses(skill: str, text: str, skills: SkillDictionary) -> list[str]:
    """Headings of CV experience and project entries that mention the skill."""
    return [entry[0] for entry in _entries(text) if skills.lines_mentioning(skill, "\n".join(entry))]


def _direct_skill_score(skill: str, uses: list[str]) -> tuple[int, str]:
    return (
        min(100, SKILL_LISTED + SKILL_USE_BONUS * len(uses)),
        f"{skill} listed" + (f", used in {len(uses)} experience/project {'entry' if len(uses) == 1 else 'entries'}" if uses else ""),
    )


@dataclass(frozen=True)
class SkillTraceItem:
    skill: str
    score: int
    entries: tuple[str, ...] = ()
    match: str = "direct"
    related_skill: str | None = None


@dataclass(frozen=True)
class DirectSkillTrace:
    skills: tuple[SkillTraceItem, ...]
    base: int = SKILL_LISTED
    bonus: int = SKILL_USE_BONUS
    cap: int = 100


def _score_named_skills(
    criterion: Criterion, wanted: list[str], text: str, dictionary: SkillDictionary
) -> tuple[CriterionResult, DirectSkillTrace]:
    have = set(dictionary.find_in_text(text))
    traces, reasons, evidence = [], [], []
    for skill in wanted:
        lines = dictionary.lines_mentioning(skill, text)
        if lines:
            uses = _skill_uses(skill, text, dictionary)
            score, reason = _direct_skill_score(skill, uses)
            traces.append(SkillTraceItem(skill, score, tuple(uses)))
            reasons.append(reason)
            evidence.extend(lines[:2])
            continue
        related = [name for name in dictionary.related_to(skill) if name in have]
        if related:
            name = related[0]
            traces.append(SkillTraceItem(skill, RELATED_SCORE, match="related", related_skill=name))
            reasons.append(f"No direct {skill} experience, but related skill {name} found")
            evidence.extend(dictionary.lines_mentioning(name, text)[:1])
        else:
            traces.append(SkillTraceItem(skill, 0, match="missing"))
            reasons.append(f"{skill} not confirmed")
    score = sum(item.score for item in traces) / len(traces)
    result = _result(criterion, score, "; ".join(reasons), list(dict.fromkeys(evidence)), "rule:skill")
    return result, DirectSkillTrace(tuple(traces))


def verified_direct_skill_trace(
    criterion: Criterion, text: str, skills: SkillDictionary, stored: CriterionResult
) -> DirectSkillTrace | None:
    """Expose replayed named-skill inputs only when they reproduce the persisted result."""
    wanted = skills.find_in_text(f"{criterion.name}\n{criterion.description}")
    if stored.method != "rule:skill" or criterion.category != "skill" or not wanted:
        return None
    replayed, trace = _score_named_skills(criterion, wanted, text, skills)
    if replayed != stored or any(quote not in text for quote in stored.evidence):
        return None
    return trace


def score_skill(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    wanted = ctx.skills.find_in_text(f"{c.name}\n{c.description}")
    if not wanted:
        return score_unlisted_skill(c, candidate, ctx)
    # Read the masked CV text rather than seeker-edited profile fields.
    result, _ = _score_named_skills(c, wanted, candidate.text, ctx.skills)
    return result


# ── experience ──

# "3년", "10년차", "3~5년" (lower bound), "5+ years", "1년 6개월"; not a year like "2020년"
_YEARS = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:[~\-–]\s*\d{1,2}\s*)?\+?\s*(?:년|years?)(?:\s*(\d{1,2})\s*(?:개월|months?))?", re.IGNORECASE
)
_MONTHS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:개월|months?)", re.IGNORECASE)


def required_years(text: str) -> float | None:
    """Years of experience a criterion asks for: months count as fractions, 신입/entry-level is 0, None if not stated."""
    if m := _YEARS.search(text):
        return int(m.group(1)) + int(m.group(2) or 0) / 12
    if m := _MONTHS.search(text):
        return int(m.group(1)) / 12
    low = text.lower()
    if "신입" in text or re.search(r"\b(?:entry[\s\-]?level|no experience|new grad(?:uate)?)\b", low):
        return 0
    return None


def _span(months: int) -> str:
    years, rest = divmod(months, 12)
    y_str = f"{years} year{'s' if years != 1 else ''}"
    m_str = f"{rest} month{'s' if rest != 1 else ''}"
    if not years:
        return m_str
    return f"{y_str} {m_str}" if rest else y_str


def score_experience(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    """Employment periods in the CV text first (`verified_experience`); only when the text has none, the total
    the CV states (`stated_experience`, method rule:experience-stated). Same formula for both."""
    required = required_years(f"{c.name} {c.description}")
    if required is None:
        # The job's min_experience_years; NULL means entry-level eligible (0 years)
        required = ctx.job.min_experience_years or 0
    # Periods read from the CV text, not the seeker-edited dates
    months, evidence = verified_experience(candidate.text, candidate.profile.experiences, ctx.today)
    if required == 0:
        # No experience required (entry-level): everyone meets it, so no CV evidence is needed
        reason = "No experience requirement (entry-level)" + (f", ~{_span(months)} verified" if months else "")
        return _result(c, 100, reason, evidence, "rule:experience", evidence_required=False)
    target_months = round(12 * required)
    if not evidence and (stated := stated_experience(candidate.text)) is not None:
        # No employment period in the CV text: the total the CV states, reported as stated, not verified (D48)
        stated_months, line = stated
        reason = f"Stated experience {_span(stated_months) if stated_months else '0 years'} (required {_span(target_months)}); employment periods not verified"
        return _result(c, 100 * stated_months / target_months, reason, [line], "rule:experience-stated")
    if not months:
        return _result(c, 0, "No verified experience found", [], "rule:experience")
    reason = f"~{_span(months)} verified experience (required {_span(target_months)})"
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
                reasons.append(f"{name} verified")
                evidence.append(known[name].strip())
            else:
                scores.append(0)
                reasons.append(f"{name} not confirmed")
        return _result(c, sum(scores) / len(scores), "; ".join(reasons), evidence, "rule:certificate")
    # Generic "Relevant certificates": count job-related certificates
    related = [n for n in known if n not in _LANGUAGE_CERTS]
    others = [x for x in certs if x.name and not any(x.name in n or n in x.name for n in known)]
    points = len(related) + 0.5 * len(others)
    score = 0 if points == 0 else 35 if points < 1 else 70 if points < 2 else 100
    names = related + [x.name for x in others]
    evidence = [known[n].strip() for n in related] + [x.source.strip() for x in others]
    reason = f"{len(names)} certificate{'s' if len(names) != 1 else ''} verified: {', '.join(names[:3])}" if names else "No certificates verified"
    return _result(c, score, reason, evidence, "rule:certificate")


# ── education ──


def _clean_en_major(raw: str) -> str:
    words = [w.strip(".,;:()") for w in raw.lower().split()]
    while words and words[0] in _EN_NON_MAJORS:
        words.pop(0)
    while words and words[-1] in _EN_NON_MAJORS:
        words.pop()
    return " ".join(words)


def wanted_majors(text: str) -> list[str]:
    """Majors named in a criterion, e.g. '컴퓨터공학 관련 전공' -> ['컴퓨터공학'], 'Computer science major' -> ['computer science']."""
    majors = []
    for word in re.findall(r"[가-힣]{2,}", text):
        if word in _NOT_MAJORS or not word.endswith(_MAJOR_SUFFIXES):
            continue
        core = word.removesuffix("전공").removesuffix("학과").removesuffix("학부")
        if len(core) >= 2 and core not in _NOT_MAJORS:
            majors.append(core)
    heads = "|".join(_EN_MAJOR_HEADS)
    for m in re.finditer(rf"\b(?:[a-z]+(?:[ \-][a-z]+)?\s+)?(?:{heads})\b", text, re.IGNORECASE):
        if phrase := _clean_en_major(m.group(0)):
            majors.append(phrase)
    for m in re.finditer(r"\b([a-z][a-z\- ]{1,35}?)\s+majors?\b", text, re.IGNORECASE):
        for part in re.split(r"\s*(?:,|/|\bor\b|\band\b)\s*", m.group(1), flags=re.IGNORECASE):
            if phrase := _clean_en_major(part):
                majors.append(phrase)
    for m in re.finditer(r"\b(?:major|degree)\s+in\s+([a-z][a-z\-,/ ]{1,50})", text, re.IGNORECASE):
        for part in re.split(r"\s*(?:,|/|\bor\b|\band\b)\s*", m.group(1), flags=re.IGNORECASE):
            if phrase := _clean_en_major(part):
                majors.append(phrase)
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
        reason = "No major specified: criterion names no major, neutral score applied"
        return _result(c, EDUCATION_NEUTRAL_SCORE, reason, [], "rule:education", evidence_required=False)
    best, best_line, best_reason = 0, "", "No education major verified in CV"
    for e in candidate.profile.education:
        major = e.major.lower()
        # The major counts only when its line is in the CV text and names it
        if not major or not line_in_text(e.source, candidate.text) or major not in e.source.lower():
            continue
        if any(w.lower() in major for w in wanted):
            s, why = 100, f"Matches required major: {e.major}"
        elif stem and any(k in major for k in _STEM_MAJOR):
            s, why = 100, f"STEM major: {e.major}"
        else:
            s, why = 30, f"Different major from requirement: {e.major}"
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
    company = f"Company: {ctx.job.company_name}\nIdeal candidate: {ctx.job.talent_profile}\n" if ctx.job.talent_profile else ""
    user = (
        f"{company}Job: {ctx.job.title}\n"
        f"Criterion: {c.name}\nCriteria details: {c.description or '(no description)'}\n\n"
        f"<cv_excerpts>\n{excerpts}\n</cv_excerpts>"
    )
    system = (PROMPT_DIR / "rubric_score.md").read_text(encoding="utf-8")
    for _attempt in range(2):
        try:
            out = ctx.llm.complete_json(system, user, RubricOut, max_tokens=2000)
        except LLMError as e:
            log.warning("rubric scoring failed for criterion %s: %s", c.id, type(e).__name__)
            break
        if out.level == 0:
            return _result(c, 0, out.reason or "No relevant content", [], f"llm:{ctx.llm.model}")
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
        return _result(c, 0, "No relevant content found", [], "retrieval")
    return _result(c, score, f"Relevant content found (keyword/similarity estimate): {lines[0][:60]}", lines, "retrieval")


def _retrieval_or_neutral(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    """Retrieval for vague `other` criteria; in AI_MODE=rules one it cannot judge gets the same neutral score for
    everyone (D28)."""
    result = score_retrieval(c, candidate, ctx)
    if result.score == 0 and ctx.llm is None:
        return _result(c, RULES_NEUTRAL_SCORE, RULES_NEUTRAL_REASON, [], "rule:neutral", evidence_required=False)
    return result


def _term_lines(term: str, text: str) -> list[str]:
    """CV lines containing `term`; a term starting or ending with a Latin letter or digit must sit on a word
    boundary ("Excel" does not match "Excellent")."""
    pattern = re.compile(
        (r"(?<![0-9a-z])" if re.match(r"[0-9a-z]", term) else "")
        + re.escape(term)
        + (r"(?![0-9a-z])" if re.search(r"[0-9a-z]$", term) else ""),
        re.IGNORECASE,
    )
    return [line.strip() for line in text.splitlines() if line.strip() and pattern.search(line)]


def score_unlisted_skill(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    """Skill criterion naming no skill of data/skills.yaml (D28), in both AI modes.

    The name's keywords (and the description's) are looked up in the CV text. None found → 0. Found → the retrieval
    score, at least UNLISTED_SKILL_FOUND when a keyword of the name itself is on a CV line (that line is evidence).
    Never the neutral score: that is only for vague `other` criteria.
    """
    name_terms = keywords(c.name)
    terms = list(dict.fromkeys([*name_terms, *keywords(c.description)]))
    if not any(_term_lines(t, candidate.text) for t in terms):
        return _result(c, 0, UNLISTED_SKILL_MISSING, [], "retrieval")
    result = score_retrieval(c, candidate, ctx)
    name_lines = [line for t in name_terms for line in _term_lines(t, candidate.text)]
    if not name_lines or result.score >= UNLISTED_SKILL_FOUND:
        return result
    evidence = list(dict.fromkeys([*name_lines[:2], *result.evidence]))
    return _result(c, UNLISTED_SKILL_FOUND, f"Found '{c.name}' in CV: {name_lines[0][:60]}", evidence, "retrieval")


def score_project_rules(c: Criterion, candidate: Candidate, ctx: ScoringContext) -> CriterionResult:
    """Project criterion without an LLM (D27), from the entries of the project section of the CV text.

    An entry is relevant when it mentions a skill the criterion or the job (title, JD) names, or a keyword of the
    criterion. Any entry: PROJECT_LISTED; one relevant entry: PROJECT_RELEVANT; two or more: PROJECT_RELEVANT_MANY.
    """
    entries = _entries(candidate.text, ("project",))
    if not entries:
        return _result(c, 0, "No project entries found in CV", [], "rule:project")
    named = ctx.skills.find_in_text(f"{c.name}\n{c.description}\n{ctx.job.title}\n{ctx.job.description}")
    terms = [w for w in keywords(f"{c.name} {c.description}") if w not in ("프로젝트", "project", "projects")]

    def relevant(entry: list[str]) -> bool:
        body = "\n".join(entry)
        low = body.lower()
        return any(ctx.skills.lines_mentioning(s, body) for s in named) or any(t in low for t in terms)

    hits = [e for e in entries if relevant(e)]
    if not hits:
        reason = f"{len(entries)} project {'entry' if len(entries) == 1 else 'entries'} found (no job-related tech or keywords confirmed)"
        return _result(c, PROJECT_LISTED, reason, [e[0] for e in entries[:2]], "rule:project")
    score = PROJECT_RELEVANT_MANY if len(hits) >= 2 else PROJECT_RELEVANT
    reason = f"{len(hits)} job-related project {'entry' if len(hits) == 1 else 'entries'} confirmed ({len(entries)} total)"
    return _result(c, score, reason, [e[0] for e in hits[:3]], "rule:project")


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
        case "project":
            return score_llm(c, candidate, ctx) if ctx.llm is not None else score_project_rules(c, candidate, ctx)
        case _:
            return score_llm(c, candidate, ctx) if ctx.llm is not None else _retrieval_or_neutral(c, candidate, ctx)
