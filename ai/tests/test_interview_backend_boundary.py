"""Architecture guards of the backend interview code (M4 S2). AST scans, like `test_interview_model_boundary.py`; they read source
files and run nothing.

Where the stored masked CV may go (it still has age, gender and military-service text, Q24), who may import the interview code, and
that the seeker API (M4 S4) is one router module with no placeholder and no agent endpoint, and that the interview code reads no
environment variable and has no LiveKit. Each scanner has a self-test: it flags what it exists to flag.
Like the other guards it sees names and calls, not meaning: a CV text copied into another variable under a name nobody scans,
or code that lives outside the scanned files, is not seen."""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
SERVICES = APP / "services"
PLAN = SERVICES / "interview_plan_service.py"
LIFECYCLE = SERVICES / "interview_service.py"
INTERVIEW_SERVICES = sorted(SERVICES.glob("interview_*.py"))
INTERVIEW_ROUTER = APP / "api" / "v1" / "interview_sessions.py"  # the seeker API (S4): the one module that serves the interview paths
AGENT_ROUTER = APP / "api" / "v1" / "internal_interview.py"  # the Interview Agent's internal API (M5 S1, D80)
INTERVIEW_SCHEMAS = APP / "schemas" / "interview.py"
INTERVIEW_CODE = [
    *INTERVIEW_SERVICES, APP / "models" / "interview.py", ROOT / "scripts" / "purge_interviews.py", INTERVIEW_ROUTER, INTERVIEW_SCHEMAS,
    AGENT_ROUTER, APP / "schemas" / "interview_internal.py", APP / "core" / "agent_auth.py",
]
CV_NAMES = frozenset({"stored_cv", "masked_cv", "cv_text", "masked_text"})


def tree_of(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def call_name(call: ast.Call) -> str:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def imports(tree: ast.AST) -> set[tuple[str, str | None]]:
    out: set[tuple[str, str | None]] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {(a.name, None) for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out |= {(n.module or "", a.name) for a in n.names}
    return out


def name_violations(tree: ast.AST, name: str, allowed: dict[str, tuple[set[int], set[str]]]) -> list[str]:
    """Every load of `name` must be an argument of a call listed in `allowed` ({call: (positions, keywords)}): anything else
    (an assignment to another name, a return, an f-string, another call, an attribute) is a violation."""
    parents = parent_map(tree)
    bad = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)):
            continue
        parent, ok = parents[n], False
        if isinstance(parent, ast.Call) and call_name(parent) in allowed:
            ok = any(a is n for a in parent.args) and next(i for i, a in enumerate(parent.args) if a is n) in allowed[call_name(parent)][0]
        elif isinstance(parent, ast.keyword):
            call = parents[parent]
            ok = isinstance(call, ast.Call) and call_name(call) in allowed and parent.arg in allowed[call_name(call)][1]
        if not ok:
            bad.append(f"{name}@{n.lineno}")
    return bad


def loads(tree: ast.AST, name: str) -> int:
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load))


# ── The stored CV in the plan service ──

PLAN_ALLOWED = {"clean_cv": ({0}, set()), "build_plan": ({2}, {"masked_cv"})}


def test_the_stored_cv_goes_only_to_clean_cv_and_build_plan():
    tree = tree_of(PLAN)
    assert name_violations(tree, "stored_cv", PLAN_ALLOWED) == []
    assert loads(tree, "stored_cv") == 2  # not vacuous: exactly these two uses exist
    params = [(a.arg, fn.name) for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for a in [*fn.args.args, *fn.args.kwonlyargs] if a.arg in CV_NAMES]
    assert params == [("stored_cv", "build_canonical_plan")]  # no other function takes a CV text under any of its names
    assert not any(isinstance(n, ast.Name) and n.id in CV_NAMES - {"stored_cv"} for n in ast.walk(tree))


def test_the_model_bank_gets_the_cleaned_text_and_nothing_else_of_the_cv():
    tree = tree_of(PLAN)
    (bank,) = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and call_name(n) == "make_bank"]
    fourth = bank.args[3]
    assert isinstance(fourth, ast.Attribute) and fourth.attr == "text" and isinstance(fourth.value, ast.Name) and fourth.value.id == "clean"
    (clean,) = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "clean" for t in n.targets)]
    assert isinstance(clean.value, ast.Call) and call_name(clean.value) == "clean_cv" and isinstance(clean.value.args[0], ast.Name) and clean.value.args[0].id == "stored_cv"


