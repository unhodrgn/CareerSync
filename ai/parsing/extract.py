"""CV / JD structuring: LLM with JSON output when configured, rule-based otherwise.

Input text is already PII-masked. Experience months and skill normalization are always computed
in code, never trusted from the LLM.
"""
import logging
import re
from pathlib import Path

from ai.embedding.skills import SkillDictionary
from ai.llm.client import LLMClient, LLMError
from ai.parsing.profile import (
    Certificate,
    CvProfile,
    Education,
    Experience,
    JdAnalysis,
    JdProfile,
    Project,
    SuggestedCriterion,
)
from ai.parsing.sections import split_sections

log = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts" / "v1"
PROMPT_VERSION = "v1"


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


# ── Dates ──

_YM = r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*월?"
_RANGE = re.compile(
    _YM + r"\s*[~\-–—]\s*(?:" + _YM + r"|(현재|재직\s*중|재학\s*중|진행\s*중|present|now))",
    re.IGNORECASE,
)
_SINGLE = re.compile(_YM)


def _ym(year: str, month: str) -> str | None:
    y, m = int(year), int(month)
    return f"{y:04d}-{m:02d}" if 1950 <= y <= 2100 and 1 <= m <= 12 else None


def months_between(start: str | None, end: str | None, today: str) -> int:
    if not start:
        return 0
    end = end or today
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    return max(0, (ey - sy) * 12 + (em - sm) + 1)


def total_experience_months(experiences: list[Experience], today: str) -> int:
    """Total months with overlapping periods counted once."""
    spans = []
    for e in experiences:
        if not e.start:
            continue
        sy, sm = map(int, e.start.split("-"))
        ey, em = map(int, (e.end or today).split("-"))
        a, b = sy * 12 + sm, ey * 12 + em
        if b >= a:
            spans.append((a, b))
    total, cur = 0, None
    for a, b in sorted(spans):
        if cur is None or a > cur[1] + 1:
            if cur:
                total += cur[1] - cur[0] + 1
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    if cur:
        total += cur[1] - cur[0] + 1
    return total


# ── Rule-based CV structuring ──

_DEGREES = (("박사", "박사"), ("석사", "석사"), ("전문학사", "전문학사"), ("학사", "학사"), ("대학교", "학사"),
            ("대학", "학사"), ("고등학교", "고졸"), ("ph.d", "박사"), ("master", "석사"), ("bachelor", "학사"))
_MAJOR_END = ("학과", "학부", "공학", "전공", "과학", "학")


