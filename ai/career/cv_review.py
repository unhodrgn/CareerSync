"""CV self-check for the seeker: strengths and things to improve (docs/DECISIONS.md D25).

Rule checks read the masked CV text and the profile version under review. Every rule quote is a line of the
masked text. Some rule findings change what scoring can read (missing headings, periods it cannot read, skills or
certificates added only in the editor, a major it cannot verify, projects without technologies); they are marked
`affects_scoring` and are always included, also next to an LLM review.

The LLM sees only the masked text. A strength needs a `cv_quote` that passes `verify_quotes`, else it is dropped;
an improvement keeps its quote only if it passes. Every item (title and detail) must pass the criteria blocklist
and the interview blocklist; URLs are stripped. An LLM error, or no strength left, falls back to the rules.
"""
import logging
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field

from ai.career.interview import allowed
from ai.embedding.skills import SkillDictionary
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.evidence import verify_quotes
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import _RANGE, PROMPT_DIR, line_in_text, verified_experience
from ai.parsing.profile import CvProfile
from ai.parsing.sections import split_sections

log = logging.getLogger(__name__)

MAX_LLM_ITEMS = 5
MAX_STRENGTHS = 5
MAX_IMPROVEMENTS = 10
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|io|dev|net|kr)/\S*", re.IGNORECASE)
_SECTION_LABELS = {"experience": "Experience", "project": "Projects", "education": "Education", "skill": "Skills"}
# Missing these headings changes scoring: periods and skill uses are read from the 경력/프로젝트 sections
_SCORED_SECTIONS = ("experience", "project")


@dataclass(frozen=True)
class ReviewItem:
    title: str
    detail: str
    cv_quote: str | None = None
    affects_scoring: bool = False


@dataclass(frozen=True)
class CvReview:
    strengths: tuple[ReviewItem, ...]
    improvements: tuple[ReviewItem, ...]

    def to_dict(self) -> dict:
        return {"strengths": [asdict(i) for i in self.strengths], "improvements": [asdict(i) for i in self.improvements]}

    @classmethod
    def from_dict(cls, data: dict) -> "CvReview":
        return cls(
            strengths=tuple(ReviewItem(**i) for i in data.get("strengths", [])),
            improvements=tuple(ReviewItem(**i) for i in data.get("improvements", [])),
        )


def _entries(text: str, keys: Sequence[str]) -> list[list[str]]:
    """Entries of the given sections: a line with a period (YYYY.MM ~ …) starts an entry."""
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


def _span(months: int) -> str:
    years, rest = divmod(months, 12)
    y_str = f"{years} year{'s' if years != 1 else ''}"
    m_str = f"{rest} month{'s' if rest != 1 else ''}"
    if not years:
        return m_str
    return f"{y_str} {m_str}" if rest else y_str


# ── Rule checks ──


def scoring_checks(text: str, profile: CvProfile, skills: SkillDictionary) -> list[ReviewItem]:
    """Findings that change what scoring can read; always shown."""
    items: list[ReviewItem] = []
    sections = {s.key: s for s in split_sections(text)}
    for key in _SCORED_SECTIONS:
        if key not in sections:
            label = _SECTION_LABELS[key]
            items.append(ReviewItem(
                f"Missing '{label}' heading",
                f"No '{label}' heading was found in the CV. Put '{label}' on its own line so periods and used skills "
                "count toward scoring.",
                affects_scoring=True,
            ))
    if (exp := sections.get("experience")) is not None and not _RANGE.search(exp.text):
        first = next((line.strip() for line in exp.text.splitlines() if line.strip()), None)
        items.append(ReviewItem(
            "Unreadable experience dates",
            "Write work periods as 'YYYY.MM ~ YYYY.MM' (or '~ present' for current roles) so experience duration counts toward scoring.",
            first,
            True,
        ))
    missing_skills = [s for s in profile.skills if s.strip() and not skills.lines_mentioning(s, text)]
    if missing_skills:
        items.append(ReviewItem(
            "Skills missing from CV text",
            f"{', '.join(missing_skills[:8])}: Skills added only on the edit screen are absent from the PDF text and do not count toward scoring. "
            "Add them to your PDF and re-upload.",
            affects_scoring=True,
        ))
    missing_certs = [c.name for c in profile.certificates if c.name.strip() and not line_in_text(c.name, text)]
    if missing_certs:
        items.append(ReviewItem(
            "Certificates missing from CV text",
            f"{', '.join(missing_certs[:5])}: Certificates absent from the PDF text do not count toward scoring. Add them to your PDF and re-upload.",
            affects_scoring=True,
        ))
    if "education" in sections or profile.education:
        verified = [
            e for e in profile.education
            if e.major.strip() and line_in_text(e.source, text) and line_in_text(e.major, e.source)
        ]
        if not verified:
            items.append(ReviewItem(
                "Major could not be verified",
                "Include your major (e.g., 'Computer Science') on your education line so postings requiring a major can evaluate it.",
                affects_scoring=True,
            ))
    no_tech = [e[0] for e in _entries(text, ("project",)) if not skills.find_in_text("\n".join(e))]
    for line in no_tech[:2]:
        items.append(ReviewItem(
            "Project without listed technologies",
            "List the technologies used in this project so your experience with them counts toward skill scoring.",
            line,
            True,
        ))
    return items