PLAN_IMPORTS = {
    ("ai.career.interview", "CriterionInfo"), ("ai.career.interview", "Question"),
    ("ai.embedding.model", "Embedder"), ("ai.embedding.skills", "SkillDictionary"), ("ai.guardrails.blocklist", "Blocklist"),
    ("ai.interview", "CleanCv"), ("ai.interview", "InterviewLimits"), ("ai.interview", "InterviewPlan"), ("ai.interview", "PlanCriterion"),
    ("ai.interview", "build_plan"), ("ai.interview", "clean_cv"), ("ai.interview", "make_bank"), ("ai.interview", "validate_plan"),
    ("ai.llm.client", "LLMClient"), ("app.core.config", "settings"),
    ("collections.abc", "Mapping"), ("collections.abc", "Sequence"),
    ("dataclasses", "dataclass"), ("dataclasses", "fields"), ("dataclasses", "is_dataclass"), ("dataclasses", "replace"),
    ("hashlib", None), ("json", None), ("unicodedata", None),
}


def test_the_plan_service_imports_nothing_that_could_read_or_send_the_cv():
    """No retrieval, no parser, no CV excerpts, no question planner of its own, no model client: the types are all it takes."""
    assert imports(tree_of(PLAN)) == PLAN_IMPORTS


# ── The stored CV in the lifecycle service ──


def test_the_stored_cv_text_is_read_in_one_place_and_handed_to_one_call():
    for path in INTERVIEW_SERVICES:
        tree = tree_of(path)
        reads = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "masked_text"]
        assert len(reads) == (1 if path == LIFECYCLE else 0), path.name
    tree = tree_of(LIFECYCLE)
    (reader,) = [fn for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and fn.name == "_read_stored_cv"]
    assert any(isinstance(n, ast.Attribute) and n.attr == "masked_text" for n in ast.walk(reader))
    assert name_violations(tree, "stored_cv", {"build_canonical_plan": (set(), {"stored_cv"})}) == []
    assert loads(tree, "stored_cv") == 1
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and call_name(n) == "_read_stored_cv"]
    assert len(calls) == 1
    assert not any(isinstance(n, ast.Name) and n.id in {"masked_cv", "cv_text", "masked_text"} for n in ast.walk(tree))
    # The CvDocument model is touched only where the text is read
    users = [fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and any(isinstance(n, ast.Name) and n.id == "CvDocument" for n in ast.walk(fn))]
    assert users == ["_read_stored_cv"]


def test_the_scanner_flags_every_other_use_of_the_stored_cv():
    bad_sources = [
        "def f(stored_cv):\n    return stored_cv\n",
        "def f(stored_cv):\n    other = stored_cv\n    clean_cv(other)\n",
        "def f(stored_cv):\n    print(f'{stored_cv}')\n",
        "def f(stored_cv):\n    make_bank('t', 'j', [], stored_cv)\n",  # the model path must get `clean.text`
        "def f(stored_cv):\n    build_plan([], [], [], stored_cv)\n",  # the wrong position
        "def f(stored_cv):\n    len(stored_cv.splitlines())\n",
        "def f(stored_cv):\n    clean_cv(stored_cv=stored_cv)\n",  # the wrong keyword
    ]
    for source in bad_sources:
        assert name_violations(ast.parse(source), "stored_cv", PLAN_ALLOWED), source
    good = "def f(stored_cv):\n    c = clean_cv(stored_cv)\n    build_plan(a, b, stored_cv, (), d)\n    build_plan(a, b, masked_cv=stored_cv)\n"
    assert name_violations(ast.parse(good), "stored_cv", PLAN_ALLOWED) == []


def test_the_import_scanner_sees_every_form_of_import():
    found = imports(ast.parse("import os\nimport a.b as c\nfrom x.y import z, w as v\nfrom . import q\n"))
    assert found == {("os", None), ("a.b", None), ("x.y", "z"), ("x.y", "w"), ("", "q")}


