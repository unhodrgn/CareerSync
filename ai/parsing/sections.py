"""Split CV text into sections and retrieval chunks."""
import re
from dataclasses import dataclass

# Section heading keywords (Korean and English) → section key
_HEADINGS = {
    "experience": ("경력", "경력사항", "경력 사항", "work experience", "experience", "employment", "career"),
    "education": ("학력", "학력사항", "학력 사항", "education"),
    "project": ("프로젝트", "프로젝트 경험", "프로젝트 경력", "projects", "project"),
    "certificate": ("자격증", "자격 사항", "자격사항", "어학", "certificates", "certifications", "licenses"),
    "skill": ("기술", "기술 스택", "보유 기술", "스킬", "skills", "tech stack", "technical skills"),
    "summary": ("자기소개", "소개", "요약", "summary", "about me", "profile"),
    "activity": ("활동", "대외활동", "수상", "activities", "awards"),
}
_HEADING_LOOKUP = {h: key for key, words in _HEADINGS.items() for h in words}
_STRIP = re.compile(r"^[\s#*■□●○◆◇▶▷•\-\[\]【】<>()0-9.]+|[\s:：\[\]【】<>()]+$")


@dataclass(frozen=True)
class Section:
    key: str  # one of _HEADINGS keys, or "other"
    title: str
    text: str


@dataclass(frozen=True)
class Chunk:
    section: str
    text: str


def heading_key(line: str) -> str | None:
    words = _STRIP.sub("", line).strip().lower()
    if not words or len(words) > 20:
        return None
    return _HEADING_LOOKUP.get(words)


def split_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    key, title, buf = "other", "", []
    for line in text.splitlines():
        if (k := heading_key(line)) is not None:
            if any(b.strip() for b in buf):
                sections.append(Section(key, title, "\n".join(buf).strip()))
            key, title, buf = k, line.strip(), []
        else:
            buf.append(line)
    if any(b.strip() for b in buf):
        sections.append(Section(key, title, "\n".join(buf).strip()))
    return sections


def chunk_sections(sections: list[Section], max_chars: int = 600) -> list[Chunk]:
    """Paragraph-aligned chunks of about max_chars (≈300 tokens of Korean text)."""
    chunks = []
    for s in sections:
        buf = ""
        for para in re.split(r"\n\s*\n|\n(?=[•\-*·▪■]\s)", s.text):
            para = para.strip()
            if not para:
                continue
            if buf and len(buf) + len(para) > max_chars:
                chunks.append(Chunk(s.key, buf))
                buf = ""
            buf = f"{buf}\n{para}".strip()
            while len(buf) > max_chars * 1.5:
                chunks.append(Chunk(s.key, buf[:max_chars]))
                buf = buf[max_chars:]
        if buf:
            chunks.append(Chunk(s.key, buf))
    return chunks
