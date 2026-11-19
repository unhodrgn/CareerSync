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

_SPOKEN_DIGITS = "공영일이삼사오육칠팔구"
_COMPOUND = "|".join(re.escape(s) for s in sorted(_DETECT_SURNAMES, key=len, reverse=True) if len(s) == 2)
_SINGLE = "".join(re.escape(s) for s in sorted(_DETECT_SURNAMES) if len(s) == 1)
_SURNAME = rf"(?:{_COMPOUND}|[{_SINGLE}])"
_BIRTH_DATE = r"(?:19|20)\d{2}\s*(?:년|[.\-/])\s*\d{1,2}\s*(?:월|[.\-/])\s*\d{1,2}\s*일?"
_AFTER_NAME = r"(?=\s*(?:입니다|이에요|예요|이라고|라고|이고|인데|이며|[,.]|$))"

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
_LABELED_NAME_RE = re.compile(rf"(?P<pre>(?:이름|성함|성명)\s*(?:은|는|이|가)?\s*)(?P<name>[가-힣]{{2,4}}){_AFTER_NAME}")
# "저는 김철수입니다" (a surname, then 1-2 syllables): "저는 개발자입니다" is not a name and stays
_INTRO_NAME_RE = re.compile(rf"(?P<pre>(?:저는|전|제\s*이름은)\s*)(?P<name>{_SURNAME}[가-힣]{{1,2}})(?=\s*(?:입니다|이에요|예요|이라고|라고\s*합니다))")
_ENGLISH_NAME_RE = re.compile(r"(?P<pre>\bmy\s+name\s+is\s+)(?P<name>[A-Za-z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*)?)", re.IGNORECASE)


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

    def sub_name(pattern: re.Pattern[str], source: str) -> str:
        out, count = pattern.subn(lambda m: m.group("pre") + NAME_TOKEN, source)
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
    for pattern in _account_patterns(names):
        out = sub(pattern, NAME_TOKEN, "name", out)
    return SpokenMaskResult(" ".join(out.split()), dict(kinds))
