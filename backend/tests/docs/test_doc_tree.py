"""The folder tree in the docs (any code block whose first line is `CareerSync/`, today PROJECT_DOCUMENTATION.md §8) vs
the files. Every entry must exist, and the tree must list every top-level entry and every folder down to DEPTH levels
below the repo root. The real tree comes from walking the files with a fixed skip list (local, generated and tool
folders), not from git, so it works offline and in a fresh checkout. A deliberate omission goes into
allowlist.yaml [tree_omitted] with a reason."""
import os
import posixpath
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .markdown import ROOT, Allowlist, Doc, guarded_docs, report

ROOT_LINE = "CareerSync/"
DEPTH = 2  # folders down to this many levels below the repo root must be listed
# Local, generated or secret, so never listed; hidden folders are tool folders (.claude, .impeccable, …) except these
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "__pycache__"}
HIDDEN_KEPT = {".github"}
SKIP_FILES = {".env", "AUDIT_REPORT.md"}  # local secrets; the untracked audit report
BRANCH = re.compile(r"├── |└── ")
INDENT = ("│   ", "    ")  # one level = 4 characters
FIX_TREE = "Add it to the tree, or allowlist it in backend/tests/docs/allowlist.yaml [tree_omitted] with a reason."


@dataclass(frozen=True)
class Entry:
    path: str  # from the repo root, forward slashes, no trailing slash
    is_dir: bool
    line: int


def skipped_dir(name: str) -> bool:
    return name in SKIP_DIRS or (name.startswith(".") and name not in HIDDEN_KEPT)


def repo_paths(root: Path = ROOT) -> tuple[set[str], set[str]]:
    """(files, folders) under the repo root, skip lists applied."""
    files, dirs = set(), set()
    for here, subdirs, names in os.walk(root):
        rel = Path(here).relative_to(root).as_posix()
        subdirs[:] = sorted(d for d in subdirs if not skipped_dir(d))
        dirs.update(_join(rel, d) for d in subdirs)
        files.update(_join(rel, n) for n in names if n not in SKIP_FILES)
    return files, dirs


def _join(parent: str, name: str) -> str:
    return name if parent in ("", ".") else posixpath.join(parent, name)


def trees(docs: list[Doc]) -> Iterator[tuple[Doc, int, list[tuple[int, str]]]]:
    """(doc, line of the opening fence, body lines) of each code block whose first line is `CareerSync/`."""
    for doc in docs:
        for start, _info, body in doc.code_blocks():
            if body and body[0][1].strip() == ROOT_LINE:
                yield doc, start, body


def parse_tree(doc: Doc, body: list[tuple[int, str]]) -> tuple[list[Entry], list[str]]:
    """Entries of a ├──/└── tree (4 characters per level). `a/b.py` is a path below the current folder, `x, y/` lists
    several entries on one line, and text after `#` is a comment. Deeper lines belong to the last folder on the line."""
    entries, problems = [], []
    parents = [""]  # parents[level - 1] = folder of the entries at that level
    for no, line in body[1:]:
        m = BRANCH.search(line)
        if not m:
            rest = line.strip(" │")
            if rest and not rest.startswith("#"):
                problems.append(f"{doc.rel}:{no} is not a tree line (├── or └── after 4 characters per level). Fix the line.")
            continue
        prefix = line[: m.start()]
        if len(prefix) % 4 or any(prefix[i : i + 4] not in INDENT for i in range(0, len(prefix), 4)):
            problems.append(f"{doc.rel}:{no} is not indented by 4 characters (│ or spaces) per level. Fix the line.")
            continue
        level = len(prefix) // 4 + 1
        if level > len(parents):
            problems.append(f"{doc.rel}:{no} is indented below an entry that is not a folder (folders end with /). Fix the tree.")
            continue
        del parents[level:]
        names = [n.strip() for n in re.split(r"\s#", line[m.end() :], maxsplit=1)[0].split(",") if n.strip()]
        last_dir = None
        for name in names:
            path = _join(parents[-1], name.rstrip("/"))
            entries.append(Entry(path, name.endswith("/"), no))
            last_dir = path if name.endswith("/") else None
        if last_dir is not None:
            parents.append(last_dir)
    return entries, problems


def tree_problems(
    doc: Doc, fence: int, entries: list[Entry], files: set[str], dirs: set[str], allowed: Allowlist, depth: int = DEPTH
) -> list[str]:
    problems, listed = [], set()
    for e in entries:
        shown = e.path + ("/" if e.is_dir else "")
        if e.path in (dirs if e.is_dir else files):
            pass
        elif e.path in dirs:
            problems.append(f"{doc.rel}:{e.line} lists {shown} as a file, but it is a folder. End it with / in the tree.")
        elif e.path in files:
            problems.append(f"{doc.rel}:{e.line} lists {shown} as a folder, but it is a file. Drop the / in the tree.")
        else:
            problems.append(
                f"{doc.rel}:{e.line} lists {shown}, which is not in the repo (missing, or local/generated and skipped). "
                f"Fix the tree or restore the file."
            )
        parts = e.path.split("/")
        listed.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))  # `a/b.py` lists a/ too
    top = {p for p in files | dirs if "/" not in p}
    candidates = top | {d for d in dirs if d.count("/") < depth}
    covered = {""}
    for path in sorted(candidates, key=lambda p: (p.count("/"), p)):
        if posixpath.dirname(path) not in covered:
            continue  # under an omitted or missing folder: that folder is reported (or allowlisted) instead
        if path in listed:
            covered.add(path)
        elif not allowed.covers(path):
            shown = path + ("/" if path in dirs else "")
            problems.append(f"{doc.rel}:{fence} the folder tree does not list {shown}. {FIX_TREE}")
    return problems


def test_folder_tree_matches_the_files():
    files, dirs = repo_paths()
    allowed = Allowlist("tree_omitted", "path")
    problems, found = [], False
    for doc, fence, body in trees(guarded_docs()):
        found = True
        entries, parse = parse_tree(doc, body)
        problems += parse + tree_problems(doc, fence, entries, files, dirs, allowed)
    if not found:
        problems.append(f"No doc has the folder tree (a code block starting with `{ROOT_LINE}`) any more. Restore it in PROJECT_DOCUMENTATION.md §8 or drop this guard.")
    problems += allowed.problems()
    assert not problems, report(problems)
