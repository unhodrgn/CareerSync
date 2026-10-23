"""Constants and thresholds quoted in the docs match the code: tables whose first column is "Constant"
(PROJECT_DOCUMENTATION.md §9), every "`NAME` = `value`", "`NAME` is `value`" and "`NAME` (number" in prose, and the
prose claims in claims.py (Fit/Pref 40, 0.5 · Fit + 0.5 · Pref, importance and match bands, criteria limits, …)."""
import importlib
import re

from app.core.config import settings

from .claims import CLAIMS, Claim
from .markdown import Allowlist, Doc, code_spans, guarded_docs, place, report, tables
from .test_doc_env import code_readers

# Modules whose UPPER_CASE names the docs may quote; Settings attributes are tried first
MODULES = ("app.core.config", "ai.llm.client", "ai.scoring.fit", "ai.parsing.pdf", "ai.parsing.extract", "app.services.company_project_service")
CONST = r"(?:[a-z_][a-z0-9_]*\.)?[A-Z][A-Z0-9_]+"
ASSIGNED = re.compile(rf"`({CONST})`\s+(?:=|is)\s+`([^`]+)`")
IN_PARENS = re.compile(rf"`({CONST})`\s*\((\d+(?:\.\d+)?)(?![\d.])")
FIX = "The doc is the standard (D11): fix the code, unless the doc is wrong (then fix the doc and tell Long)."


def _file(module: str) -> str:
    return ("backend/" if module.startswith("app.") else "") + module.replace(".", "/") + ".py"


def resolve(name: str) -> tuple[bool, object, str]:
    """(found, value, file:line) for a quoted constant name."""
    alias, _, attr = name.rpartition(".")
    if not alias and hasattr(settings, attr):
        return True, getattr(settings, attr), place(_file("app.core.config"), rf"^\s+{attr}\b")
    for module in MODULES:
        if alias and module.rsplit(".", 1)[-1] != alias:
            continue
        mod = importlib.import_module(module)
        if hasattr(mod, attr):
            return True, getattr(mod, attr), place(_file(module), rf"^\s*{attr}\b")
    return False, None, ""


def same(doc_value: str, code_value: object) -> bool:
    if isinstance(code_value, int | float) and not isinstance(code_value, bool):
        try:
            return float(doc_value) == float(code_value)
        except ValueError:
            return False
    return doc_value == str(code_value)


def _fmt(values: tuple) -> str:
    return ", ".join(f"{v:g}" if isinstance(v, float) else str(v) for v in values)


def constant_problems(docs: list[Doc], allowed: Allowlist, env_names: set[str]) -> list[str]:
    problems = []

    def check(where: str, name: str, doc_value: str) -> None:
        found, value, code_where = resolve(name)
        if not found:
            if name not in env_names and not allowed.covers(name):
                problems.append(
                    f"{where} names `{name}`, which is neither a Settings field nor a constant of {', '.join(MODULES)}. "
                    f"Fix the name, or allowlist it in backend/tests/docs/allowlist.yaml [constants] with a reason."
                )
        elif not same(doc_value, value):
            problems.append(f"{where} says {name} = {doc_value}; the code has {value!r} ({code_where}). {FIX}")

    for doc in docs:
        for table in tables(doc):
            if not table.header or table.header[0].strip().lower() != "constant":
                continue
            for line, cells in table.rows:
                names = [n for n in code_spans(cells[0]) if re.fullmatch(CONST, n)]
                values = code_spans(cells[1]) if len(cells) > 1 else []
                pairs = zip(names, values, strict=True) if len(names) == len(values) else zip(names[:1], values[:1], strict=True)
                for name, doc_value in pairs:
                    check(f"{doc.rel}:{line}", name, doc_value)
        for line, text in doc.prose():
            for m in [*ASSIGNED.finditer(text), *IN_PARENS.finditer(text)]:
                check(f"{doc.rel}:{line}", m.group(1), m.group(2))
    return problems


def claim_problems(docs: list[Doc], claims: tuple[Claim, ...]) -> list[str]:
    problems = []
    for claim in claims:
        rx, expected, found = re.compile(claim.pattern), claim.values(), 0
        for doc in docs:
            for line, text in doc.prose():
                for m in rx.finditer(text):
                    found += 1
                    if not all(same(got, want) for got, want in zip(m.groups(), expected, strict=True)):
                        problems.append(f"{doc.rel}:{line} says {m.group(0)!r}; the code has {_fmt(expected)} ({claim.source}). {FIX}")
        if not found:
            problems.append(
                f"Claim {claim.id!r} is not in any doc any more (pattern {claim.pattern!r}). Restore the sentence, or "
                f"update the claim in backend/tests/docs/claims.py."
            )
    return problems


def test_quoted_constants_match_the_code():
    allowed = Allowlist("constants", "name")
    env_names = {r.name for r in code_readers()}
    problems = constant_problems(guarded_docs(), allowed, env_names) + allowed.problems()
    assert not problems, report(problems)


def test_prose_claims_match_the_code():
    problems = claim_problems(guarded_docs(), CLAIMS)
    assert not problems, report(problems)
