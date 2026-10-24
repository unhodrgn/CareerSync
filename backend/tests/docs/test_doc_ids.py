"""Every D<n>, Q<n> and "issue <n>" a guarded doc mentions exists: D as a row of docs/DECISIONS.md §2, Q as an open
question in §3 or closed by a §2 row, issue as a row of the PROJECT_DOCUMENTATION.md issues table. No ID is
defined twice. D-ids in code comments must exist as well. Bare "#14"-style numbers (old PROGRESS numbering) are not
checked, and DECISIONS rows are never rewritten to satisfy this guard."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from .markdown import ROOT, Allowlist, Doc, guarded_docs, load, report, tables

D_REF = re.compile(r"\bD(\d{1,3})(?![0-9])")
Q_REF = re.compile(r"\bQ(\d{1,3})(?![0-9])")
ISSUE_REF = re.compile(r"\bissues?\s+(\d+(?:\s*(?:,|and|–|-|to)\s*\d+)*)", re.IGNORECASE)
DECISIONS = "docs/DECISIONS.md"
ISSUES = "PROJECT_DOCUMENTATION.md"
CODE_DIRS = ("backend/app", "backend/tests", "ai", "scripts", "frontend/src")
# The guards' own samples use made-up IDs; fixtures are data
CODE_SKIP = ("backend/tests/docs/", "ai/tests/fixtures/")


@dataclass
class Ids:
    decisions: dict[int, int] = field(default_factory=dict)  # D number → line in DECISIONS
    open_questions: dict[int, int] = field(default_factory=dict)
    closed_questions: set[int] = field(default_factory=set)  # mentioned in a §2 row
    issues: dict[int, int] = field(default_factory=dict)  # issue number → line in PROJECT_DOCUMENTATION
    problems: list[str] = field(default_factory=list)  # duplicates


def _define(ids: dict[int, int], number: int, where: Doc, line: int, kind: str, problems: list[str]) -> None:
    if number in ids:
        problems.append(f"{where.rel}:{line} defines {kind}{number} again (first at line {ids[number]}). Renumber one of them.")
    else:
        ids[number] = line


def collect_ids(decisions: Doc, issues_doc: Doc) -> Ids:
    ids = Ids()
    for table in tables(decisions):
        first = table.header[0].strip().lower()
        for line, cells in table.rows:
            if first == "id" and (m := re.fullmatch(r"D(\d+)", cells[0])):
                _define(ids.decisions, int(m.group(1)), decisions, line, "D", ids.problems)
                ids.closed_questions |= {int(q) for q in Q_REF.findall(" ".join(cells[1:]))}
            elif first == "#" and (m := re.fullmatch(r"Q(\d+)", cells[0])):
                _define(ids.open_questions, int(m.group(1)), decisions, line, "Q", ids.problems)
    for table in tables(issues_doc):
        if table.column("issue") is not None and table.column("status") is not None:
            for line, cells in table.rows:
                if re.fullmatch(r"\d+", cells[0]):
                    _define(ids.issues, int(cells[0]), issues_doc, line, "issue ", ids.problems)
    return ids


def issue_numbers(text: str) -> list[int]:
    """'33–39' → 33..39; '3, 6 and 26' → [3, 6, 26]."""
    numbers = []
    for part in re.split(r"\s*(?:,|and)\s*", text):
        if m := re.fullmatch(r"(\d+)\s*(?:–|-|to)\s*(\d+)", part.strip()):
            numbers += list(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.strip().isdigit():
            numbers.append(int(part))
    return numbers


def reference_problems(docs: list[Doc], ids: Ids, allowed: Allowlist) -> list[str]:
    problems = []
    last_issue = max(ids.issues, default=0)
    for doc in docs:
        for line, text in doc.prose():
            for m in D_REF.finditer(text):
                if int(m.group(1)) not in ids.decisions and not allowed.covers(f"D{m.group(1)}"):
                    problems.append(f"{doc.rel}:{line} refers to D{m.group(1)}, which {DECISIONS} §2 does not define. Fix the reference or add the decision row.")
            for m in Q_REF.finditer(text):
                q = int(m.group(1))
                if q not in ids.open_questions and q not in ids.closed_questions and not allowed.covers(f"Q{q}"):
                    problems.append(
                        f"{doc.rel}:{line} refers to Q{q}, which is neither open in {DECISIONS} §3 nor closed by a §2 row. "
                        f"Fix the reference, or add the question to {DECISIONS} §3."
                    )
            for m in ISSUE_REF.finditer(text):
                for n in issue_numbers(m.group(1)):
                    if n not in ids.issues and not allowed.covers(f"issue {n}"):
                        problems.append(
                            f"{doc.rel}:{line} refers to issue {n}, but the issues table in {ISSUES} has issues up to "
                            f"{last_issue} and no {n}. Fix the reference or restore the issue row."
                        )
    return problems


def code_files(root: Path = ROOT) -> list[str]:
    out = []
    for top in CODE_DIRS:
        for path in sorted((root / top).rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.suffix in (".py", ".ts", ".tsx") and "node_modules" not in rel and not rel.startswith(CODE_SKIP):
                out.append(rel)
    return out


def code_reference_problems(files: dict[str, str], ids: Ids) -> list[str]:
    problems = []
    for rel, text in files.items():
        for no, line in enumerate(text.splitlines(), 1):
            for m in D_REF.finditer(line):
                if int(m.group(1)) not in ids.decisions:
                    problems.append(f"{rel}:{no} refers to D{m.group(1)}, which {DECISIONS} §2 does not define. Fix the comment.")
    return problems


def _ids() -> Ids:
    return collect_ids(load(DECISIONS), load(ISSUES))


def test_ids_are_defined_once():
    problems = _ids().problems
    assert not problems, report(problems)


def test_every_referenced_id_exists():
    allowed = Allowlist("ids", "ref")
    problems = reference_problems(guarded_docs(), _ids(), allowed) + allowed.problems()
    assert not problems, report(problems)


def test_decision_ids_in_code_comments_exist():
    files = {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in code_files()}
    problems = code_reference_problems(files, _ids())
    assert not problems, report(problems)
