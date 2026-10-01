"""Mask personal data before any LLM call (README: no name, email or phone sent to the LLM).

The masked text is also what evidence quotes are checked against, so evidence never carries PII.
"""
import re
from dataclasses import dataclass

_PATTERNS: tuple[tuple[str, str, re.Pattern], ...] = (
    ("email", "[이메일]", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("url", "[링크]", re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)),
    # Resident registration number (주민등록번호) before phone, since both are digit runs
    ("rrn", "[주민번호]", re.compile(r"\b\d{6}\s*-\s*[1-4]\d{6}\b")),
    ("phone", "[전화번호]", re.compile(r"(?:\+82[\s-]?)?0\d{1,2}[\s.-]?\d{3,4}[\s.-]?\d{4}\b")),
    # Birth date lines (생년월일 / 출생) keep the label but drop the date
    ("birth", "[생년월일]", re.compile(r"(?<=생년월일)\s*[:：]?\s*\d{4}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2}\s*일?")),
    ("address", "[주소]", re.compile(r"(?<=주소)\s*[:：]?\s*[^\n]+")),
)


@dataclass(frozen=True)
class MaskResult:
    text: str
    # Kinds of data that were found and masked, e.g. ("email", "phone")
    masked: tuple[str, ...]


def mask_pii(text: str, names: list[str] | None = None) -> MaskResult:
    found = []
    for kind, token, pattern in _PATTERNS:
        text, n = pattern.subn(token if kind not in ("birth", "address") else " " + token, text)
        if n:
            found.append(kind)
    for name in names or []:
        name = name.strip()
        if len(name) < 2:
            continue
        # Korean names are often written with spaces between syllables on CVs ("김 지 원")
        spaced = r"\s*".join(map(re.escape, name.replace(" ", "")))
        text, n = re.subn(spaced, "[이름]", text)
        if n and "name" not in found:
            found.append("name")
    return MaskResult(text=text, masked=tuple(found))