# ── Who may import the interview code ──

FORBIDDEN_FOR_INTERVIEW = (
    "application_service", "evaluation_service", "talent_service", "offer_service", "gate_service", "job_service",
    "company_project_service", "preference_service", "auth_service", "cv_service", "cv_review_service", "jd_service",
)


def test_the_interview_services_import_no_company_evaluation_or_application_code():
    """Applications and evaluations are never read or written (AI rule 5), and nothing of a company reaches an interview."""
    for path in INTERVIEW_SERVICES:
        modules = {m for m, name in imports(tree_of(path))} | {name for m, name in imports(tree_of(path)) if name}
        for forbidden in FORBIDDEN_FOR_INTERVIEW:
            assert forbidden not in modules, f"{path.name} imports {forbidden}"


NEW_INTERVIEW_NAMES = frozenset(
    {"InterviewSession", "InterviewTurn", "InterviewQuota", "InterviewStatus", "QuotaKind"}
    | {"interview_service", "interview_plan_service", "interview_quota_service", "interview_consent_service", "interview_time", "interview_feedback_service"}
)


def imports_the_new_interview_code(tree: ast.AST) -> list[str]:
    """What of the practice-interview models and services a module imports (the D21 interview *questions* are another feature)."""
    return [
        f"{module}.{name}" if name else module
        for module, name in sorted(imports(tree), key=str)
        if module == "app.models.interview" or module.startswith("app.services.interview_") or name in NEW_INTERVIEW_NAMES
    ]


# The one use of the interview code from outside it (M5 S3, D81): withdrawing the AI consent ends the seeker's sessions that are in progress.
# `consent_service` imports that single function and nothing else of the interview code; a second use is a review point.
CONSENT_WITHDRAWAL_USE = {"backend/app/services/consent_service.py": ["app.services.interview_service.abort_for_consent_withdrawal"]}


def test_no_other_backend_code_imports_the_interview_models_or_services():
    """Not the existing seeker features, not the scoring, not a company route or service: only the interview services, the model
    module, the package that re-exports the models, the interview routers (the seeker's, and the agent's internal one since M5 S1,
    which import services, never the models), and the one named use of D81 (`CONSENT_WITHDRAWAL_USE`)."""
    allowed = {*INTERVIEW_SERVICES, APP / "models" / "interview.py", APP / "models" / "__init__.py", INTERVIEW_ROUTER, AGENT_ROUTER}
    found = {
        path.relative_to(ROOT).as_posix(): imports_the_new_interview_code(tree_of(path))
        for path in sorted(APP.rglob("*.py"))
        if path not in allowed and "__pycache__" not in path.parts
    }
    assert {file: uses for file, uses in found.items() if uses} == CONSENT_WITHDRAWAL_USE
    assert imports_the_new_interview_code(tree_of(LIFECYCLE))  # not vacuous: the allowed modules do import them


def test_the_import_guard_flags_what_it_exists_to_flag():
    for source in (
        "from app.models import InterviewSession\n",
        "from app.models.interview import QuotaKind\n",
        "from app.services import interview_service\n",
        "from app.services.interview_plan_service import seal\n",
        "import app.services.interview_time\n",
    ):
        assert imports_the_new_interview_code(ast.parse(source)), source
    assert imports_the_new_interview_code(ast.parse("from app.schemas.career import InterviewOut\nfrom app.services import career_service\n")) == []


def test_the_interview_services_use_no_row_locks_and_no_sleeping():
    """The stage's concurrency is compare-and-set, unique indexes and leases; a row lock held across a model call is what it avoids."""
    for path in INTERVIEW_SERVICES:
        for n in ast.walk(tree_of(path)):
            assert not (isinstance(n, ast.Attribute) and n.attr in {"with_for_update", "sleep"}), path.name
            assert not (isinstance(n, ast.keyword) and n.arg in {"with_for_update", "nowait"}), path.name


# ── The seeker API: one router, no placeholder, no agent endpoint; no new environment variable, no LiveKit ──


def names_in(tree: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}


