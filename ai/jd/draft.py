"""JD draft for a company's draft job: LLM text when configured, a template otherwise (docs/DECISIONS.md D24).

The draft is never saved here; the company edits it. The LLM returns fixed parts (intro, 주요 업무, 자격 요건,
우대 사항) and the description is assembled in code. Every sentence — LLM or template — is screened: pay or money
amounts, URLs, email addresses and phone numbers drop the sentence, and so does any hit of the criteria blocklist
(data/blocklist.yaml). Dropped sentences are returned with the reason. An LLM error, or no 자격 요건 left after
screening, falls back to the template. Only company data goes in; no seeker data, so no PII.
"""
import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ai.embedding.skills import SkillDictionary
from ai.guardrails.blocklist import Blocklist
from ai.guardrails.criteria import check_criterion
from ai.llm.client import LLMClient, LLMError
from ai.parsing.extract import PROMPT_DIR

log = logging.getLogger(__name__)

MAX_ITEMS = 8
MAX_ITEM_CHARS = 200
MAX_INTRO_CHARS = 500
MAX_DESCRIPTION_CHARS = 10000

EMPLOYMENT_LABELS = {"full_time": "정규직", "contract": "계약직", "intern": "인턴"}
SECTION_TITLES = (("responsibilities", "주요 업무"), ("requirements", "자격 요건"), ("preferred", "우대 사항"))

# Pay words and amounts ("4,000만 원", "5천만원"); "5억 건" (a count) and "3원칙" are not amounts
_MONEY = re.compile(
    r"연봉|급여|월급|시급|일급|임금|성과급|인센티브|스톡\s*옵션"
    r"|\d[\d,.]*\s*(?:만|천|백만|억)?\s*원(?!칙|활|리|인|격|본|래)|₩|\bKRW\b|\$\s*\d",
    re.IGNORECASE,
)
# A scheme or www, or a domain followed by a path ("Node.js", "Socket.io" stay), as in ai/career/roadmap.py
_URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|io|dev|net|kr)/\S*", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)0\d{1,2}[-.\s)]?\d{3,4}[-.\s]?\d{4}(?!\d)")

REASON_MONEY = "급여·금액 정보는 AI가 쓰지 않습니다. 필요하면 직접 입력하세요."
REASON_CONTACT = "링크·이메일·전화번호는 넣지 않습니다."
REASON_LENGTH = f"{MAX_ITEM_CHARS}자를 넘는 문장입니다."


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    description: str = ""
    techs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DraftInput:
    title: str
    employment_type: str = "full_time"
    min_experience_years: int | None = None
    keywords: tuple[str, ...] = ()
    notes: str = ""
    company_name: str = ""
    company_intro: str = ""
    talent_profile: str = ""
    projects: tuple[ProjectInfo, ...] = ()


@dataclass(frozen=True)
class Dropped:
    text: str
    reason: str


@dataclass
class JdDraft:
    intro: str
    responsibilities: list[str]
    requirements: list[str]
    preferred: list[str]
    dropped: list[Dropped] = field(default_factory=list)

    @property
    def description(self) -> str:
        """The JD text, sections in the order `analyze_jd` reads them (자격 요건 before 우대 사항)."""
        parts = [self.intro] if self.intro else []
        for key, title in SECTION_TITLES:
            if items := getattr(self, key):
                parts.append(title + "\n" + "\n".join(f"- {i}" for i in items))
        return "\n\n".join(parts)[:MAX_DESCRIPTION_CHARS]


class JdDraftLlmOut(BaseModel):
    intro: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)


def _norm(text: str) -> str:
    return " ".join(text.split()).lstrip("-•·*▪ ").strip()


def drop_reason(text: str, blocklist: Blocklist) -> str | None:
    """Why a sentence may not be in the draft, or None when it may."""
    if _MONEY.search(text):
        return REASON_MONEY
    if _URL.search(text) or _EMAIL.search(text) or _PHONE.search(text):
        return REASON_CONTACT
    result = check_criterion(text, "", blocklist)
    if not result.allowed:
        hit = result.hits[0]
        return f"{hit.reason} ({hit.law_ref})"
    return None


def screen(draft: JdDraft, blocklist: Blocklist) -> JdDraft:
    """Normalize, de-duplicate and cap the items; drop sentences that fail `drop_reason`."""
    dropped: list[Dropped] = []
    seen: set[str] = set()

    def keep(text: str, limit: int) -> bool:
        if len(text) > limit:
            dropped.append(Dropped(text, REASON_LENGTH if limit == MAX_ITEM_CHARS else f"{limit}자를 넘는 소개입니다."))
            return False
        if reason := drop_reason(text, blocklist):
            dropped.append(Dropped(text, reason))
            return False
        return True

    intro = _norm(draft.intro)
    intro = intro if intro and keep(intro, MAX_INTRO_CHARS) else ""
    lists = {}
    for key, _ in SECTION_TITLES:
        items = []
        for raw in getattr(draft, key):
            text = _norm(raw)
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            if keep(text, MAX_ITEM_CHARS) and len(items) < MAX_ITEMS:
                items.append(text)
        lists[key] = items
    return JdDraft(intro=intro, dropped=[*draft.dropped, *dropped], **lists)


