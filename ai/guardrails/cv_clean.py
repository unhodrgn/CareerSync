"""The CV cleaner: the masked CV without its personal and military blocks (docs/DECISIONS.md D61, D62, D85).

Shared by the practice interview, where `ai/interview/cv_context.py` is the one door the CV passes through, and by the
recruiter verification questions (`ai/career/verification.py`). It reads text only and calls no model.

The stored masked CV still carries age, gender and military-service text (Q24: `mask_pii` only masks what it can name, and
Q24 is unresolved), so nothing in `ai/interview/` reads it directly. `clean_cv` makes the version a model may be given,
in steps that do not depend on one another:

1. Structure. Only text under a known section heading (experience, education, project, certificate, skill, summary,
   activity) is kept; whatever comes before the first heading, the place of the name, contact and personal lines, is dropped.
   A heading of a personal or military block (인적사항, 병역사항 (필), Personal Profile, 추가 정보, 기타, …) is not a section
   heading of the parser, so the parser would fold its lines into the section above; here it starts a block that is dropped
   up to the next known heading. Matching is by prefix and fails closed: a heading that looks personal, or is a catch-all
   such as 기타, is treated as personal.
2. Labels. A personal label (성별, 나이, 생년월일, 국적, Date of birth, Nationality, …) on its own line is dropped with the
   short value line or lines after it (the two-line layout of a table); with its value on the same line, the line goes.
3. Segments. In what is left, a parenthesis or a ` | ` segment that touches age, gender or military service is cut and the
   professional rest of the line stays (`ai.guardrails.sensitive.cut_sensitive`).
4. Vocabulary. A line that still does is reduced to its other clauses or dropped.

`CleanCv.removed` keeps what was taken out, so a plan can be checked for a removed line that came back in another form
(`CleanCv.mentions_removed`). Over-blocking is accepted. What no step can see: a line about these topics under a normal heading
that uses none of the vocabulary, and a personal block under a heading that is not recognized as one.
"""
import re
import unicodedata
from dataclasses import dataclass

from ai.guardrails.sensitive import cut_sensitive
from ai.parsing.sections import heading_key

_DECORATION = re.compile(r"^[\s#*■□●○◆◇▶▷•\-\[\]【】<>()0-9.]+|[\s:：\[\]【】<>()]+$")
_COMPACT = re.compile(r"[\s\-_/·&,.:：()\[\]]+")
_BULLETS = "-•*·▪"  # list items; ■ ▶ # and the like decorate headings and are stripped by _DECORATION
_STOP = re.compile(r"[.。!?]\s*$|(?:다|요|죠)$")  # a sentence ends like this; a heading does not
_COLON = re.compile(r"[:：]")
_MIN_REMOVED_CHARS = 10  # a shorter removed line ("대한민국", "미혼") would match ordinary words of a question

# A heading that starts a personal block (prefix match on the compact heading, so "병역사항 (필)" and "Personal Profile"
# count) ...
_BLOCK_PREFIX = re.compile(
    r"^(?:인적|신상|병역|보훈|군복무|군경력|군생활|개인정보|개인사항|개인신상|기본정보|기본사항|기본인적|인사정보"
    r"|personal(?!project|website|portfolio|blog|development|growth)|military|demographic|veteran|biodata|vital"
    r"|additional(?:info|information|details))"
)
# ... or a catch-all or family/hobby heading, which often holds such lines (whole heading, with or without a suffix)
_BLOCK_WHOLE = re.compile(
    r"^(?:(?:가족|혼인|결혼|취미|특기|종교|추가|기타|비고|참고)(?:사항|정보|관계|여부|상태)?)+"
    r"$|^(?:family|religion|hobbies(?:interests)?|interests|others?|misc(?:ellaneous)?|notes?|remarks|references?)$"
)
# A label whose value is a personal fact: alone on a line, its value is on the next line
_LABEL = re.compile(
    r"^(?:성별|나이|연령|생년월일|생일|출생지?|국적|본적|혈액형|신장|체중"
    r"|age|sex|gender|dateofbirth|birthdate|birthday|dob|birth|nationality|maritalstatus|marital|bloodtype|blood|height|weight)"
    r"(?:사항|정보|여부)?$"
)