def test_the_seeker_api_is_one_router_module_that_main_wires_and_no_other_api_module_touches_the_interview_code():
    api = APP / "api" / "v1"
    assert sorted(p.name for p in api.glob("*interview*")) == ["internal_interview.py", "interview_sessions.py"]
    assert {"interview_sessions", "internal_interview", "no_store", "validation_errors", "install"} <= names_in(tree_of(APP / "main.py"))
    for path in api.glob("*.py"):
        if path not in (INTERVIEW_ROUTER, AGENT_ROUTER):
            assert not any("interview" in module.lower() for module, _ in imports(tree_of(path))), path.name


# Each stage of S4 adds the imports of the routes it adds; a changed set is a review point, like the pins of the services
ROUTER_IMPORTS = {
    ("fastapi", "APIRouter"), ("fastapi", "Depends"), ("fastapi", "Path"), ("fastapi", "Query"), ("fastapi", "Request"), ("fastapi", "status"), ("typing", "Annotated"),
    ("app.core.allowed_methods", "all_methods_route_class"),
    ("app.core.deps", "CurrentUser"), ("app.core.deps", "DbSession"), ("app.core.deps", "get_current_user"), ("app.core.errors", "AppError"),
    ("app.schemas.interview", "ConsentTextOut"), ("app.schemas.interview", "CreatedSessionOut"), ("app.schemas.interview", "HistoryPageOut"),
    ("app.schemas.interview", "FeedbackOut"), ("app.schemas.interview", "InterviewCreateIn"), ("app.schemas.interview", "JoinOut"), ("app.schemas.interview", "SessionOut"),
    ("app.services", "interview_consent_service"), ("app.services", "interview_feedback_service"), ("app.services", "interview_service"),
    ("app.services", "interview_join_service"),  # M5 S4: the join token
    ("app.services.interview_time", "Clock"), ("app.services.interview_time", "utcnow"),  # the clock the router hands to the services
}
SCHEMA_IMPORTS = {
    ("datetime", "datetime"), ("pydantic", "BaseModel"), ("pydantic", "ConfigDict"), ("pydantic", "Field"), ("app.schemas.application", "AI_NOTICE"),
}


def test_the_interview_router_and_its_schemas_import_only_what_they_need():
    """The services and the schemas: never the models, never the engine (`ai.interview`), never a model client or the quota or the
    clock (those are the services' business)."""
    assert imports(tree_of(INTERVIEW_ROUTER)) == ROUTER_IMPORTS
    assert imports(tree_of(INTERVIEW_SCHEMAS)) == SCHEMA_IMPORTS


def placeholder_uses(tree: ast.AST) -> list[str]:
    """What makes a route a placeholder: the status 501, `NotImplemented`, `NotImplementedError`, an agent or internal path."""
    bad = [f"{n.value}@{n.lineno}" for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == 501]
    bad += sorted(names_in(tree) & {"HTTP_501_NOT_IMPLEMENTED", "NotImplemented", "NotImplementedError"})
    bad += [f"path@{n.lineno}" for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("/") and ("internal" in n.value or "agent" in n.value)]
    return bad


def test_the_interview_router_has_no_placeholder_and_no_agent_route():
    assert placeholder_uses(tree_of(INTERVIEW_ROUTER)) == []


def test_the_placeholder_scanner_flags_what_it_exists_to_flag():
    for source in (
        "raise HTTPException(status_code=501)",
        "from fastapi import status\nx = status.HTTP_501_NOT_IMPLEMENTED",
        "return NotImplemented",
        "raise NotImplementedError",
        "router.get('/internal/interview-sessions/{id}/context')",
        "router.post('/agent/events')",
    ):
        assert placeholder_uses(ast.parse(source)), source
    assert placeholder_uses(ast.parse("router.get('/interview-consent')\nreturn current()")) == []


ENV_READERS = {"getenv", "environ", "env_or_default"}


