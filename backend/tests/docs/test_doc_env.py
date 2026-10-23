"""Environment variables: the names and defaults the code reads (AST over the backend, ai/, scripts/ and the test
fixture file; the Vite config), docker-compose.yml, .env.example and the docs agree. A table whose first column is
"Variable" is an env table; those with a Default column are the reference (PROJECT_DOCUMENTATION.md §9) and must list
every variable the code or Compose reads."""
import ast
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .markdown import ROOT, Allowlist, Doc, Table, code_spans, guarded_docs, report, tables

READER_DIRS = ("backend/app", "ai", "scripts")
READER_FILES = ("backend/tests/conftest.py",)
READER_SKIP = ("ai/tests/",)
VITE_CONFIG = "frontend/vite.config.ts"
COMPOSE = "docker-compose.yml"
EXAMPLE = ".env.example"
NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
UNKNOWN = object()  # a default the AST cannot work out


@dataclass(frozen=True)
class Reader:
    name: str
    where: str  # file:line
    default: object  # str, None (no default) or UNKNOWN


# ── Code side ──


def _constants(tree: ast.Module) -> dict[str, str]:
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out |= {t.id: node.value.value for t in node.targets if isinstance(t, ast.Name)}
    return out


def _value(node: ast.AST | None, constants: dict[str, str]) -> object:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    # str(REPO_ROOT / "data" / "skills.yaml") → "data/skills.yaml"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str" and len(node.args) == 1:
        parts, cur = [], node.args[0]
        while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div) and isinstance(cur.right, ast.Constant):
            parts.insert(0, str(cur.right.value))
            cur = cur.left
        if isinstance(cur, ast.Name) and cur.id == "REPO_ROOT" and parts:
            return "/".join(parts)
    return UNKNOWN


def _env_name(node: ast.AST) -> str | None:
    """The variable a call or subscript reads: env_or_default("X"), os.getenv("X"), os.environ.get("X"), os.environ["X"]."""
    arg = None
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        environ_get = name == "get" and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute) and func.value.attr == "environ"
        if name in ("env_or_default", "getenv") or environ_get:
            arg = node.args[0] if node.args else None
    elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
            arg = node.slice
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def readers_in(source: str, rel: str) -> list[Reader]:
    tree = ast.parse(source)
    constants = _constants(tree)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    out = []
    for node in ast.walk(tree):
        name = _env_name(node)
        if name is None:
            continue
        if isinstance(node, ast.Call) and len(node.args) > 1:
            default = _value(node.args[1], constants)
        else:
            # (os.getenv("X") or "").strip() or DEFAULT → DEFAULT: the last value of the outermost `or` around the read
            default, cur = None, node
            while cur in parents and isinstance(parents[cur], ast.BoolOp | ast.Call | ast.Attribute):
                cur = parents[cur]
                if isinstance(cur, ast.BoolOp) and isinstance(cur.op, ast.Or):
                    default = _value(cur.values[-1], constants)
        out.append(Reader(name, f"{rel}:{node.lineno}", default))
    return out


def code_readers(root: Path = ROOT) -> list[Reader]:
    files = [p for top in READER_DIRS for p in sorted((root / top).rglob("*.py"))]
    files += [root / f for f in READER_FILES]
    out = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if not rel.startswith(READER_SKIP):
            out += readers_in(path.read_text(encoding="utf-8"), rel)
    vite = (root / VITE_CONFIG).read_text(encoding="utf-8")
    for no, line in enumerate(vite.splitlines(), 1):
        for m in re.finditer(r"env\.(VITE_[A-Z0-9_]+)\s*\|\|\s*'([^']*)'", line):
            out.append(Reader(m.group(1), f"{VITE_CONFIG}:{no}", m.group(2)))
    return out


@dataclass(frozen=True)
class Compose:
    substitutions: dict[str, tuple[str | None, str]]  # ${NAME:-default} → (default, file:line)
    environment: dict[str, str]  # keys of every environment mapping → file:line


