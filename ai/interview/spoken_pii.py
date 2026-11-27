"""Mask personal data in transcribed speech before any model sees it (CLAUDE.md AI rule 3; docs/DECISIONS.md D39, D53).

Speech is not a CV, so `ai.parsing.pii.mask_pii` is not called as a whole: it masks everything after the word 주소 on a
line and looks for a name at the top of the "document", which would damage a spoken technical answer. This module
reuses what is safe to share and leaves `mask_pii` and the CV masking untouched:
- the placeholder tokens and the surname list of `ai.parsing.pii`, so a spoken name reads like a CV name;
- its name patterns for the account name (spaces between syllables, family name first or last, romanized Korean).
On top of that it covers what only speech has: spoken digits ("공일공 …"), a spoken email ("… 골뱅이 …") and a name the
candidate introduces ("저는 김철수입니다", "my name is …").

Best effort, rule based, no model. A name said without any introduction is not found, like in D39; the stored text is
therefore still treated as possibly personal (D53).
"""
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# Private on purpose: the same tables and patterns as the CV masking, imported instead of copied (see the module docstring)
from ai.parsing.pii import _DETECT_SURNAMES, _PATTERNS, NAME_TOKEN, _name_patterns

_TOKENS = {kind: token for kind, token, _ in _PATTERNS}
EMAIL, URL, RRN, PHONE, BIRTH = _TOKENS["email"], _TOKENS["url"], _TOKENS["rrn"], _TOKENS["phone"], _TOKENS["birth"]
# Common spoken roles/titles after "저는 …입니다" whose leading syllable is a Korean surname
_NON_NAME_ROLES = frozenset(
    "이력서 지원서 지원자 구직자 성명 이름 이메일 주소 연락처 전화 생년월일 주민번호 링크 "
    "백엔드 프론트엔드 풀스택 개발자 엔지니어 디자이너 기획자 연구원 연구생 인턴 신입 신입생 "
    "경력직 정규직 계약직 지원자 고객 서비스 전문가 주니어 시니어 추천인 추천자 담당자 지도교수 "
    "팀장 부장 과장 차장 대리 사원 대표 학생 대학생 졸업 졸업생 박사 석사 학사 전공자 담당 선배 후배 "
    "동료 리더 사회자 면접자 설계자 운영자 관리자 교육생 수료생 안녕하세요 성별 국적 병역 장애".split()
)

_EN_NON_NAME_ROLES = frozenset({
    "a", "an", "the", "senior", "junior", "backend", "frontend", "fullstack", "full-stack",
    "software", "developer", "engineer", "designer", "manager", "lead", "principal", "architect",
    "student", "intern", "applicant", "candidate", "korean", "english", "seoul", "korea",
    "java", "spring", "boot", "python", "fastapi", "django", "docker", "kubernetes", "aws", "gcp",
    "sorry", "glad", "happy", "excited", "ready", "sure", "fine", "good", "great", "interested",
    "working", "currently", "building", "using", "not", "looking", "applying", "familiar",
    "experience", "experienced", "project", "projects", "team", "company", "role", "system",
})

_SPOKEN_DIGITS = "공영일이삼사오육칠팔구"
_EN_DIGIT_WORD = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)"
_COMPOUND = "|".join(re.escape(s) for s in sorted(_DETECT_SURNAMES, key=len, reverse=True) if len(s) == 2)
_SINGLE = "".join(re.escape(s) for s in sorted(_DETECT_SURNAMES) if len(s) == 1)
_SURNAME = rf"(?:{_COMPOUND}|[{_SINGLE}])"
_BIRTH_DATE = r"(?:19|20)\d{2}\s*(?:년|[.\-/])\s*\d{1,2}\s*(?:월|[.\-/])\s*\d{1,2}\s*일?"
_AFTER_NAME = r"(?=\s*(?:입니다|이에요|예요|이라고|라고|이고|인데|이며|[,.]|$))"

