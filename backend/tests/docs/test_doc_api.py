"""Endpoint tables vs the routes. Any table with a Method and a Path/Endpoint column must name only real routes; the
tables that also have a Who column (PROJECT_DOCUMENTATION.md §4.1) must cover every route and state its auth
correctly; a sentence listing the endpoints that need no token must list exactly those. The doc is the standard
(D11): every message says which side to fix."""
import importlib
import inspect
import pkgutil
import re
from dataclasses import dataclass
from itertools import product

from fastapi.routing import APIRoute

import app.api.v1 as v1
from app.core import deps
from app.main import app

from .markdown import ROOT, Allowlist, Doc, Table, code_spans, guarded_docs, report, tables

API_PREFIX = "/api"  # app/main.py includes every v1 router under /api
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
AUTH = {deps.get_company_user: "company", deps.get_current_user: "login", deps.get_optional_user: "optional"}
DESCRIBE = {
    "public": "needs no token",
    "optional": "takes an optional token (OptionalUser)",
    "login": "needs a logged-in user (CurrentUser)",
    "company": "needs a company user (CompanyUser)",
}
FIX = "The doc is the standard (D11): fix the route, unless the doc is wrong (then fix the doc and tell Long)."


@dataclass(frozen=True)
class Route:
    kind: str  # public | optional | login | company
    place: str  # file:line of the endpoint function


@dataclass(frozen=True)
class DocOp:
    op: tuple[str, str]  # (METHOD, /path)
    where: str  # file:line of the row
    who: str | None  # the Who cell, if the table has one


def auth_kind(dependant) -> str:
    found = set()

    def walk(d):
        for sub in d.dependencies:
            if sub.call in AUTH:
                found.add(AUTH[sub.call])
            walk(sub)

    walk(dependant)
    for kind in ("company", "login", "optional"):
        if kind in found:
            return kind
    return "public"


def _place(endpoint) -> str:
    path = inspect.getsourcefile(endpoint)
    rel = str(path).replace("\\", "/").split(str(ROOT).replace("\\", "/") + "/")[-1]
    return f"{rel}:{inspect.getsourcelines(endpoint)[1]}"


def code_routes() -> dict[tuple[str, str], Route]:
    routes = {}
    for info in pkgutil.iter_modules(v1.__path__):
        router = getattr(importlib.import_module(f"app.api.v1.{info.name}"), "router", None)
        for route in getattr(router, "routes", []):
            if isinstance(route, APIRoute):
                for method in route.methods - {"HEAD"}:
                    routes[(method, API_PREFIX + route.path)] = Route(auth_kind(route.dependant), _place(route.endpoint))
    for route in app.routes:  # /health and other routes declared on the app itself
        if isinstance(route, APIRoute) and route.include_in_schema:
            for method in route.methods - {"HEAD"}:
                routes[(method, route.path)] = Route(auth_kind(route.dependant), _place(route.endpoint))
    return routes


def openapi_operations() -> set[tuple[str, str]]:
    return {(method.upper(), path) for path, item in app.openapi()["paths"].items() for method in item}


def endpoint_tables(docs: list[Doc]) -> list[Table]:
    return [t for t in (t for d in docs for t in tables(d)) if t.column("method") is not None and t.column("path", "endpoint") is not None]


def row_operations(table: Table, line: int, cells: tuple[str, ...]) -> tuple[list[DocOp], list[str]]:
    where = f"{table.doc.rel}:{line}"
    methods = re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\b", cells[table.column("method")])
    paths: list[str] = []
    for span in code_spans(cells[table.column("path", "endpoint")]):
        path = span.split("?", 1)[0].strip()
        if not path.startswith("/"):
            continue
        if paths and not path.startswith((API_PREFIX + "/", "/health")) and path.count("/") == 1:
            path = paths[-1].rsplit("/", 1)[0] + path  # "`/api/x/{id}/accept` · `/reject`"
        paths.append(path)
    if not methods or not paths:
        return [], [f"{where}: cannot read a method and a path from this row. Write the method(s) and a backticked path."]
    if len(methods) > 1 and len(paths) > 1:
        return [], [f"{where}: {len(methods)} methods with {len(paths)} paths is ambiguous. Split the row into one row per path."]
    who_col = table.column("who")
    who = cells[who_col] if who_col is not None else None
    return [DocOp(op, where, who) for op in product(methods, paths)], []