def compose_vars(text: str) -> Compose:
    subs, env = {}, {}
    for no, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}", line):
            subs.setdefault(m.group(1), (m.group(2), f"{COMPOSE}:{no}"))
    data = yaml.safe_load(text) or {}
    blocks = [data.get("x-backend", {})] + list((data.get("services") or {}).values())
    lines = text.splitlines()
    # Only the images we build run our code; `db` (postgres:16) reads POSTGRES_* itself
    for block in (b for b in blocks if b and "build" in b):
        for key in block.get("environment") or {}:
            no = next((i for i, line in enumerate(lines, 1) if re.match(rf"^\s+{key}:", line)), None)
            env.setdefault(key, f"{COMPOSE}:{no}" if no else COMPOSE)
    return Compose(subs, env)


def example_vars(text: str) -> dict[str, tuple[str, int, bool]]:
    """NAME → (value, line, commented out) for each `NAME=value` or `# NAME=value` line of .env.example."""
    out = {}
    for no, line in enumerate(text.splitlines(), 1):
        if m := re.match(r"^\s*(#)?\s*([A-Z][A-Z0-9_]*)=(.*)$", line):
            out[m.group(2)] = (m.group(3).strip(), no, bool(m.group(1)))
    return out


# ── Doc side ──


def env_tables(docs: list[Doc]) -> list[Table]:
    return [t for d in docs for t in tables(d) if t.header and t.header[0].strip().lower() == "variable"]


def row_names(cells: tuple[str, ...]) -> list[str]:
    return [s for s in code_spans(cells[0]) if NAME.match(s)]


def row_defaults(table: Table, cells: tuple[str, ...], names: list[str]) -> dict[str, str]:
    col = table.column("default")
    if col is None:
        return {}
    values = code_spans(cells[col])
    if len(values) == len(names):
        return dict(zip(names, values, strict=True))
    if len(names) == 1 and values:
        return {names[0]: values[0]}
    return {}


def env_problems(
    docs: list[Doc], readers: list[Reader], compose: Compose, example: dict, allowed: Allowlist
) -> list[str]:
    problems = []
    read = {}
    for r in readers:
        read.setdefault(r.name, []).append(r)
    known = set(read) | {n for n in compose.substitutions if n.startswith("COMPOSE_")}

    def code_default(name: str) -> tuple[object, str]:
        if name.startswith("COMPOSE_") and name in compose.substitutions:
            default, where = compose.substitutions[name]
            return default, where
        stated = [r for r in read.get(name, []) if r.default is not None]
        if not stated:
            return None, read[name][0].where if name in read else ""
        values = {r.default for r in stated}
        if UNKNOWN in values or len(values) > 1:
            return UNKNOWN, ", ".join(r.where for r in stated)
        return stated[0].default, stated[0].where

    reference = set()
    for table in env_tables(docs):
        is_reference = table.column("default") is not None
        for line, cells in table.rows:
            names = row_names(cells)
            where = f"{table.doc.rel}:{line}"
            for name in names:
                if name not in known:
                    problems.append(f"{where} documents {name}, which no code or Compose reads. Remove it from the doc, or add the reader if the doc is right (D11).")
                elif is_reference:
                    reference.add(name)
            for name, doc_default in row_defaults(table, cells, names).items():
                if name in known:
                    value, code_where = code_default(name)
                    if value is not UNKNOWN and value is not None and doc_default != value:
                        problems.append(f"{where} says {name} defaults to {doc_default!r}; it defaults to {value!r} at {code_where}. The doc is the standard (D11): fix the code, unless the doc is wrong.")
            if len(names) == 1 and (m := re.search(r"[Dd]efaults to `?([A-Za-z0-9_./:-]+)`?", " ".join(cells[1:]))):
                value, code_where = code_default(names[0])
                if value is not UNKNOWN and value is not None and m.group(1) != value:
                    problems.append(f"{where} says {names[0]} defaults to {m.group(1)!r}; it defaults to {value!r} at {code_where}. Fix the doc or the code (D11).")
    for name in sorted(set(read) | set(compose.substitutions) | set(compose.environment)):
        if name not in reference and not allowed.covers(name):
            source = read[name][0].where if name in read else compose.substitutions.get(name, (None, compose.environment.get(name)))[1]
            problems.append(
                f"{name} is read or set at {source} but has no row in an env table with a Default column "
                f"(PROJECT_DOCUMENTATION.md §9). Add the row, or allowlist it in backend/tests/docs/allowlist.yaml [env_undocumented] with a reason."
            )
    for name, (_default, where) in sorted(compose.substitutions.items()):
        if name not in known:
            problems.append(f"{where} substitutes ${{{name}}}, which no code reads. Remove it or read it in the code.")
    for name, where in sorted(compose.environment.items()):
        if name not in read:
            problems.append(f"{where} sets {name} for the container, but no code reads it. Remove it from {COMPOSE} or read it in the code.")
    for name, (_value, no, _commented) in sorted(example.items()):
        if name not in read:
            problems.append(f"{EXAMPLE}:{no} lists {name}, which no code reads. Remove it from {EXAMPLE} or read it in the code.")
    return problems