def _extra_checks(text: str) -> list[ReviewItem]:
    """Advice that does not change scoring."""
    items = []
    if "education" not in {s.key for s in split_sections(text)}:
        items.append(ReviewItem("Missing 'Education' heading", "If you have education history, list your school, major, and dates under an 'Education' heading."))
    flat = [e for e in _entries(text, ("experience", "project")) if len(e) > 1]
    for entry in [e for e in flat if not any(re.search(r"\d", line) for line in e[1:])][:2]:
        items.append(ReviewItem(
            "Quantify results with numbers",
            "Include measurable outcomes (throughput, improvement percentage, users served, etc.) alongside your work to make impact clear.",
            entry[0],
        ))
    return items


def _strengths(text: str, profile: CvProfile, skills: SkillDictionary, today: str) -> list[ReviewItem]:
    items = []
    months, lines = verified_experience(text, profile.experiences, today)
    if months:
        items.append(ReviewItem("Clear employment periods", f"Verified approximately {_span(months)} of experience from your CV.", lines[0]))
    entries = _entries(text, ("experience", "project"))
    used = []
    for skill in skills.find_in_text(text):
        hits = [e[0] for e in entries if skills.lines_mentioning(skill, "\n".join(e))]
        if len(hits) >= 2:
            used.append((len(hits), skill, hits[0]))
    for count, skill, line in sorted(used, key=lambda x: -x[0])[:3]:
        items.append(ReviewItem(f"{skill} hands-on experience", f"Used {skill} across {count} experience and project entries.", line))
    certs = list(dict.fromkeys(skills.find_certificates(text)))
    if certs:
        names = list(dict.fromkeys(name for name, _ in certs))
        items.append(ReviewItem("Verified certificates", f"Listed in CV: {', '.join(names[:3])}.", certs[0][1].strip()))
    with_tech = [e[0] for e in _entries(text, ("project",)) if skills.find_in_text("\n".join(e))]
    if len(with_tech) >= 2:
        items.append(ReviewItem("Projects with clear tech stacks", f"Found {len(with_tech)} project entries specifying technologies used.", with_tech[0]))
    return items[:MAX_STRENGTHS]


def review_rules(text: str, profile: CvProfile, skills: SkillDictionary, today: str) -> CvReview:
    improvements = scoring_checks(text, profile, skills) + _extra_checks(text)
    return CvReview(tuple(_strengths(text, profile, skills, today)), tuple(improvements[:MAX_IMPROVEMENTS]))


# ── LLM ──


class _LlmItem(BaseModel):
    title: str = Field(max_length=100)
    detail: str = Field(max_length=500)
    cv_quote: str | None = Field(None, max_length=500)


class CvReviewLlmOut(BaseModel):
    strengths: list[_LlmItem] = Field(default_factory=list)
    improvements: list[_LlmItem] = Field(default_factory=list)


def _clean(text: str, limit: int) -> str:
    return " ".join(_URL.sub("", text).split())[:limit]


def _validate(raw: list[_LlmItem], text: str, blocklists: Sequence[Blocklist], quote_required: bool) -> list[ReviewItem]:
    out = []
    for item in raw:
        title, detail = _clean(item.title, 60), _clean(item.detail, 300)
        if not title or not detail:
            continue
        quote = item.cv_quote.strip() if item.cv_quote else None
        if quote and not verify_quotes([quote], text):
            quote = None
        if quote_required and quote is None:
            log.info("CV review strength dropped (quote not in the CV): %s", title)
            continue
        if not allowed(title, detail, (), blocklists):
            log.info("CV review item dropped by a blocklist: %s", title)
            continue
        out.append(ReviewItem(title, detail, quote))
        if len(out) == MAX_LLM_ITEMS:
            break
    return out


def review_llm(text: str, blocklists: Sequence[Blocklist], llm: LLMClient) -> CvReview:
    """The LLM part only (no rule findings); raises LLMError when nothing valid is left."""
    out = llm.complete_json(
        (PROMPT_DIR / "cv_review.md").read_text(encoding="utf-8"), f"<cv>\n{text}\n</cv>", CvReviewLlmOut, max_tokens=3000
    )
    strengths = _validate(out.strengths, text, blocklists, quote_required=True)
    if not strengths:
        raise LLMError("no verified strength left")
    return CvReview(tuple(strengths), tuple(_validate(out.improvements, text, blocklists, quote_required=False)))


def combine(llm_part: CvReview, text: str, profile: CvProfile, skills: SkillDictionary) -> CvReview:
    """An LLM review with the rule findings that affect scoring first (duplicate titles dropped)."""
    rules = scoring_checks(text, profile, skills)
    titles = {i.title for i in rules}
    improvements = rules + [i for i in llm_part.improvements if i.title not in titles]
    return CvReview(llm_part.strengths, tuple(improvements[:MAX_IMPROVEMENTS]))


def make_llm_review(text: str, blocklists: Sequence[Blocklist], llm: LLMClient) -> tuple[CvReview | None, str]:
    """(LLM part, method) or (None, "rules") when the LLM failed."""
    try:
        return review_llm(text, blocklists, llm), f"llm:{llm.model}"
    except LLMError as e:
        log.warning("CV review by LLM failed, using rules: %s", type(e).__name__)
        return None, "rules"
