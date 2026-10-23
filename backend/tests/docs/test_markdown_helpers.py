"""The doc guards' parsers and comparisons on small samples, broken ones included: each guard is shown to fail, with
a message that names the doc place, the code place and the side to fix. The IDs and names here are made up."""
from .claims import Claim
from .markdown import Allowlist, Doc, anchors, tables
from .test_doc_api import Route, api_problems, public_sentence_problems, row_operations, who_kinds
from .test_doc_constants import claim_problems, constant_problems
from .test_doc_env import UNKNOWN, Compose, Reader, compose_vars, env_block_problems, env_problems, example_vars, readers_in
from .test_doc_ids import code_reference_problems, collect_ids, issue_numbers, reference_problems
from .test_doc_links import link_problems, path_problems
from .test_doc_numbers import account_problems, count_problems, migration_problems

D11 = "The doc is the standard (D11)"


def doc(rel: str, text: str) -> Doc:
    return Doc.from_text(rel, text)


def empty(section: str, key: str) -> Allowlist:
    return Allowlist(section, key, data={})


# ── Markdown ──


def test_github_anchors_keep_the_emoji_variation_selector_and_number_duplicates():
    d = doc("a.md", "# ⚙️ Run It Locally\n## 6. AI / ML\n## 3. Câu hỏi còn mở\n## Setup\n## Setup\n```\n# not a heading\n```")
    assert anchors(d) == {"️-run-it-locally", "6-ai--ml", "3-câu-hỏi-còn-mở", "setup", "setup-1"}


def test_table_cells_keep_escaped_pipes_and_code_blocks_are_not_tables():
    d = doc("a.md", "| A | B |\n|---|---|\n| `x`\\|`y` | 2 |\n\n```\n| C | D |\n|---|---|\n```")
    [table] = tables(d)
    assert table.header == ("A", "B") and table.rows == ((3, ("`x`|`y`", "2")),)


def test_allowlist_entries_need_a_reason_and_must_still_be_needed():
    allowed = Allowlist("ids", "ref", {"ids": [{"ref": "Q5"}, {"ref": "Q8", "reason": "history"}]})
    allowed.covers("Q5")
    assert allowed.problems() == [
        "allowlist.yaml [ids] 'Q5' has no reason. Add one or remove the entry.",
        "allowlist.yaml [ids] 'Q8' no longer matches any difference. Remove the entry.",
    ]


# ── Links ──


def test_link_guard_reports_a_missing_anchor_and_a_missing_file():
    a = doc("a.md", "# Top\nSee [b](b.md#setup), [gone](missing.md), [ok](b.md#intro), `[code](x.md)` and [web](https://example.com).")
    b = doc("b.md", "# Intro\n## Set-up")
    docs = {d.rel: d for d in (a, b)}
    assert link_problems([a], exists=lambda rel: rel in docs, doc_for=docs.get) == [
        "a.md:2 links to #setup in b.md, which has no such heading. Closest: #set-up. Fix the link or the heading.",
        "a.md:2 links to 'missing.md', but missing.md does not exist. Fix the link or restore the file.",
    ]


def test_path_guard_reports_a_missing_repo_path():
    d = doc("a.md", "Edit `backend/app/main.py:12`, `backend/app/gone.py` and `ai/prompts/vN/`; `services/x.py` is relative.")
    allowed = Allowlist("paths", "path", {"paths": [{"path": "ai/prompts/vN", "reason": "placeholder"}]})
    problems = path_problems([d], allowed, exists=lambda p: p == "backend/app/main.py") + allowed.problems()
    assert len(problems) == 1
    assert problems[0].startswith("a.md:1 names `backend/app/gone.py`, but backend/app/gone.py does not exist. Fix the path")


# ── IDs ──

DECISIONS = """## 2
| ID | Ngày | Quyết định | Lý do |
|---|---|---|---|
| D1 | 2026-10-13 | chốt Q2 | x |
| D2 | 2026-10-13 | y | z |
| D2 | 2026-10-14 | again | z |

## 3
| # | Câu hỏi | Nguồn |
|---|---|---|
| Q5 | open? | D1 |
"""
ISSUES = """| # | Type | Issue | Where | Status |
|---|---|---|---|---|
| 1 | Config | x | y | Open |
| 2 | Tests | x | y | Fixed |
"""