def who_kinds(who: str) -> set[str] | None:
    text = who.strip().lower()
    if text.startswith("anyone"):
        return {"optional"} if "token optional" in text else {"public", "optional"}
    if text.startswith("company"):
        return {"company"}
    if text.startswith(("seeker", "logged in", "any signed-in")):
        return {"login"}
    return None


def _op(op: tuple[str, str]) -> str:
    return f"{op[0]} {op[1]}"


def api_problems(docs: list[Doc], routes: dict[tuple[str, str], Route], allowed: Allowlist) -> list[str]:
    problems, reference = [], {}
    for table in endpoint_tables(docs):
        for line, cells in table.rows:
            ops, row_problems = row_operations(table, line, cells)
            problems += row_problems
            for d in ops:
                route = routes.get(d.op)
                if route is None:
                    problems.append(f"{d.where} documents {_op(d.op)}, which no route serves. Remove the row, or add the route if the doc is right (D11).")
                    continue
                if d.who is None:
                    continue
                if d.op in reference:
                    problems.append(f"{d.where} documents {_op(d.op)} again (also {reference[d.op].where}). Keep one row.")
                reference[d.op] = d
                kinds = who_kinds(d.who)
                if kinds is None:
                    problems.append(f"{d.where}: cannot read the Who cell {d.who!r}. Start it with Anyone, Logged in, Seeker or Company.")
                elif route.kind not in kinds:
                    problems.append(
                        f"{d.where} says {_op(d.op)} is for {d.who.split('.')[0]!r} ({' or '.join(DESCRIBE[k] for k in sorted(kinds))}); "
                        f"the route {DESCRIBE[route.kind]} ({route.place}). {FIX}"
                    )
    for op, route in sorted(routes.items()):
        if op not in reference and not allowed.covers(_op(op)):
            problems.append(
                f"Undocumented endpoint {_op(op)} ({route.place}). Add a row to the Method/Path/Who table in "
                f"PROJECT_DOCUMENTATION.md §4.1, or allowlist it in backend/tests/docs/allowlist.yaml [api_undocumented] with a reason."
            )
    return problems


def public_sentence_problems(docs: list[Doc], routes: dict[tuple[str, str], Route]) -> list[str]:
    """A sentence such as "All endpoints except register, login, … need `Authorization: Bearer <token>`"."""
    expected = {op for op, r in routes.items() if r.kind in ("public", "optional")}
    problems = []
    for doc in docs:
        for line, text in doc.prose():
            if "Authorization: Bearer" not in text or not re.search(r"\bexcept\b", text, re.IGNORECASE):
                continue
            listed = {(m.group(1), m.group(2)) for m in re.finditer(rf"`({'|'.join(METHODS)}) (/[^`\s]+)`", text)}
            if "`/health`" in text:
                listed.add(("GET", "/health"))
            for word, op in (("register", ("POST", "/api/auth/register")), ("login", ("POST", "/api/auth/login"))):
                if re.search(rf"\b{word}\b", text):
                    listed.add(op)
            if listed != expected:
                missing = ", ".join(f"{_op(o)} ({routes[o].place})" for o in sorted(expected - listed))
                extra = ", ".join(f"{_op(o)} ({routes[o].place if o in routes else 'no such route'})" for o in sorted(listed - expected))
                problems.append(
                    f"{doc.rel}:{line} lists the endpoints that need no token. Not listed but tokenless in code: {missing or '-'}; "
                    f"listed but needing a token in code: {extra or '-'}. Fix the sentence, or the routes if the doc is right (D11)."
                )
    return problems


def test_route_walk_matches_openapi():
    """Self-check of this guard: the routes it reads are exactly the operations the app serves."""
    walked, served = set(code_routes()), openapi_operations()
    assert walked == served, f"route walk disagrees with app.openapi(): only walked {walked - served}, only served {served - walked}. Fix backend/tests/docs/test_doc_api.py."


def test_endpoint_tables_match_the_routes():
    allowed = Allowlist("api_undocumented", "endpoint")
    problems = api_problems(guarded_docs(), code_routes(), allowed) + allowed.problems()
    assert not problems, report(problems)


def test_sentences_listing_tokenless_endpoints_match():
    problems = public_sentence_problems(guarded_docs(), code_routes())
    assert not problems, report(problems)
