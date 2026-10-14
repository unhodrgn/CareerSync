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
_SECTION_LABELS = {"experience": "경력", "project": "프로젝트", "education": "학력", "skill": "기술"}
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
    if not years:
        return f"{rest}개월"
    return f"{years}년 {rest}개월" if rest else f"{years}년"


# ── Rule checks ──


def scoring_checks(text: str, profile: CvProfile, skills: SkillDictionary) -> list[ReviewItem]:
    """Findings that change what scoring can read; always shown."""
    items: list[ReviewItem] = []
    sections = {s.key: s for s in split_sections(text)}
    for key in _SCORED_SECTIONS:
        if key not in sections:
            label = _SECTION_LABELS[key]
            items.append(ReviewItem(
                f"'{label}' 제목 없음",
                f"이력서에서 '{label}' 제목을 찾지 못했습니다. {label}이(가) 있다면 '{label}' 제목을 한 줄에 따로 적어야 "
                "기간과 사용 기술이 평가에 반영됩니다.",
                affects_scoring=True,
            ))
    if (exp := sections.get("experience")) is not None and not _RANGE.search(exp.text):
        first = next((line.strip() for line in exp.text.splitlines() if line.strip()), None)
        items.append(ReviewItem(
            "경력 기간을 읽을 수 없음",
            "경력 기간을 'YYYY.MM ~ YYYY.MM'(재직 중이면 '~ 현재') 형식으로 적어야 경력 기간이 평가에 반영됩니다.",
            first,
            True,
        ))
    missing_skills = [s for s in profile.skills if s.strip() and not skills.lines_mentioning(s, text)]
    if missing_skills:
        items.append(ReviewItem(
            "이력서 원문에 없는 기술",
            f"{', '.join(missing_skills[:8])}: 수정 화면에서만 추가한 기술은 PDF 원문에 없어 평가에 반영되지 않습니다. "
            "반영하려면 PDF에 적은 뒤 다시 업로드하세요.",
            affects_scoring=True,
        ))
    missing_certs = [c.name for c in profile.certificates if c.name.strip() and not line_in_text(c.name, text)]
    if missing_certs:
        items.append(ReviewItem(
            "이력서 원문에 없는 자격증",
            f"{', '.join(missing_certs[:5])}: PDF 원문에 없는 자격증은 평가에 반영되지 않습니다. PDF에 적은 뒤 다시 업로드하세요.",
            affects_scoring=True,
        ))
    if "education" in sections or profile.education:
        verified = [
            e for e in profile.education
            if e.major.strip() and line_in_text(e.source, text) and line_in_text(e.major, e.source)
        ]
        if not verified:
            items.append(ReviewItem(
                "전공을 확인할 수 없음",
                "학력 줄에 전공(예: '컴퓨터공학과')을 함께 적어야 전공 요건이 있는 공고에서 평가됩니다.",
                affects_scoring=True,
            ))
    no_tech = [e[0] for e in _entries(text, ("project",)) if not skills.find_in_text("\n".join(e))]
    for line in no_tech[:2]:
        items.append(ReviewItem(
            "기술 스택이 없는 프로젝트",
            "프로젝트에 사용한 기술을 적으면 해당 기술의 사용 경험으로 평가됩니다.",
            line,
            True,
        ))
    return items


def _extra_checks(text: str) -> list[ReviewItem]:
    """Advice that does not change scoring."""
    items = []
    if "education" not in {s.key for s in split_sections(text)}:
        items.append(ReviewItem("'학력' 제목 없음", "학력이 있다면 '학력' 제목 아래에 학교, 전공, 기간을 적으세요."))
    flat = [e for e in _entries(text, ("experience", "project")) if len(e) > 1]
    for entry in [e for e in flat if not any(re.search(r"\d", line) for line in e[1:])][:2]:
        items.append(ReviewItem(
            "성과를 수치로 보여 주기",
            "맡은 일과 함께 결과를 숫자(처리량, 개선 비율, 사용자 수 등)로 적으면 기여도가 더 잘 드러납니다.",
            entry[0],
        ))
    return items


def _strengths(text: str, profile: CvProfile, skills: SkillDictionary, today: str) -> list[ReviewItem]:
    items = []
    months, lines = verified_experience(text, profile.experiences, today)
    if months:
        items.append(ReviewItem("경력 기간이 명확함", f"이력서에서 약 {_span(months)}의 경력 기간이 확인됩니다.", lines[0]))
    entries = _entries(text, ("experience", "project"))
    used = []
    for skill in skills.find_in_text(text):
        hits = [e[0] for e in entries if skills.lines_mentioning(skill, "\n".join(e))]
        if len(hits) >= 2:
            used.append((len(hits), skill, hits[0]))
    for count, skill, line in sorted(used, key=lambda x: -x[0])[:3]:
        items.append(ReviewItem(f"{skill} 활용 경험", f"{skill}을(를) 경력·프로젝트 {count}건에서 사용했습니다.", line))
    certs = list(dict.fromkeys(skills.find_certificates(text)))
    if certs:
        names = list(dict.fromkeys(name for name, _ in certs))
        items.append(ReviewItem("자격증 보유", f"{', '.join(names[:3])} 자격증이 이력서에 있습니다.", certs[0][1].strip()))
    with_tech = [e[0] for e in _entries(text, ("project",)) if skills.find_in_text("\n".join(e))]
    if len(with_tech) >= 2:
        items.append(ReviewItem("기술 스택이 드러난 프로젝트", f"사용 기술이 적힌 프로젝트가 {len(with_tech)}건 있습니다.", with_tech[0]))
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
        log.warning("CV review by LLM failed, using rules: %s", e)
        return None, "rules"