def test_issue_reference_ranges_and_lists():
    assert issue_numbers("33–39") == list(range(33, 40))
    assert issue_numbers("3, 6 and 26") == [3, 6, 26]


def test_id_guard_reports_a_duplicate_and_unknown_references():
    ids = collect_ids(doc("docs/DECISIONS.md", DECISIONS), doc("PROJECT_DOCUMENTATION.md", ISSUES))
    assert ids.problems == ["docs/DECISIONS.md:6 defines D2 again (first at line 5). Renumber one of them."]
    text = "Per D1 and D9 (Q2 closed, Q5 open, Q7 unknown); see issues 1–3."
    assert reference_problems([doc("README.md", text)], ids, empty("ids", "ref")) == [
        "README.md:1 refers to D9, which docs/DECISIONS.md §2 does not define. Fix the reference or add the decision row.",
        "README.md:1 refers to Q7, which is neither open in docs/DECISIONS.md §3 nor closed by a §2 row. Fix the reference, "
        "or add the question to docs/DECISIONS.md §3.",
        "README.md:1 refers to issue 3, but the issues table in PROJECT_DOCUMENTATION.md has issues up to 2 and no 3. "
        "Fix the reference or restore the issue row.",
    ]
    assert code_reference_problems({"ai/x.py": "# see D2\n# and D42"}, ids) == [
        "ai/x.py:2 refers to D42, which docs/DECISIONS.md §2 does not define. Fix the comment."
    ]


# ── API ──


def test_endpoint_rows_expand_methods_relative_suffixes_and_drop_query_strings():
    [table] = tables(doc(
        "PROJECT_DOCUMENTATION.md",
        "| Method | Path | Who |\n|---|---|---|\n| GET / PUT | `/api/cv/{id}` | Seeker |\n"
        "| POST | `/api/o/{id}/accept` · `/reject` | Seeker |\n| GET | `/api/r?limit=20` | Anyone |\n"
        "| POST / PUT | `/api/a`, `/api/a/{id}` | Company |",
    ))
    rows = [row_operations(table, line, cells) for line, cells in table.rows]
    assert [d.op for d in rows[0][0]] == [("GET", "/api/cv/{id}"), ("PUT", "/api/cv/{id}")]
    assert [d.op for d in rows[1][0]] == [("POST", "/api/o/{id}/accept"), ("POST", "/api/o/{id}/reject")]
    assert [d.op for d in rows[2][0]] == [("GET", "/api/r")]
    assert rows[3] == ([], ["PROJECT_DOCUMENTATION.md:6: 2 methods with 2 paths is ambiguous. Split the row into one row per path."])


def test_who_cells():
    assert who_kinds("Anyone (token optional)") == {"optional"}
    assert who_kinds("Anyone") == {"public", "optional"}
    assert who_kinds("Company (own job)") == {"company"}
    assert who_kinds("Logged in. Filters by seeker") == {"login"}
    assert who_kinds("Recruiter") is None


def test_api_guard_reports_a_wrong_who_a_phantom_and_an_undocumented_endpoint():
    docs = [
        doc("PROJECT_DOCUMENTATION.md", "| Method | Path | Who |\n|---|---|---|\n| GET | `/api/a` | Company |\n| GET | `/api/gone` | Anyone |"),
        doc("README.md", "| Method | Endpoint | Description |\n|---|---|---|\n| GET | `/api/a` | x |"),
    ]
    routes = {("GET", "/api/a"): Route("optional", "backend/app/api/v1/a.py:10"), ("POST", "/api/b"): Route("login", "backend/app/api/v1/b.py:20")}
    assert api_problems(docs, routes, empty("api_undocumented", "endpoint")) == [
        "PROJECT_DOCUMENTATION.md:3 says GET /api/a is for 'Company' (needs a company user (CompanyUser)); the route takes an "
        "optional token (OptionalUser) (backend/app/api/v1/a.py:10). The doc is the standard (D11): fix the route, unless the "
        "doc is wrong (then fix the doc and tell Long).",
        "PROJECT_DOCUMENTATION.md:4 documents GET /api/gone, which no route serves. Remove the row, or add the route if the doc is right (D11).",
        "Undocumented endpoint POST /api/b (backend/app/api/v1/b.py:20). Add a row to the Method/Path/Who table in "
        "PROJECT_DOCUMENTATION.md §4.1, or allowlist it in backend/tests/docs/allowlist.yaml [api_undocumented] with a reason.",
    ]


