"""Privacy and safety guards of the interview PoC.

1. `mask_spoken_pii`: replaces personal data in transcribed speech with placeholders BEFORE the text reaches the LLM, the
   page or the logs (CareerSync AI rule 3: the LLM sees only masked text). Best effort, rule based, no model: like
   docs/DECISIONS.md D39 it covers email, phone, URL, resident registration number, labeled birth date and names that the
   candidate introduces or that are configured. A name said without any introduction is not found.
2. `screen_followup` / `screen_closing`: checks on what the LLM wrote, in the spirit of the interview blocklist of D21
   (no questions about protected attributes) and AI rule 5 (the AI never says who passes). They check the form of the
   output, not the meaning of anything the candidate said. A failed check means the PoC speaks a fixed fallback line.

This module is standalone: it does not import `app.*` or `ai.*`, so the lists below are a small copy of the intent of
`data/interview_blocklist.yaml`, not the file itself.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

# ── Masking ──

NAME = "[이름]"
EMAIL = "[이메일]"
PHONE = "[전화번호]"
URL = "[URL]"
RRN = "[주민번호]"
BIRTH = "[생년월일]"

_SPOKEN_DIGITS = "공영일이삼사오육칠팔구"
_SURNAMES = (
    "김이박최정강조윤장임한오서신권황안송류홍전고문양손배백허유남심노하곽성차주우구민나진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예경봉사부가"
)
_BIRTH_DATE = r"(?:19|20)\d{2}\s*(?:년|[.\-/])\s*\d{1,2}\s*(?:월|[.\-/])\s*\d{1,2}\s*일?"

_RRN_RE = re.compile(r"(?<!\d)\d{6}\s?-?\s?[1-4]\d{6}(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_EMAIL_SPOKEN_RE = re.compile(r"[\w.\-]+\s*(?:골뱅이|앳)\s*[\w\-]+(?:\s*(?:점|\.)\s*[\w\-]+)+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[-.\s]?)?(?:0?1[016-9]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_PHONE_SPOKEN_RE = re.compile(
    rf"(?<![가-힣])(?:공일공|영일영)(?:[\s-]*[{_SPOKEN_DIGITS}]){{7,8}}"
    rf"|(?<!\S)(?:[{_SPOKEN_DIGITS}](?:\s+|-)){{7,}}[{_SPOKEN_DIGITS}](?!\S)"
)
_BIRTH_RE = re.compile(rf"(?:(?:생년월일|생일|출생)[은는이가:\s]*){_BIRTH_DATE}|{_BIRTH_DATE}(?=\s*(?:에\s*)?(?:태어났|출생))")
# "이름은 철수입니다", "성함은 홍길동"
_LABELED_NAME_RE = re.compile(
    r"(?P<pre>(?:이름|성함|성명)\s*(?:은|는|이|가)?\s*)(?P<name>[가-힣]{2,4})(?=\s*(?:입니다|이에요|예요|이라고|라고|이고|인데|이며|[,.]|$))"
)
# "저는 김철수입니다" (surname first, 2-4 syllables): "저는 개발자입니다" is not a name and stays
_INTRO_NAME_RE = re.compile(
    rf"(?P<pre>(?:저는|전|제\s*이름은)\s*)(?P<name>[{_SURNAMES}][가-힣]{{1,2}})(?=\s*(?:입니다|이에요|예요|이라고|라고\s*합니다))"
)
_ENGLISH_NAME_RE = re.compile(r"(?P<pre>\bmy\s+name\s+is\s+)(?P<name>[A-Za-z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)?)", re.IGNORECASE)


@dataclass(frozen=True)
class MaskResult:
    text: str
    kinds: dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.kinds)


def _configured_names_re(names: Iterable[str]) -> re.Pattern[str] | None:
    variants: set[str] = set()
    for name in names:
        name = name.strip()
        if len(name) < 2:
            continue
        variants.add(name)
        variants.add("".join(name.split()))
    if not variants:
        return None
    return re.compile("|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True)), re.IGNORECASE)


def mask_spoken_pii(text: str, names: Iterable[str] = ()) -> MaskResult:
    """Mask personal data in one transcript. `names` are extra names to hide wherever they occur (synthetic candidate)."""
    kinds: Counter[str] = Counter()

    def sub(pattern: re.Pattern[str], placeholder: str, kind: str, source: str) -> str:
        out, count = pattern.subn(placeholder, source)
        if count:
            kinds[kind] += count
        return out

    def sub_name(pattern: re.Pattern[str], source: str) -> str:
        out, count = pattern.subn(lambda m: m.group("pre") + NAME, source)
        if count:
            kinds["name"] += count
        return out

    out = text or ""
    out = sub(_RRN_RE, RRN, "rrn", out)
    out = sub(_EMAIL_RE, EMAIL, "email", out)
    out = sub(_EMAIL_SPOKEN_RE, EMAIL, "email", out)
    out = sub(_URL_RE, URL, "url", out)
    out = sub(_PHONE_RE, PHONE, "phone", out)
    out = sub(_PHONE_SPOKEN_RE, PHONE, "phone", out)
    out = sub(_BIRTH_RE, BIRTH, "birth_date", out)
    out = sub_name(_LABELED_NAME_RE, out)
    out = sub_name(_INTRO_NAME_RE, out)
    out = sub_name(_ENGLISH_NAME_RE, out)
    if (configured := _configured_names_re(names)) is not None:
        out = sub(configured, NAME, "name", out)
    return MaskResult(" ".join(out.split()), dict(kinds))


def mask_speech_event(event, names: Iterable[str] = ()) -> int:
    """Mask the transcript text of a LiveKit `SpeechEvent` in place. Returns how many alternatives changed.

    Word timings are dropped for an alternative whose text changed, because they would still carry the raw words.
    """
    changed = 0
    for alt in getattr(event, "alternatives", None) or []:
        result = mask_spoken_pii(alt.text, names)
        if result.text != alt.text:
            alt.text = result.text
            if result.changed and getattr(alt, "words", None):
                alt.words = None
            changed += 1
    return changed


# ── Output screens ──

# Topics an interviewer must not raise (intent of data/interview_blocklist.yaml, D21). Over-blocking is acceptable:
# the PoC then speaks its fixed fallback question.
BLOCKED_TOPICS = (
    "결혼", "미혼", "기혼", "자녀", "출산", "임신", "종교", "나이", "연령", "몇 살", "고향", "출신", "가족", "부모님",
    "정치", "병역", "군대", "외모", "몸무게", "성별", "연애", "애인", "국적", "질병", "건강 상태",
)
# The AI never decides who passes (AI rule 5): no verdict words in anything it says
VERDICT_WORDS = ("합격", "불합격", "탈락", "점수", "채용", "선발", "뽑")

MAX_FOLLOWUP_CHARS = 160
MAX_CLOSING_CHARS = 200
_QUESTION_MARKS = ("?", "？")


def _clean(text: str) -> str:
    return " ".join((text or "").strip().strip("\"'“”‘’`").split())


def _has_any(text: str, words: Iterable[str]) -> bool:
    return any(w in text for w in words)


def screen_followup(text: str) -> str | None:
    """The cleaned follow-up question when it passes, else None (caller speaks the fixed fallback)."""
    q = _clean(text)
    if not q or len(q) > MAX_FOLLOWUP_CHARS:
        return None
    if sum(q.count(m) for m in _QUESTION_MARKS) != 1 or not q.endswith(_QUESTION_MARKS):
        return None
    if _URL_RE.search(q) or _EMAIL_RE.search(q) or "[" in q or "```" in q or "\n" in text.strip():
        return None
    if _has_any(q, BLOCKED_TOPICS) or _has_any(q, VERDICT_WORDS):
        return None
    return q


def screen_closing(text: str) -> str | None:
    """The cleaned closing line when it passes (no question, no verdict, no protected topic), else None."""
    c = _clean(text)
    if not c or len(c) > MAX_CLOSING_CHARS:
        return None
    if _has_any(c, _QUESTION_MARKS) or _URL_RE.search(c) or _EMAIL_RE.search(c) or "[" in c or "```" in c:
        return None
    if _has_any(c, BLOCKED_TOPICS) or _has_any(c, VERDICT_WORDS):
        return None
    return c
