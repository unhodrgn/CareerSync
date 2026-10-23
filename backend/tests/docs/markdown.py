"""Markdown and repo reading for the doc-drift guards in this folder.

Offline and read-only: no network, database or git. The guards find their input by structure (a table by its
header cells, an `env` code block, a phrase) in any guarded doc, so moving text between docs keeps them working.
"""
import posixpath
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST = Path(__file__).with_name("allowlist.yaml")

# Not maintained or not docs: the archived snapshot, the audit report, LLM prompts
EXCLUDED = ("docs/archive/", "AUDIT_REPORT.md", "ai/prompts/")
# Design docs: checked for links only
LINK_ONLY = ("DESIGN.md", "PRODUCT.md")

INLINE_CODE = re.compile(r"`[^`\n]*`")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)\)")


@dataclass(frozen=True)
class Doc:
    rel: str  # path from the repo root, with forward slashes
    lines: tuple[str, ...]
    in_code: tuple[bool, ...]  # inside a fenced code block (fence lines included)

    @classmethod
    def from_text(cls, rel: str, text: str) -> "Doc":
        lines, flags, fence = text.splitlines(), [], False
        for line in lines:
            if line.lstrip().startswith("```"):
                flags.append(True)
                fence = not fence
            else:
                flags.append(fence)
        return cls(rel, tuple(lines), tuple(flags))

    def prose(self) -> Iterator[tuple[int, str]]:
        """(line number, line) outside code blocks; table rows included."""
        for no, (line, code) in enumerate(zip(self.lines, self.in_code, strict=True), 1):
            if not code:
                yield no, line

    def numbered(self) -> Iterator[tuple[int, str]]:
        yield from enumerate(self.lines, 1)

    def code_blocks(self) -> Iterator[tuple[int, str, list[tuple[int, str]]]]:
        """(line of the opening fence, info string, [(line number, line)]) for each fenced block."""
        start, info, body = None, "", []
        for no, line in self.numbered():
            if line.lstrip().startswith("```"):
                if start is None:
                    start, info, body = no, line.strip()[3:].strip(), []
                else:
                    yield start, info, body
                    start = None
            elif start is not None:
                body.append((no, line))


def load(rel: str, root: Path = ROOT) -> Doc:
    return Doc.from_text(rel, (root / rel).read_text(encoding="utf-8"))


def markdown_files(root: Path = ROOT) -> list[str]:
    files = sorted(p.name for p in root.glob("*.md"))
    files += sorted(p.relative_to(root).as_posix() for p in (root / "docs").rglob("*.md"))
    return [f for f in files if not f.startswith(EXCLUDED)]


def guarded_docs(root: Path = ROOT) -> list[Doc]:
    return [load(f, root) for f in markdown_files(root) if f not in LINK_ONLY]


def link_docs(root: Path = ROOT) -> list[Doc]:
    return [load(f, root) for f in markdown_files(root)]


def resolve(doc_rel: str, target: str) -> str:
    """A link target relative to the doc, as a path from the repo root."""
    return posixpath.normpath(posixpath.join(posixpath.dirname(doc_rel), target))


# ── Headings and GitHub anchors ──


def slug(text: str) -> str:
    """GitHub's anchor for a heading: lower case, letters/marks/numbers/`_`/space/`-` kept, spaces → `-`.
    Marks stay, so the U+FE0F after an emoji survives: "⚙️ Run" → "️-run"."""
    kept = [ch for ch in text.strip().lower() if unicodedata.category(ch)[0] in "LMN" or unicodedata.category(ch) == "Pc" or ch in " -"]
    return "".join(kept).replace(" ", "-")


def heading_text(line: str) -> str:
    text = re.sub(r"^#+\s*", "", line).strip()
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", text)


def headings(doc: Doc) -> list[tuple[int, str]]:
    return [(no, heading_text(line)) for no, line in doc.prose() if re.match(r"^#{1,6}\s", line)]


def anchors(doc: Doc) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for _no, text in headings(doc):
        base = slug(text)
        n = seen.get(base, 0)
        out.add(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    return out


def links(doc: Doc) -> Iterator[tuple[int, str, str]]:
    """(line, label, target) of each Markdown link outside code (inline code spans are not links)."""
    for no, line in doc.prose():
        for m in LINK.finditer(INLINE_CODE.sub("", line)):
            yield no, m.group(1), m.group(2)


def code_spans(text: str) -> list[str]:
    return CODE_SPAN.findall(text)


# ── Tables ──


@dataclass(frozen=True)
class Table:
    doc: Doc
    line: int  # line of the header row
    header: tuple[str, ...]
    rows: tuple[tuple[int, tuple[str, ...]], ...]

    def column(self, *names: str) -> int | None:
        """Index of the first header cell that starts with one of `names` (case-insensitive)."""
        for i, cell in enumerate(self.header):
            if any(cell.lower().startswith(n.lower()) for n in names):
                return i
        return None


def split_cells(line: str) -> tuple[str, ...]:
    """Cells of a table row; `\\|` is a pipe inside a cell, not a separator."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return tuple(cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", inner))


def tables(doc: Doc) -> list[Table]:
    out, block = [], []
    for no, line in [*doc.prose(), (0, "")]:
        if line.strip().startswith("|"):
            if block and no != block[-1][0] + 1:
                out += _table(doc, block)
                block = []
            block.append((no, line))
            continue
        out += _table(doc, block)
        block = []
    return out


def _table(doc: Doc, block: list[tuple[int, str]]) -> list[Table]:
    if len(block) < 2 or not re.fullmatch(r"[\s|:\-]+", block[1][1]):
        return []
    rows = tuple((no, split_cells(line)) for no, line in block[2:])
    return [Table(doc, block[0][0], split_cells(block[0][1]), rows)]


# ── Code places, for failure messages ──


def line_of(rel: str, pattern: str, root: Path = ROOT) -> int | None:
    """First line of a repo file that matches `pattern`."""
    path = root / rel
    if not path.is_file():
        return None
    rx = re.compile(pattern)
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if rx.search(line):
            return no
    return None


def place(rel: str, pattern: str, root: Path = ROOT) -> str:
    no = line_of(rel, pattern, root)
    return f"{rel}:{no}" if no else rel


# ── Allowlist ──


class Allowlist:
    """One section of allowlist.yaml: known, intended differences. Every entry needs a `reason`, and an entry that
    no longer matches a real difference is reported as stale, so the list cannot outlive what it excuses."""

    def __init__(self, section: str, key: str, data: dict | None = None):
        if data is None:
            data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
        self.section, self.key = section, key
        self._problems: list[str] = []
        self._entries: dict[str, bool] = {}
        for entry in data.get(section) or []:
            value = str(entry.get(key, "")).strip()
            if not str(entry.get("reason", "")).strip():
                self._problems.append(f"allowlist.yaml [{section}] {value!r} has no reason. Add one or remove the entry.")
            self._entries[value] = False

    def covers(self, value: str) -> bool:
        if value in self._entries:
            self._entries[value] = True
            return True
        return False

    def problems(self) -> list[str]:
        stale = [
            f"allowlist.yaml [{self.section}] {value!r} no longer matches any difference. Remove the entry."
            for value, used in self._entries.items()
            if not used
        ]
        return self._problems + stale


def report(problems: list[str]) -> str:
    return f"{len(problems)} doc/code difference(s):\n- " + "\n- ".join(problems)
