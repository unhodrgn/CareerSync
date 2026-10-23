"""Links and anchors in every Markdown doc follow GitHub's anchor rules (emoji headings included), and backticked
repo paths in the guarded docs exist. External links are not checked: the suite runs offline."""
import difflib
import re
from collections.abc import Callable

from .markdown import ROOT, Allowlist, Doc, anchors, code_spans, guarded_docs, link_docs, links, load, report, resolve

SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
# `backend/app/core/config.py:30`, `docs/archive/`: a path from the repo root; placeholders and globs are not paths
REPO_PATH = re.compile(r"^(?:backend|ai|frontend|data|docs|scripts)/[\w./-]*$")


def _on_disk(rel: str) -> bool:
    return (ROOT / rel).exists()


def _doc_on_disk(rel: str) -> Doc | None:
    return load(rel) if (ROOT / rel).is_file() else None


def link_problems(
    docs: list[Doc], exists: Callable[[str], bool] = _on_disk, doc_for: Callable[[str], Doc | None] = _doc_on_disk
) -> list[str]:
    problems, anchor_cache = [], {}
    for doc in docs:
        for line, _label, target in links(doc):
            if SCHEME.match(target) or target.startswith("//"):
                continue
            file_part, _, fragment = target.partition("#")
            dest = resolve(doc.rel, file_part) if file_part else doc.rel
            if file_part and not exists(dest):
                problems.append(f"{doc.rel}:{line} links to {target!r}, but {dest} does not exist. Fix the link or restore the file.")
                continue
            if not fragment or not dest.endswith(".md"):
                continue
            if dest not in anchor_cache:
                target_doc = doc if dest == doc.rel else doc_for(dest)
                anchor_cache[dest] = anchors(target_doc) if target_doc else set()
            if fragment not in anchor_cache[dest]:
                close = difflib.get_close_matches(fragment, sorted(anchor_cache[dest]), n=3)
                hint = f" Closest: {', '.join('#' + c for c in close)}." if close else ""
                problems.append(f"{doc.rel}:{line} links to #{fragment} in {dest}, which has no such heading.{hint} Fix the link or the heading.")
    return problems


def path_problems(docs: list[Doc], allowed: Allowlist, exists: Callable[[str], bool] = _on_disk) -> list[str]:
    problems = []
    for doc in docs:
        for line, text in doc.prose():
            for span in code_spans(text):
                path = re.sub(r":\d+(?:-\d+)?$", "", span.strip()).rstrip("/")
                if not REPO_PATH.match(path) or exists(path) or allowed.covers(path):
                    continue
                problems.append(
                    f"{doc.rel}:{line} names `{span}`, but {path} does not exist. Fix the path in the doc, restore the "
                    f"file, or allowlist it in backend/tests/docs/allowlist.yaml [paths] with a reason."
                )
    return problems


def test_links_and_anchors_resolve():
    problems = link_problems(link_docs())
    assert not problems, report(problems)


def test_backticked_repo_paths_exist():
    allowed = Allowlist("paths", "path")
    problems = path_problems(guarded_docs(), allowed) + allowed.problems()
    assert not problems, report(problems)