def test_public_sentence_guard_names_what_is_missing_and_what_is_wrong():
    routes = {
        ("POST", "/api/auth/register"): Route("public", "x.py:1"),
        ("POST", "/api/auth/login"): Route("public", "x.py:2"),
        ("GET", "/health"): Route("public", "x.py:3"),
        ("GET", "/api/jobs"): Route("optional", "x.py:4"),
        ("GET", "/api/jobs/{job_id}/criteria"): Route("optional", "x.py:5"),
        ("GET", "/api/cv/me"): Route("login", "x.py:6"),
    }
    text = "All endpoints except register, login, `/health`, `GET /api/jobs` and `GET /api/cv/me` need `Authorization: Bearer <token>`."
    [problem] = public_sentence_problems([doc("README.md", text)], routes)
    assert problem.startswith("README.md:1 lists the endpoints that need no token.")
    assert "Not listed but tokenless in code: GET /api/jobs/{job_id}/criteria (x.py:5)" in problem
    assert "listed but needing a token in code: GET /api/cv/me (x.py:6)" in problem


# ── Env ──

SOURCE = '''
import os
from pathlib import Path

DEFAULT = "d"
REPO_ROOT = Path(".")
a = env_or_default("A", "1")
b = os.getenv("B", "x")
c = (os.getenv("C") or "").strip() or DEFAULT
d = os.environ["D"]
os.environ["E"] = "written, not read"
f = Path(env_or_default("F", str(REPO_ROOT / "data" / "f.yaml")))
g = os.environ.get("G", compute())
'''
COMPOSE = """x-backend: &backend
  build: .
  environment:
    APP_PORT: ${APP_PORT:-8000}
    FIXED: "1"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: ${DB_USER:-postgres}
  app:
    <<: *backend
    ports:
      - "${COMPOSE_PORT:-3000}:3000"
"""


def test_env_readers_and_their_defaults_from_the_ast():
    got = {(r.name, "?" if r.default is UNKNOWN else r.default) for r in readers_in(SOURCE, "x.py")}
    assert got == {("A", "1"), ("B", "x"), ("C", "d"), ("D", None), ("F", "data/f.yaml"), ("G", "?")}


def test_compose_substitutions_and_the_environment_of_built_services_only():
    compose = compose_vars(COMPOSE)
    assert {k: v[0] for k, v in compose.substitutions.items()} == {"APP_PORT": "8000", "DB_USER": "postgres", "COMPOSE_PORT": "3000"}
    assert compose.environment == {"APP_PORT": "docker-compose.yml:4", "FIXED": "docker-compose.yml:5"}


def test_env_guard_reports_a_wrong_default_a_phantom_an_undocumented_and_a_stale_example_variable():
    readers = [Reader("ALPHA", "backend/app/x.py:3", "1"), Reader("BETA", "backend/app/x.py:4", None)]
    compose = Compose({"COMPOSE_PORT": ("3000", "docker-compose.yml:9")}, {})
    example = {"ALPHA": ("1", 5, False), "OLD_VAR": ("x", 6, False)}
    table = "| Variable | Default | Notes |\n|---|---|---|\n| `ALPHA` | `2` | |\n| `COMPOSE_PORT` | `3000` | |\n| `GHOST` | — | |"
    assert env_problems([doc("PROJECT_DOCUMENTATION.md", table)], readers, compose, example, empty("env_undocumented", "name")) == [
        "PROJECT_DOCUMENTATION.md:3 says ALPHA defaults to '2'; it defaults to '1' at backend/app/x.py:3. "
        "The doc is the standard (D11): fix the code, unless the doc is wrong.",
        "PROJECT_DOCUMENTATION.md:5 documents GHOST, which no code or Compose reads. Remove it from the doc, or add the reader if the doc is right (D11).",
        "BETA is read or set at backend/app/x.py:4 but has no row in an env table with a Default column (PROJECT_DOCUMENTATION.md §9). "
        "Add the row, or allowlist it in backend/tests/docs/allowlist.yaml [env_undocumented] with a reason.",
        ".env.example:6 lists OLD_VAR, which no code reads. Remove it from .env.example or read it in the code.",
    ]