def test_the_interview_code_reads_no_environment_variable():
    for path in INTERVIEW_CODE:
        for n in ast.walk(tree_of(path)):
            assert not (isinstance(n, ast.Attribute) and n.attr in ENV_READERS), path.name
            assert not (isinstance(n, ast.Name) and n.id in ENV_READERS), path.name
    # config.py: the practice-interview settings are constants; the one environment variable of this family is the old blocklist path
    names = []
    for n in ast.walk(tree_of(APP / "core" / "config.py")):
        if isinstance(n, ast.Call) and call_name(n) in ENV_READERS and n.args and isinstance(n.args[0], ast.Constant):
            names.append(n.args[0].value)
    # M5 S1 (D80) added the agent's shared secret; S4 adds the LiveKit project the join token is signed for and the agent's name
    assert sorted(x for x in names if x.startswith(("INTERVIEW_", "LIVEKIT_"))) == [
        "INTERVIEW_AGENT_NAME", "INTERVIEW_AGENT_SECRET", "INTERVIEW_BLOCKLIST_PATH", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL",
    ]


AGENT_SECRET_READERS = {"core/config.py", "core/agent_auth.py"}  # M5 S1 (D80): read in config, checked in the one auth module


LIVEKIT_SECRET_READERS = {"core/config.py", "services/interview_join_service.py"}  # M5 S4: read in config, used to sign the join token
JOIN_SERVICE = APP / "services" / "interview_join_service.py"


def calls_logger(tree: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id in ("log", "logger")
        for n in ast.walk(tree)
    )


def test_livekit_is_in_the_backend_only_as_the_pinned_token_signer_and_the_backend_never_imports_the_agent():
    """M5 S4 (D56, D79, D80): the backend uses one LiveKit package, `livekit-api`, pinned, in one module (`interview_join_service`), only to
    sign a token (`from livekit import api`, no network call). At no stage does it import the agent's code (the agent reaches it over
    HTTP only). Only the settings and the auth module know the agent's secret, and only the settings and the join service the LiveKit
    secret, which the join service never logs."""
    scanned = [*APP.rglob("*.py"), *(ROOT / "backend" / "migrations").rglob("*.py"), *(ROOT / "scripts").glob("*.py")]
    for path in scanned:
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(m.split(".")[0] == "interview_agent" for m, _ in imports(tree) if m), path.name
        livekit_imports = {(m, name) for m, name in imports(tree) if m.split(".")[0] == "livekit"}
        assert livekit_imports == ({("livekit", "api")} if path == JOIN_SERVICE else set()), path.name
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = [line for line in requirements if "livekit" in line.lower() and not line.startswith("#")]
    assert len(pins) == 1 and re.fullmatch(r"livekit-api==\d+\.\d+\.\d+", pins[0]) and int(pins[0].split("==")[1].split(".")[0]) < 2, pins
    sources = {p.relative_to(APP).as_posix(): p.read_text(encoding="utf-8") for p in APP.rglob("*.py")}
    assert {name for name, text in sources.items() if "INTERVIEW_AGENT_SECRET" in text} == AGENT_SECRET_READERS
    assert {name for name, text in sources.items() if "LIVEKIT_API_SECRET" in text} == LIVEKIT_SECRET_READERS
    join = ast.parse(JOIN_SERVICE.read_text(encoding="utf-8"))
    assert "logging" not in {m for m, _ in imports(join)} and not calls_logger(join), "the join service logs nothing: it holds the LiveKit secret"


@pytest.mark.parametrize("source, expected", [("import os\nos.getenv('A')\n", True), ("from x import env_or_default\nenv_or_default('A', '')\n", True), ("x = 1\n", False)])
def test_the_environment_scanner_flags_what_it_exists_to_flag(source, expected):
    tree = ast.parse(source)
    flagged = any((isinstance(n, ast.Attribute) and n.attr in ENV_READERS) or (isinstance(n, ast.Name) and n.id in ENV_READERS) for n in ast.walk(tree))
    assert flagged is expected


# ── The ingest service (M4 S3a) ──