# ── Template (AI_MODE=rules, or fallback) ──


def _skills(inp: DraftInput, skills: SkillDictionary) -> tuple[list[str], list[str]]:
    """Keywords (canonical names where known) and project technologies not among them."""
    wanted = skills.normalize_list(list(inp.keywords))
    techs = skills.normalize_list([t for p in inp.projects for t in p.techs])
    lower = {w.lower() for w in wanted}
    return wanted, [t for t in techs if t.lower() not in lower]


def draft_rules(inp: DraftInput, skills: SkillDictionary) -> JdDraft:
    wanted, extra_techs = _skills(inp, skills)
    employment = EMPLOYMENT_LABELS.get(inp.employment_type, "")
    who = f"{inp.company_name}에서" if inp.company_name else "함께"
    intro = f"{who} {inp.title}" + (f"({employment})" if employment else "") + "을(를) 찾습니다."
    if inp.notes.strip():
        intro += " " + _norm(inp.notes)

    responsibilities = []
    for p in inp.projects[:3]:
        techs = ", ".join(skills.normalize_list(list(p.techs))[:5])
        responsibilities.append(f"{p.name} 프로젝트 개발 및 운영" + (f" ({techs})" if techs else ""))
    responsibilities.append(f"{inp.title} 직무 관련 기능 설계·개발 및 유지보수")
    responsibilities.append("코드 리뷰와 문서화를 통한 팀 협업")

    years = inp.min_experience_years
    requirements = [f"관련 경력 {years}년 이상" if years else "신입 지원 가능"]
    requirements += [f"{s} 실무 또는 프로젝트 경험" for s in wanted[:5]]
    if not wanted:
        requirements.append(f"{inp.title} 직무 관련 지식과 경험")
    requirements.append("원활한 커뮤니케이션과 협업 능력")

    preferred = [f"{t} 사용 경험" for t in extra_techs[:4]]
    preferred.append("스스로 문제를 정의하고 해결해 본 경험")
    if inp.talent_profile.strip() and len(inp.talent_profile) <= 150:
        preferred.append(f"회사의 인재상에 공감하는 분: {_norm(inp.talent_profile)}")
    return JdDraft(intro=intro, responsibilities=responsibilities, requirements=requirements, preferred=preferred)


# ── LLM ──


def _llm_input(inp: DraftInput) -> str:
    years = "" if inp.min_experience_years is None else str(inp.min_experience_years)
    projects = "\n".join(f"- {p.name}: {p.description} (기술: {', '.join(p.techs)})" for p in inp.projects)
    return (
        f"<job>\ntitle: {inp.title}\nemployment_type: {EMPLOYMENT_LABELS.get(inp.employment_type, inp.employment_type)}\n"
        f"min_experience_years: {years}\n</job>\n"
        f"<keywords>\n{', '.join(inp.keywords)}\n</keywords>\n"
        f"<notes>\n{inp.notes}\n</notes>\n"
        f"<company>\nname: {inp.company_name}\nintro: {inp.company_intro}\n인재상: {inp.talent_profile}\n</company>\n"
        f"<projects>\n{projects}\n</projects>"
    )


def draft_llm(inp: DraftInput, llm: LLMClient) -> JdDraft:
    out = llm.complete_json(
        (PROMPT_DIR / "jd_draft.md").read_text(encoding="utf-8"), _llm_input(inp), JdDraftLlmOut, max_tokens=3000
    )
    return JdDraft(
        intro=out.intro, responsibilities=out.responsibilities, requirements=out.requirements, preferred=out.preferred
    )


def make_draft(inp: DraftInput, skills: SkillDictionary, blocklist: Blocklist, llm: LLMClient | None) -> tuple[JdDraft, str]:
    """The screened draft and its method (`llm:<model>` or `rules`)."""
    if llm is not None:
        try:
            draft = screen(draft_llm(inp, llm), blocklist)
            if draft.requirements:
                return draft, f"llm:{llm.model}"
            log.warning("JD draft by LLM has no requirements left after screening, using the template")
        except LLMError as e:
            log.warning("JD draft by LLM failed, using the template: %s", e)
    return screen(draft_rules(inp, skills), blocklist), "rules"