def _major(line: str) -> str:
    for word in re.findall(r"[가-힣A-Za-z]+", line):
        if "대학" in word or "고등학교" in word or word in ("학사", "석사", "박사", "전문학사"):
            continue
        if word.endswith(_MAJOR_END) and len(word) >= 3:
            return word
    m = re.search(r"(?:major|전공)\s*[:：]?\s*([A-Za-z가-힣 ]{2,40})", line, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _clean(line: str) -> str:
    return re.sub(r"^[\s•\-*·▪■□●○◆◇▶▷]+", "", line).strip()


def _experiences(text: str) -> list[Experience]:
    out = []
    lines = [l for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        m = _RANGE.search(line)
        if not m:
            continue
        start = _ym(m.group(1), m.group(2))
        end = _ym(m.group(3), m.group(4)) if m.group(3) else None
        rest = _clean(_RANGE.sub(" ", line))
        parts = [p.strip() for p in re.split(r"\s*[|/,]\s*|\s{2,}", rest) if p.strip()]
        desc = []
        for nxt in lines[i + 1 : i + 6]:
            if _RANGE.search(nxt):
                break
            desc.append(_clean(nxt))
        out.append(
            Experience(
                org=(parts[0] if parts else "")[:100],
                role=(" ".join(parts[1:]) if len(parts) > 1 else "")[:100],
                start=start,
                end=end,
                description="\n".join(desc)[:2000],
                source=line.strip()[:500],
            )
        )
    return out


def _projects(text: str, skills: SkillDictionary) -> list[Project]:
    out, cur = [], None
    for line in text.splitlines():
        if not line.strip():
            continue
        is_item = bool(_RANGE.search(line)) or not re.match(r"^\s*[•\-*·▪]", line)
        if is_item and (cur is None or cur["desc"]):
            if cur:
                out.append(cur)
            cur = {"name": _clean(_RANGE.sub(" ", line))[:200], "source": line.strip()[:500], "desc": []}
        elif cur is None:
            cur = {"name": _clean(line)[:200], "source": line.strip()[:500], "desc": []}
        else:
            cur["desc"].append(_clean(line))
    if cur:
        out.append(cur)
    projects = []
    for p in out:
        desc = "\n".join(p["desc"])
        projects.append(
            Project(
                name=p["name"],
                tech=skills.find_in_text(f"{p['name']}\n{desc}"),
                description=desc[:2000],
                source=p["source"],
            )
        )
    return projects


def _education(text: str) -> list[Education]:
    out = []
    for line in text.splitlines():
        low = line.lower()
        degree = next((d for k, d in _DEGREES if k in low), "")
        major = _major(line)
        if not degree and not major:
            continue
        school = re.search(r"([가-힣A-Za-z]+(?:대학교|대학|고등학교|University))", line)
        out.append(
            Education(
                school=school.group(1)[:100] if school else "",
                major=major[:100],
                degree=degree,
                source=line.strip()[:500],
            )
        )
    return out


def _certificates(text: str, sections_text: str | None, skills: SkillDictionary) -> list[Certificate]:
    out, seen = [], set()
    for name, line in skills.find_certificates(text):
        if name not in seen:
            seen.add(name)
            m = _SINGLE.search(line)
            out.append(Certificate(name=name, date=_ym(m.group(1), m.group(2)) if m else None, source=line.strip()[:500]))
    for line in (sections_text or "").splitlines():
        name = _clean(_SINGLE.sub(" ", line))
        if name and len(name) <= 40 and name not in seen and not any(name in s for s in seen):
            seen.add(name)
            m = _SINGLE.search(line)
            out.append(Certificate(name=name, date=_ym(m.group(1), m.group(2)) if m else None, source=line.strip()[:500]))
    return out


def structure_cv_rules(text: str, skills: SkillDictionary) -> CvProfile:
    sections = split_sections(text)
    by_key: dict[str, str] = {}
    for s in sections:
        by_key[s.key] = f"{by_key.get(s.key, '')}\n{s.text}".strip()
    exp_text = by_key.get("experience") or "\n".join(s.text for s in sections if s.key in ("other", "summary"))
    return CvProfile(
        skills=skills.find_in_text(text),
        experiences=_experiences(exp_text),
        projects=_projects(by_key.get("project", ""), skills),
        education=_education(by_key.get("education", "")),
        certificates=_certificates(text, by_key.get("certificate"), skills),
        summary="",
    )


# ── Public API ──


def normalize_profile(profile: CvProfile, skills: SkillDictionary) -> CvProfile:
    """Canonical skill names, deduplicated; project tech normalized the same way."""
    data = profile.model_copy(deep=True)
    data.skills = skills.normalize_list(data.skills)
    for p in data.projects:
        p.tech = skills.normalize_list(p.tech)
    return data


def structure_cv(masked_text: str, skills: SkillDictionary, llm: LLMClient | None) -> tuple[CvProfile, str]:
    """Returns (profile, method). Method is "llm:<model>" or "rules"."""
    if llm is not None:
        try:
            profile = llm.complete_json(
                _prompt("cv_structure.md"), f"<cv>\n{masked_text}\n</cv>", CvProfile, max_tokens=8000
            )
            return normalize_profile(profile, skills), f"llm:{llm.model}"
        except LLMError as e:
            log.warning("CV structuring by LLM failed, using rules: %s", e)
    return normalize_profile(structure_cv_rules(masked_text, skills), skills), "rules"


_YEARS = re.compile(r"(\d{1,2})\s*(?:년|years?)\s*(?:이상|\+|or more)?", re.IGNORECASE)


def analyze_jd_rules(title: str, text: str, min_years: int | None, skills: SkillDictionary) -> JdAnalysis:
    preferred_part = ""
    m = re.search(r"(우대\s*사항|우대|preferred)", text, re.IGNORECASE)
    required_part, preferred_part = (text[: m.start()], text[m.start():]) if m else (text, "")
    required = skills.find_in_text(f"{title}\n{required_part}")
    preferred = [s for s in skills.find_in_text(preferred_part) if s not in required]
    if min_years is None and (y := _YEARS.search(required_part)):
        min_years = int(y.group(1))
    certs = [name for name, _ in skills.find_certificates(text)]
    profile = JdProfile(
        required_skills=required, preferred_skills=preferred, min_years=min_years, certificates=certs, education=""
    )
    return JdAnalysis(profile=profile, criteria=suggest_criteria(profile))


def suggest_criteria(profile: JdProfile) -> list[SuggestedCriterion]:
    """A starting criteria set from the JD; the recruiter edits it and the guardrail checks it on save."""
    items: list[tuple[str, str, str, int]] = []
    for s in profile.required_skills[:3]:
        items.append((f"{s} 활용 능력", f"실무 또는 프로젝트에서 {s} 사용 경험", "skill", 3))
    if profile.min_years:
        items.append((f"경력 {profile.min_years}년 이상", "관련 직무 경력", "experience", 2))
    items.append(("프로젝트 경험", "직무와 관련된 프로젝트 경험과 본인의 역할", "project", 2))
    if profile.certificates:
        items.append(("관련 자격증", ", ".join(profile.certificates[:3]), "certificate", 1))
    total = sum(w for *_, w in items)
    weights = [max(1, round(100 * w / total)) for *_, w in items]
    weights[0] += 100 - sum(weights)
    return [
        SuggestedCriterion(name=n[:50], description=d[:500], category=c, weight=w)
        for (n, d, c, _), w in zip(items, weights, strict=True)
    ]


_CATEGORIES = {"skill", "experience", "project", "certificate", "education", "other"}


def _fix_weights(items: list[SuggestedCriterion]) -> list[SuggestedCriterion]:
    """Keep at most 10 valid items and rescale weights to integers summing to 100."""
    items = [i for i in items if i.category in _CATEGORIES and i.name.strip()][:10]
    if not items:
        return []
    total = sum(i.weight for i in items)
    weights = [max(1, round(100 * i.weight / total)) for i in items]
    weights[weights.index(max(weights))] += 100 - sum(weights)
    return [i.model_copy(update={"weight": w}) for i, w in zip(items, weights, strict=True)]


def analyze_jd(title: str, text: str, min_years: int | None, skills: SkillDictionary, llm: LLMClient | None) -> tuple[JdAnalysis, str]:
    if llm is not None:
        try:
            result = llm.complete_json(
                _prompt("jd_analyze.md"), f"<title>{title}</title>\n<jd>\n{text}\n</jd>", JdAnalysis, max_tokens=4000
            )
            result.profile.required_skills = skills.normalize_list(result.profile.required_skills)
            result.profile.preferred_skills = skills.normalize_list(result.profile.preferred_skills)
            if min_years is not None:
                result.profile.min_years = min_years
            result.criteria = _fix_weights(result.criteria) or suggest_criteria(result.profile)
            return result, f"llm:{llm.model}"
        except LLMError as e:
            log.warning("JD analysis by LLM failed, using rules: %s", e)
    return analyze_jd_rules(title, text, min_years, skills), "rules"