INGEST = SERVICES / "interview_ingest_service.py"
INGEST_IMPORTS = {
    ("ai.interview", "AnswerType"), ("ai.interview", "InterviewPlan"), ("ai.interview", "TopicStatus"), ("ai.interview", "mask_spoken"),
    ("ai.interview", "verified_quotes"), ("ai.interview.types", "LEVEL_RANK"),
    ("app.core.config", "settings"), ("app.core.errors", "AppError"),
    ("app.models", "InterviewSession"), ("app.models", "InterviewTurn"), ("app.models", "User"), ("app.models.interview", "InterviewStatus"),
    ("app.services.interview_plan_service", "plan_digest"),
    ("app.services.interview_time", "Clock"), ("app.services.interview_time", "derive"), ("app.services.interview_time", "now_from"), ("app.services.interview_time", "utcnow"),
    ("collections.abc", "Mapping"), ("dataclasses", "dataclass"), ("datetime", "timedelta"),
    ("json", None), ("logging", None), ("re", None),
    ("sqlalchemy", "func"), ("sqlalchemy", "insert"), ("sqlalchemy", "select"), ("sqlalchemy", "update"),
    ("sqlalchemy.exc", "IntegrityError"), ("sqlalchemy.orm", "Session"),
}
NOT_FOR_INGEST = frozenset(
    {
        "InterviewEngine", "InterviewState", "InterviewQuota", "ai_runtime", "clean_cv", "CvDocument", "CvProfile", "complete_json", "get_llm_client",
        "make_feedback", "feedback_request", "make_bank", "build_plan", "validate_plan", "interview_quota_service", "interview_service",
    }
)


def test_the_ingest_service_imports_only_what_it_needs():
    """The masker, the quote check and the engine's vocabularies; the clock; the models. No engine, no state, no model client."""
    assert imports(tree_of(INGEST)) == INGEST_IMPORTS


def test_the_ingest_service_never_touches_the_engine_a_model_the_cv_the_quota_or_the_feedback():
    tree = tree_of(INGEST)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert used & NOT_FOR_INGEST == set()
    assert "masked_text" not in used and "model_dump" not in used and "to_dict" not in used


def test_the_ingest_functions_name_no_user_and_the_session_id_alone_selects_the_target():
    tree = tree_of(INGEST)
    names = {a.arg for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for a in [*fn.args.args, *fn.args.kwonlyargs]}
    assert not names & {"user", "seeker", "current_user", "company", "request"}


def test_the_ingest_service_writes_only_to_the_session_and_its_turns():
    tree = tree_of(INGEST)
    tables = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and call_name(n) in {"update", "insert", "delete"} and n.args and isinstance(n.args[0], ast.Name):
            tables.add((call_name(n), n.args[0].id))
    assert tables == {("update", "_S"), ("insert", "_T")}  # never a delete, never another table


# ── The feedback service (M4 S3b) ──

FEEDBACK = SERVICES / "interview_feedback_service.py"
FEEDBACK_IMPORTS = {
    ("ai.career.resources", "Resources"), ("ai.embedding.skills", "SkillDictionary"), ("ai.guardrails.blocklist", "Blocklist"),
    ("ai.interview", "FeedbackReport"), ("ai.interview", "InterviewPlan"), ("ai.interview", "SafePlan"), ("ai.interview", "SafeTurn"),
    ("ai.interview", "feedback_request"), ("ai.interview", "make_feedback"), ("ai.interview", "plan_view_from"),
    ("ai.interview", "rules_feedback"), ("ai.interview", "transcript_view_from"),
    ("ai.interview.types", "Turn"), ("ai.llm.client", "LLMClient"), ("ai.parsing.extract", "PROMPT_VERSION"),
    ("app.core.config", "settings"), ("app.core.errors", "AppError"),
    ("app.models", "InterviewSession"), ("app.models", "InterviewTurn"), ("app.models", "User"),
    ("app.models.interview", "InterviewStatus"), ("app.models.interview", "QuotaKind"),
    ("app.services", "ai_runtime"), ("app.services", "career_service"), ("app.services", "interview_quota_service"), ("app.services", "interview_service"),
    ("app.services.interview_plan_service", "has_nul"), ("app.services.interview_plan_service", "has_surrogate"),
    ("app.services.interview_plan_service", "plan_digest"),
    ("app.services.interview_time", "Clock"), ("app.services.interview_time", "as_utc"), ("app.services.interview_time", "now_from"), ("app.services.interview_time", "utcnow"),
    ("dataclasses", "dataclass"), ("datetime", "datetime"), ("datetime", "timedelta"),
    ("logging", None), ("math", None), ("secrets", None),
    ("sqlalchemy", "or_"), ("sqlalchemy", "select"), ("sqlalchemy", "update"),
    ("sqlalchemy.exc", "SQLAlchemyError"), ("sqlalchemy.orm", "Session"),
}
NOT_FOR_FEEDBACK = frozenset(
    {
        "InterviewEngine", "InterviewState", "InterviewQuota", "CvDocument", "CvProfile", "clean_cv", "build_plan", "make_bank", "validate_plan",
        "build_canonical_plan", "complete_json", "get_llm_client", "compose", "ask", "ModelInput", "GatedClient", "mask_spoken", "masked_text",
        "cv_service", "recommendation_service", "evaluation_service", "application_service", "json", "to_dict", "model_dump", "asdict", "dumps",
    }
)