_RRN_RE = re.compile(r"(?<!\d)\d{6}\s?-?\s?[1-4]\d{6}(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_EMAIL_SPOKEN_RE = re.compile(
    r"[\w.\-]+\s*(?:골뱅이|앳)\s*[\w\-]+(?:\s*(?:점|닷|\bdot\b|\.)\s*[\w\-]+)+"
    r"|\b[\w-]+(?:\s*(?:\.|닷|\bdot\b)\s*[\w-]+)*\s*\bat\b\s*[\w-]+(?:\s*(?:닷|\bdot\b)\s*[\w-]+)+",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?82[-.\s]?)?(?:0?1[016-9]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"
    r"|(?<!\d)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"
)
_PHONE_SPOKEN_RE = re.compile(
    rf"(?<![가-힣])(?:공일공|영일영)(?:[\s-]*[{_SPOKEN_DIGITS}]){{7,8}}"
    rf"|(?<!\S)(?:[{_SPOKEN_DIGITS}](?:\s+|-)){{7,}}[{_SPOKEN_DIGITS}](?!\S)"
    rf"|(?i:(?<!\w)(?:{_EN_DIGIT_WORD}(?:\s+|-)){{7,}}{_EN_DIGIT_WORD}(?!\w))"
)
_BIRTH_RE = re.compile(
    rf"(?:(?:생년월일|생일|출생)[은는이가:\s]*){_BIRTH_DATE}|{_BIRTH_DATE}(?=\s*(?:에\s*)?(?:태어났|출생))"
    r"|(?i:\b(?:date of birth|birthday|dob)\b\s*(?:is|:)?\s*)(?:\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
)
# "이름은 철수입니다", "성함은 홍길동"
_LABELED_NAME_RE = re.compile(rf"(?P<pre>(?:이름|성함|성명)\s*(?:은|는|이|가)?\s*)(?P<name>[가-힣]{{2,4}}){_AFTER_NAME}")
# "저는 김철수입니다" (a surname, then 1-2 syllables): "저는 개발자입니다" is not a name and stays
_INTRO_NAME_RE = re.compile(rf"(?P<pre>(?:저는|전|제\s*이름은)\s*)(?P<name>{_SURNAME}[가-힣]{{1,2}})(?=\s*(?:입니다|이에요|예요|이라고|라고\s*합니다))")
# Keep <name> case-sensitive so lowercase words ("and", "I") are not swallowed after an introduced name
_ENGLISH_NAME_RE = re.compile(
    r"(?P<pre>(?i:\b(?:my\s+name\s+is|call\s+me)\s+))(?P<name>(?:[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)?|[a-z]{2,15}))"
    r"|(?P<pre2>(?i:\b(?:i\s+am|i'm|this\s+is)\s+))(?P<name2>[A-Z][A-Za-z'-]+\s+[A-Z][A-Za-z'-]+)"
)


@dataclass(frozen=True)
class SpokenMaskResult:
    text: str
    kinds: dict[str, int] = field(default_factory=dict)  # what was masked and how often; never the text itself

    @property
    def changed(self) -> bool:
        return bool(self.kinds)


def _account_patterns(names: Iterable[str]) -> list[re.Pattern[str]]:
    account = [n.strip() for n in names if len(n.strip()) >= 2]
    patterns = [re.compile(r"\s*".join(map(re.escape, n.replace(" ", "")))) for n in account]  # "김 지 원", "김지원"
    return patterns + _name_patterns(account, [])  # romanized, family name first or last, diacritics


def mask_spoken(text: str, names: Sequence[str] = ()) -> SpokenMaskResult:
    """Mask personal data in one transcript. `names`: the seeker's account name(s), hidden wherever they occur."""
    kinds: Counter[str] = Counter()

    def sub(pattern: re.Pattern[str], placeholder: str, kind: str, source: str) -> str:
        out, count = pattern.subn(placeholder, source)
        if count:
            kinds[kind] += count
        return out

    def sub_name(pattern: re.Pattern[str], source: str, stop: frozenset[str] = frozenset()) -> str:
        def replace(m: re.Match[str]) -> str:
            pre = m.group("pre") if "pre" in m.groupdict() and m.group("pre") is not None else m.group("pre2")
            raw = m.group("name") if "name" in m.groupdict() and m.group("name") is not None else m.group("name2")
            parts = raw.strip().split()
            if any(part.lower() in stop for part in parts):
                return m.group(0)
            kinds["name"] += 1
            return pre + NAME_TOKEN

        return pattern.sub(replace, source)

    out = text or ""
    out = sub(_RRN_RE, RRN, "rrn", out)
    out = sub(_EMAIL_RE, EMAIL, "email", out)
    out = sub(_EMAIL_SPOKEN_RE, EMAIL, "email", out)
    out = sub(_URL_RE, URL, "url", out)
    out = sub(_PHONE_RE, PHONE, "phone", out)
    out = sub(_PHONE_SPOKEN_RE, PHONE, "phone", out)
    out = sub(_BIRTH_RE, BIRTH, "birth_date", out)
    out = sub_name(_LABELED_NAME_RE, out, _NON_NAME_ROLES)
    out = sub_name(_INTRO_NAME_RE, out, _NON_NAME_ROLES)
    out = sub_name(_ENGLISH_NAME_RE, out, _EN_NON_NAME_ROLES)
    for pattern in _account_patterns(names):
        out = sub(pattern, NAME_TOKEN, "name", out)
    return SpokenMaskResult(" ".join(out.split()), dict(kinds))