def test_env_code_block_must_mirror_env_example():
    example = example_vars("DB_PORT=5433\n# LLM_MODEL=x\n")
    assert env_block_problems([doc("README.md", "```env\nDB_PORT=5432\nLLM_MODEL=x\n```")], example) == [
        "README.md:2 shows DB_PORT=5432; .env.example:1 has DB_PORT=5433. Make the doc match .env.example.",
        "README.md:3 shows LLM_MODEL=x, but .env.example has no LLM_MODEL= line. Show the .env.example line, or add it there.",
    ]


# ── Constants and claims ──


def test_constant_guard_reports_a_wrong_value_and_an_unknown_name():
    d = doc(
        "PROJECT_DOCUMENTATION.md",
        "| Constant | Value | Status |\n|---|---|---|\n| `RECO_MIN_FIT` / `RECO_MIN_PREF` | `45` / `40` | Current |\n\n"
        "At most `RECO_MAX_NEW_EVALUATIONS` (10) per call; `NO_SUCH_LIMIT` = `3`.",
    )
    problems = constant_problems([d], empty("constants", "name"), env_names=set())
    assert len(problems) == 2
    assert problems[0].startswith("PROJECT_DOCUMENTATION.md:3 says RECO_MIN_FIT = 45; the code has 40 (backend/app/core/config.py:")
    assert D11 in problems[0]
    assert problems[1].startswith("PROJECT_DOCUMENTATION.md:5 names `NO_SUCH_LIMIT`, which is neither a Settings field")


def test_claim_guard_reports_a_changed_number_and_a_lost_sentence():
    claims = (Claim("fit", r"Fit ≥ (\d+)", lambda: (40,), "config.py RECO_MIN_FIT"), Claim("gone", r"never written (\d+)", lambda: (1,), "x"))
    problems = claim_problems([doc("README.md", "Recommend when Fit ≥ 45.")], claims)
    assert problems[0] == (
        "README.md:1 says 'Fit ≥ 45'; the code has 40 (config.py RECO_MIN_FIT). The doc is the standard (D11): fix the code, "
        "unless the doc is wrong (then fix the doc and tell Long)."
    )
    assert problems[1].startswith("Claim 'gone' is not in any doc any more")
    assert len(problems) == 2


# ── Numbers ──


def test_account_and_migration_guards():
    d = doc("README.md", "Log in as `hr@a.test` or `ghost@demo.test`, password `demo9999`.\nMigrations 0001 … 0010; migration `0042`.")
    problems = account_problems([d], {"hr@a.test": 10, "seeker@demo.test": 11}, "demo1234")
    assert problems[0] == "README.md:1 names the demo account ghost@demo.test, which scripts/seed.py does not create. Fix the doc or the seed."
    assert problems[1].startswith("README.md:1 gives the demo password demo9999; scripts/seed.py")
    assert problems[2] == "scripts/seed.py:11 creates seeker@demo.test, which no doc lists. Add it to the demo accounts in the README, or drop it from the seed."
    assert migration_problems([d], ["0001", "0002", "0011"]) == [
        "README.md:2 gives the migrations as 0001 … 0010; backend/migrations/versions runs 0001 … 0011. Fix the doc.",
        "README.md:2 mentions migration 0042, which backend/migrations/versions does not have. Fix the doc.",
    ]


def test_test_count_guard_flags_counts_in_prose_and_code_blocks():
    d = doc(
        "README.md",
        "Expected: `12 passed, 3 skipped`.\nRun the 8 tests in e5.\n```\n40 passed in 2.1s\n```\n"
        "Ask 3–10 questions; 5 pages; connection to port 5432 failed.",
    )
    problems = count_problems([d])
    assert [p.split(" gives")[0] for p in problems] == ["README.md:1", "README.md:1", "README.md:2", "README.md:4"]
    assert problems[0] == (
        "README.md:1 gives a test count ('12 passed'). Counts go stale: describe what must pass instead, "
        "and use `pytest --collect-only -q | tail -1` to count."
    )