def test_the_feedback_service_imports_only_what_it_needs():
    """The two views and the report maker, the clock, the quota ledger and the lifecycle checks. No CV, no engine, no model client of
    its own, no other seeker feature, no raw serialization."""
    assert imports(tree_of(FEEDBACK)) == FEEDBACK_IMPORTS


def test_the_feedback_service_never_touches_the_cv_the_engine_a_raw_model_call_or_raw_serialization():
    tree = tree_of(FEEDBACK)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert used & NOT_FOR_FEEDBACK == set()
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "masked_text"]


def test_the_feedback_service_writes_only_to_the_session_and_reads_the_turns_in_one_place():
    tree = tree_of(FEEDBACK)
    tables = {(call_name(n), n.args[0].id) for n in ast.walk(tree) if isinstance(n, ast.Call) and call_name(n) in {"update", "insert", "delete"} and n.args and isinstance(n.args[0], ast.Name)}
    assert tables == {("update", "_S")}  # never an insert, a delete or another table
    readers = [fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and any(isinstance(n, ast.Name) and n.id == "_T" for n in ast.walk(fn))]
    assert readers == ["_read"]  # the turns are read once, as plain columns, in the one read transaction


def transcript_mapping_sources(tree: ast.AST) -> list[str]:
    """For every call of `transcript_view_from`: the name its second argument is, or "?" when it is anything else."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and call_name(n) == "transcript_view_from":
            second = n.args[1] if len(n.args) > 1 else None
            out.append(second.id if isinstance(second, ast.Name) else "?")
    return out


def test_the_views_are_built_in_one_place_and_the_turns_are_mapped_by_the_original_plan_order():
    """`plan_view_from` and `transcript_view_from` are called once each, in `_build_views`, and a turn's topic comes from `order` (the
    topic ids of the stored plan as stored), never from `SafePlan.topic_ids`, which skips the items that validation drops (D64)."""
    tree = tree_of(FEEDBACK)
    for name in ("plan_view_from", "transcript_view_from", "rules_feedback", "feedback_request", "make_feedback"):
        callers = [fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) for n in ast.walk(fn) if isinstance(n, ast.Call) and call_name(n) == name]
        assert len(callers) == 1, name
    (builder,) = [fn for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and fn.name == "_build_views"]
    assert {call_name(n) for n in ast.walk(builder) if isinstance(n, ast.Call)} >= {"plan_view_from", "transcript_view_from"}
    assert transcript_mapping_sources(tree) == ["order"]
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "topic_ids" and not isinstance(n.ctx, ast.Store)][1:], "topic_ids is read once, to compare the two orders"


def test_the_mapping_scanner_flags_the_naive_mapping():
    assert transcript_mapping_sources(ast.parse("transcript_view_from(turns, order)")) == ["order"]
    assert transcript_mapping_sources(ast.parse("transcript_view_from(turns, safe_plan.topic_ids)")) == ["?"]
    assert transcript_mapping_sources(ast.parse("transcript_view_from(turns)")) == ["?"]


def test_the_model_call_is_one_function_that_calls_make_feedback_and_the_client_is_taken_once():
    tree = tree_of(FEEDBACK)
    (caller,) = [fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and any(isinstance(n, ast.Call) and call_name(n) == "make_feedback" for n in ast.walk(fn))]
    assert caller == "_model_report"
    clients = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and call_name(n) == "llm" and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "ai_runtime"]
    assert len(clients) == 1