def env_block_problems(docs: list[Doc], example: dict) -> list[str]:
    """An `env` code block in a doc shows .env.example lines: same names, same values."""
    problems = []
    for doc in docs:
        for _start, info, body in doc.code_blocks():
            if info != "env":
                continue
            for no, line in body:
                if not (m := re.match(r"^\s*([A-Z][A-Z0-9_]*)=(.*)$", line)):
                    continue
                name, value = m.group(1), m.group(2).strip()
                if name not in example or example[name][2]:
                    problems.append(f"{doc.rel}:{no} shows {name}={value}, but {EXAMPLE} has no {name}= line. Show the {EXAMPLE} line, or add it there.")
                elif example[name][0] != value:
                    problems.append(f"{doc.rel}:{no} shows {name}={value}; {EXAMPLE}:{example[name][1]} has {name}={example[name][0]}. Make the doc match {EXAMPLE}.")
    return problems


def compose_guide_problems(docs: list[Doc], compose: Compose, readers: list[Reader]) -> list[str]:
    """Prose such as "COMPOSE_DB_PORT (5434)" and "AI_MODE defaults to rules" matches Compose or the code."""
    code = {r.name: r.default for r in readers if isinstance(r.default, str)}
    problems = []
    for doc in docs:
        for line, text in doc.prose():
            for m in re.finditer(r"\b(COMPOSE_[A-Z_]+) \((\d+)\)", text):
                default = compose.substitutions.get(m.group(1), (None, ""))[0]
                if m.group(2) != default:
                    problems.append(f"{doc.rel}:{line} says {m.group(1)} is {m.group(2)}; {COMPOSE} defaults it to {default!r}. Fix the doc or {COMPOSE}.")
            for m in re.finditer(r"\b([A-Z][A-Z0-9_]{2,}) defaults to `?([A-Za-z0-9_./:-]+)", text):
                name, value = m.group(1), m.group(2).rstrip(".:")
                options = {code.get(name), compose.substitutions.get(name, (None, ""))[0]} - {None}
                if options and value not in options:
                    problems.append(f"{doc.rel}:{line} says {name} defaults to {value!r}; the code and {COMPOSE} default it to {sorted(options)}. Fix the doc, or the code if the doc is right (D11).")
    return problems


def _inputs():
    compose = compose_vars((ROOT / COMPOSE).read_text(encoding="utf-8"))
    example = example_vars((ROOT / EXAMPLE).read_text(encoding="utf-8"))
    return code_readers(), compose, example


def test_env_variables_match_across_code_compose_and_docs():
    readers, compose, example = _inputs()
    allowed = Allowlist("env_undocumented", "name")
    problems = env_problems(guarded_docs(), readers, compose, example, allowed) + allowed.problems()
    assert not problems, report(problems)


def test_env_code_blocks_mirror_env_example():
    _readers, _compose, example = _inputs()
    problems = env_block_problems(guarded_docs(), example)
    assert not problems, report(problems)


def test_compose_defaults_quoted_in_prose_match():
    readers, compose, _example = _inputs()
    problems = compose_guide_problems(guarded_docs(), compose, readers)
    assert not problems, report(problems)