@dataclass(frozen=True)
class CleanCv:
    """The CV as the interview may use it. `text` has the section headings of the original, so the usual retrieval
    (`ai.scoring.retrieval.cv_chunks`) splits it the same way. `removed`: normalized lines taken out (long enough to
    recognize), for `mentions_removed`."""

    text: str
    removed: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.text.strip())

    def contains(self, line: str | None) -> bool:
        """True when the line is in the cleaned CV word for word (spacing and case aside)."""
        return bool(line and line.strip()) and _norm(line) in _norm(self.text)

    def mentions_removed(self, text: str | None) -> bool:
        """True when `text` contains a whole line that `clean_cv` removed. Catches a removed line that came back in a
        question, a quote or a rubric point whatever its wording of the topic was; a paraphrase is not caught."""
        norm = _norm(text or "")
        return any(line in norm for line in self.removed)


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).lower()


def _compact(text: str) -> str:
    return _COMPACT.sub("", unicodedata.normalize("NFC", _DECORATION.sub("", text)).lower())


def _standalone(line: str) -> bool:
    """Shaped like a heading or a label: short, no bullet, no ` | `, no sentence ending."""
    return bool(line) and line[0] not in _BULLETS and "|" not in line and len(line) <= 40 and len(line.split()) <= 5 and not _STOP.search(line)


def _is_block_heading(line: str) -> bool:
    if not _standalone(line) or _COLON.search(line.rstrip(":：")):  # "병역: 군필" is a label with a value, not a heading
        return False
    compact = _compact(line)
    return bool(compact) and bool(_BLOCK_PREFIX.match(compact) or _BLOCK_WHOLE.match(compact))


def _label_part(line: str) -> tuple[str, bool]:
    """(the label of a personal-label line, whether its value is missing) or ("", False) when the line is no such label."""
    if not _standalone(line) and not _COLON.search(line):
        return "", False
    if _COLON.search(line):
        label, value = _COLON.split(line, maxsplit=1)
        compact = _compact(label)
        if len(label.strip()) <= 24 and (_LABEL.match(compact) or _BLOCK_PREFIX.match(compact) or _BLOCK_WHOLE.match(compact)):
            return compact, not value.strip()
        return "", False
    compact = _compact(line)
    if _LABEL.match(compact):
        return compact, True  # the label alone
    first = _compact(line.split()[0])
    if len(line.split()) > 1 and _LABEL.match(first):  # "국적 대한민국", "Nationality Korean": label and value on one line
        return first, False
    return "", False


def _value_like(line: str) -> bool:
    """A short line that can be the value of a label: "여", "1997.05.12", "군필", "Female"."""
    return len(line) <= 30 and line[0] not in _BULLETS and "|" not in line and len(line.split()) <= 4


def clean_cv(masked_text: str | None) -> CleanCv:
    """The usable part of a masked CV (see the module doc). Idempotent; empty for an empty or heading-less CV."""
    out: list[str] = []
    removed: list[str] = []
    key: str | None = None  # None: before the first heading, or in a block that is dropped
    pending = 0  # label lines seen whose value line has not come yet
    for raw in (masked_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if heading_key(raw) is not None:
            key, pending = heading_key(raw), 0
            out.append(line)
        elif _is_block_heading(line):
            key, pending = None, 0
            removed.append(line)
        elif key is None:
            removed.append(line)
        elif (label := _label_part(line))[0]:
            pending += 1 if label[1] else 0
            removed.append(line)
        elif pending and _value_like(line):
            pending -= 1
            removed.append(line)
        else:
            pending = 0
            kept = cut_sensitive(line)
            if kept:
                out.append(kept.replace("<", "‹").replace(">", "›"))
            if _norm(kept) != _norm(line):  # something of the line, or all of it, was taken out
                removed.append(line)
    text = "\n".join(out)
    gone = tuple(dict.fromkeys(n for n in map(_norm, removed) if len(n) >= _MIN_REMOVED_CHARS))
    return CleanCv(text if any(heading_key(line) is None for line in out) else "", gone)
