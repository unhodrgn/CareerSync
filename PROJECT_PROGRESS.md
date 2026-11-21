# CareerSync — Project Progress Tracker

> **Mục đích:** Theo dõi các phase, milestone, task, kết quả kiểm thử, quyết định và blockers của dự án CareerSync.  
> **Last updated:** 22/11/2026 (KST)  
> **Repository:** `D:\dev\project\CareerSync`  
> **Branch (last reported):** `feature/ai-avatar-poc`  
> **Product:** CareerSync — Criteria-Based Hiring & Job Matching Platform

---

## 1. Project Overview

| Thông tin | Nội dung |
|---|---|
| Project | CareerSync |
| Product scope | Criteria-Based Hiring & Job Matching Platform |
| Frontend | React 19, TypeScript 6, Vite 8 |
| Backend | FastAPI 0.142 |
| Database | PostgreSQL 16 target; SQLite used for local tests |
| ORM / migrations | SQLAlchemy 2.1, Alembic |
| AI interview core | Rules engine + optional LLM integration + evidence-grounded feedback |
| Realtime POC | `interview_poc/` — separate avatar/realtime proof of concept |
| Main feature tracks | Hiring/job matching, AI Interview, CareerSync Chatbot |
| Repository documentation | `PRODUCT.md`, `DECISIONS.md`, `PROJECT_DOCUMENTATION.md` |

### Overall Progress

- [x] Product and architecture documentation baseline — see M0
- [x] AI Interview rules engine and lifecycle — M1
- [x] LLM turn integration and deterministic fallback — M2
- [x] CV privacy and architecture/serialization guards — M2.1 / M2.1.1
- [x] Evidence-grounded interview feedback — M3
- [x] Interview database and seeker API implementation, S1–S4.5 — M4 *(implemented and locally verified; verified on PostgreSQL: the migrations (D70), the 140 PostgreSQL-gated tests, the JSONB diagnostics and the concurrency tests (D77); not production-ready: Q24, Q35, Q39 and M5 are open)*
- [x] PostgreSQL test safety guards and N1–N9 test additions *(the guards are verified locally and ran in front of every PostgreSQL step; N1–N9 executed and passed on PostgreSQL in Tiers B and C, D77)*
- [x] Unicode surrogate input hardening *(locally verified; the PostgreSQL JSONB diagnostics ran on 21 and 22/11/2026: they found the Feedback and Plan gap, which D73 closes, and they pass)*
- [x] PostgreSQL migration QA (M0 reset and M1 restore) on the approved existing test database *(passed 21/11/2026 and accepted by Long; outcome recorded in D70; the database ends at revision `0012` with no data and no seed)*
- [x] PostgreSQL test tiers, JSONB diagnostics and concurrency verification against the same database *(§4A.5; Tiers A, B and C, the race repeats and the JSONB diagnostics passed on 21 and 22/11/2026 after the fixes of D73 to D75; the schema was restored and `alembic check` passed on 22/11/2026; outcome in D77)*
- [x] Q42 resolved *(the one index `uq_job_criteria_job_name` is filtered out of the comparison in `backend/migrations/env.py`; `alembic check` exits 0 at head; D76)*
- [ ] M5 — realtime interview agent (planned around LiveKit)
- [ ] M6 — frontend integration for AI Interview
- [ ] CareerSync Chatbot feature — maintain its progress under this repository; consolidate the latest implementation status in this tracker
- [ ] Final integration, end-to-end testing and release readiness

### Latest Local Verification

**Latest full-suite result (22/11/2026, local, SQLite):** **3,525 passed, 140 skipped** (3,665 collected; 264.96 s; exit code 0).

| Test group | Result | Command, from the repository root, and scope |
|---|---:|---|
| Full suite | 3,525 passed, 140 skipped | `pytest`. The 140 skips are the PostgreSQL-gated tests, which skip without a PostgreSQL URL. |
| Dedicated surrogate tests | 127 passed | `backend/tests/test_interview_surrogate.py`: SQLite service-boundary tests. |
| Tests of the D73 and D74 fixes | 59 passed | `backend/tests/test_interview_surrogate_model_text.py` and `backend/tests/test_cv_upload_nul.py`. |
| Test database safety guards | 283 passed | `backend/tests/test_db_safety.py`: guard logic and CLI checks; they do not show PostgreSQL behavior by themselves. |
| Architecture tests | 340 passed | The four files `ai/tests/test_interview_backend_boundary.py`, `test_interview_cv_boundary.py`, `test_interview_model_boundary.py` and `test_interview_transcript_boundary.py`. |
| Documentation tests | 44 passed | `backend/tests/docs`. |

Every row above ran on 22/11/2026 from the repository root with `CAREERSYNC_DOTENV=0` and `AI_MODE=rules`, and with `TEST_DATABASE_URL`, `TEST_DATABASE_EXPECTED_NAME`, `TEST_DATABASE_CONFIRM_DESTRUCTIVE` and `DATABASE_URL` removed from the command, so **these local rows made no PostgreSQL connection**. The gated tests skip in them, and the skips prove nothing about PostgreSQL.

**Verified on PostgreSQL (separate evidence; never merged into the local rows).** Run against `careersync_db` on 21 and 22/11/2026 (§4A.5, D77), each step with every collected test passing and none skipped:

| PostgreSQL step | Result | Time |
|---|---:|---:|
| Tier A, 12 files (S1, second run, before D75) | 194 passed | 156.67 s |
| Race set, five consecutive runs (S2, before D75) | 105 passed in each of 5 runs | 84.10 to 105.52 s per run |
| JSONB surrogate diagnostics (S3, second run) | 16 passed (18 deselected by `-k`) | 13.64 s |
| Tier B, the interview files (S4, second run) | 1,488 passed | 1,081.23 s |
| Tier C, the whole suite (S5) | 3,665 passed | 1,401.33 s |
| Restore and `alembic check` (22/11/2026) | `0012 (head)`, 28 application tables, empty; `alembic check` exit code 0 | |

The PostgreSQL rows ran with the hashing embedder and the fake LLM (no model call, no real CV). The migration QA of 21/11/2026 (§4A.4, D70) is separate evidence for the migrations. Tier A and the race set are now collected as 203 and 114 (D75 added nine tests to the quota file after their runs); that is not a PostgreSQL result. This is not production readiness (Q24, Q35, Q39 open; M5 not started).

---

## 2. Phase 1 — Interview Architecture & Documentation (M0)

**Mục tiêu:** Chốt kiến trúc AI Interview, boundary giữa rules engine và LLM, lifecycle, privacy và các quyết định nền tảng.

- [x] Establish AI Interview architecture and module boundaries
- [x] Document the M0 baseline
- [x] Record decision set D51–D58
- [x] Record subsequent interview architecture decisions, including D63 and related guards
- [x] Keep `ai/interview/` core separate from the future realtime avatar/agent implementation
- [x] Keep model access behind the approved `compose()` / `ask()` flow

**Deliverables:**
- `PRODUCT.md`
- `DECISIONS.md`
- `PROJECT_DOCUMENTATION.md`
- `ai/interview/` architecture and related implementation documents

**Status:** Completed

---

## 3. Phase 2 — AI Interview Core (M1–M3)

**Mục tiêu:** Xây dựng interview logic có thể kiểm thử độc lập, có deterministic behavior và giới hạn rõ ràng khi sử dụng LLM.

### 3.1 M1 — Pure Rules Engine & Lifecycle

- [x] Implement pure interview rules engine
- [x] Implement interview lifecycle handling
- [x] Implement PII scrubbing / safe-text boundary
- [x] Keep the core rules path independent from real model calls
- [x] Add automated tests for deterministic behavior and lifecycle rules

**Status:** Completed — local tests pass.

### 3.2 M2 — LLM Turn Integration

- [x] Build `ModelInput` from `SafeText` through `compose()`
- [x] Route model requests through `ask()`
- [x] Add strict structured-output validation
- [x] Add deterministic fallback when the model path fails or returns invalid output
- [x] Keep normal test runs free from real model calls
- [x] Keep `ai/llm/client.py` as a sensitive boundary; do not modify without explicit review

**Status:** Completed — local tests pass.

### 3.3 M2.1 — CV Privacy Guard

- [x] Add CV privacy guard to the interview flow
- [x] Keep masked/safe text as the model-input boundary
- [x] Add tests for known PII patterns
- [x] Document the limitation of vocabulary-based masking

**Known limitation:** Vocabulary-based masking cannot guarantee removal of every possible PII form. Do not describe it as complete anonymization.

**Status:** Implemented and locally verified, with known limitations.

### 3.4 M2.1.1 — Architecture & Serialization Guards

- [x] Add architecture guards
- [x] Add serialization guards
- [x] Add regression tests for prohibited dependencies / unsafe serialization paths

**Status:** Completed — local architecture tests pass.

### 3.5 M3 — Evidence-Grounded Feedback

- [x] Implement feedback generation based on interview evidence
- [x] Require exact quote evidence for feedback claims
- [x] Restrict recommended resources to an allow-list
- [x] Exclude numeric scores, rankings and hiring verdicts
- [x] Add validation and fallback tests

**Status:** Completed — local tests pass.

---

## 4. Phase 3 — Interview Database & Seeker API (M4)

**Mục tiêu:** Persist interview sessions and turns, expose the seeker-facing API, and enforce transaction, quota, privacy and concurrency rules.

### 4.1 Database & API Implementation

- [x] Implement M4 database models and migration `0012`
- [x] Implement seeker consent endpoint — `GET /api/interview-consent`
- [x] Implement session creation — `POST /api/jobs/{job_id}/interview-sessions`
- [x] Implement session history — `GET /api/interview-sessions`
- [x] Implement session detail — `GET /api/interview-sessions/{session_id}`
- [x] Implement session end — `POST /api/interview-sessions/{session_id}/end`
- [x] Implement session deletion — `DELETE /api/interview-sessions/{session_id}`
- [x] Implement feedback get-or-create — `POST /api/interview-sessions/{session_id}/feedback`
- [x] Implement S1–S4.5 service and route stages
- [x] Implement validation/error sanitization for interview routes (D68)
- [x] Record the route/task staging clarification in D69

**Important API notes:**
- There is no separate `GET` feedback endpoint. The feedback `POST` is get-or-create.
- The End API does not insert the closing turn/agent event. That belongs to the future agent's `record_end` flow.
- Deleting a live session does not itself disconnect a future realtime agent. M5 must detect deletion/404 and stop or disconnect appropriately.

### 4.2 M4 Verification Before PostgreSQL QA

- [x] Verify M4 service and route behavior using local tests
- [x] Verify feedback lease behavior, retry limits and token fencing
- [x] Verify feedback generation occurs outside the transaction
- [x] Verify deletion during generation and lease-loss handling
- [x] Verify retention and logical read-hiding behavior through local tests
- [x] Verify API error sanitization and no-store behavior
- [x] Verify migrations against PostgreSQL *(21/11/2026, D70: upgrade to head, downgrade to `0011`, upgrade again; schema checked; one accepted cosmetic `alembic check` difference, Q42)*
- [x] Verify PostgreSQL JSONB behavior *(the diagnostics and the JSONB tests passed on PostgreSQL after D73; D77)*
- [x] Verify PostgreSQL row-lock and concurrency behavior *(the concurrency tests passed in Tiers A, B and C, and five consecutive runs of the race set passed before D75; the race set was not repeated five times on the code with D75; D77)*

**Earlier local baseline:** 3,088 passed, 57 skipped before Stage 1 guard and surrogate additions. This is historical; the latest full-suite result is recorded in Section 1.

**Status:** Implemented and locally verified; verified on PostgreSQL (migrations, D70; gated tests, JSONB and concurrency, D77). Not production-ready: Q24, Q35 and Q39 are open and M5 is not started.

### 4.3 M4 Operational Rules and Known Limits

- [x] Session retention uses 30-day logical read hiding plus lazy purge
- [ ] Configure an external scheduler for physical retention purge *(outside the current implementation scope)*
- [ ] Implement realtime-agent reaction to session deletion in M5
- [ ] Implement agent-owned closing-turn/event recording in M5

---

## 4A. Phase 4 — PostgreSQL Safety Hardening & QA

**Mục tiêu:** Verify migrations, JSONB, database behavior and concurrency against the approved existing PostgreSQL test database without connecting to an unintended database.

### 4A.1 Stage 1 — Safety Guards and PostgreSQL-Gated Tests

- [x] W1 — accept only in-memory SQLite URLs for SQLite test mode; reject file-backed SQLite
- [x] W2 — verify `current_database()` against the explicit expected database name after connection
- [x] W3 — reject guarded libpq environment variables when present, including empty values
- [x] W5 — add `backend/tests/db_safety.py` preflight modes `--no-connect` and `--app`
- [x] Require explicit expected database name, port, loopback URL and exact destructive confirmation for approved existing-database mode
- [x] Preserve the existing `_pgtest` disposable-database mode
- [x] Call identity verification before the test fixture's `drop_all`
- [x] Add N1–N9 PostgreSQL-gated tests (80 tests)
- [x] Add safety guard regression tests

**Local verification:**
- `backend/tests/test_db_safety.py`: **283 passed**
- Full suite after Stage 1: **3,329 passed, 137 skipped**
- PostgreSQL-gated N1–N9 tests were added here and were later **run against PostgreSQL** (§4A.5: Tier B and Tier C passed, D77). The numbers above are those of the day Stage 1 ended.

**Status:** Completed locally; executed and passed on PostgreSQL (D77).

### 4A.2 Unicode Surrogate Hardening

- [x] Reject direct surrogate code points U+D800–U+DFFF at the interview ingest boundary
- [x] Return the existing 422 bad-turn error with the fixed text field indicator
- [x] Reject surrogate input before duplicate/gap lookup, guard update or database write
- [x] Preserve valid Unicode scalar values, including Vietnamese, Korean, CJK, emoji and ZWJ sequences
- [x] Accept valid JSON-escaped surrogate pairs after JSON decoding to a valid astral scalar
- [x] Add 127 dedicated SQLite tests using explicit `chr()` fixtures
- [x] Add PostgreSQL JSONB diagnostics for lone surrogate rejection and astral-character storage
- [x] Execute the JSONB diagnostics against PostgreSQL *(21/11/2026: two failed, which led to D73; after D73 they pass; D77)*

**Local verification:**
- Dedicated surrogate tests: **127 passed**
- Full suite: **3,456 passed, 140 skipped**

**Diagnostic outcome (21/11/2026, closed by D73):** the Feedback and Plan services checked only NUL. On PostgreSQL a lone surrogate in a model-written Feedback value reached the caller as a raw database error (two diagnostics failed), so the services now refuse a surrogate as they refuse a NUL (D73). The Anthropic client already refuses a surrogate escape as invalid JSON, so D73 is a guard at the service boundary and not a failure seen in production. The diagnostics pass on PostgreSQL after D73 (D77).

**Status:** Implemented, locally verified and verified on PostgreSQL (D73, D77).

### 4A.3 Stage 3 — Read-Only PostgreSQL Identity & Inventory

- [x] Configure the three required environment variables in the terminal that launches Claude Code *(as reported by Long; the read-only inventory below could not have run otherwise)*
- [x] Pass `python backend/tests/db_safety.py --no-connect` *(as reported by Long; its output was not re-examined in Stage 3.1)*
- [x] Verify exact database identity with `verify_identity()` *(`careersync_db`, user `postgres`; reported by Long)*
- [x] Verify PostgreSQL version is 16.x *(16.15)*
- [x] Verify transaction isolation and loopback connection *(read committed; host binding `127.0.0.1:5434`)*
- [x] Inspect current Alembic revision *(`0011`)*
- [x] Inventory existing tables *(25 application tables + `alembic_version`)* and compare against expected model tables *(source-side comparison done in Stage 3.1, no differences; accepted by Long on 21/11/2026)*
- [ ] Record row counts only; do not read row contents or PII *(waived, not done: Long confirmed that all data in the database are disposable test data, D71; no row counts were recorded)*
- [x] Check other active PostgreSQL sessions *(0 at inventory time)*
- [x] Stop and submit the read-only inventory for review *(reviewed and accepted by Long on 21/11/2026)*

**Verified read-only inventory (reported 21/11/2026; executed inside a `READ ONLY` transaction):**

| Item | Value |
|---|---|
| Compose project / file | `careersync` / `docker-compose.yml` |
| Container / image | `careersync-db-1` / `postgres:16` |
| Database / user | `careersync_db` / `postgres` |
| Docker volume | `careersync_pgdata` |
| Host binding | `127.0.0.1:5434` |
| Server version / isolation | PostgreSQL 16.15 / read committed |
| Alembic revision | `0011` |
| Tables | 25 application tables + `alembic_version` (revision `0011`) |
| Other active connections | 0 |

**Earlier attempt (20/11/2026): BLOCKED before connection** — `TEST_DATABASE_URL` was absent, `python backend/tests/db_safety.py --no-connect` exited with code `2`, and no connection was made. Superseded by the inventory above.

**Stage 3 status:** complete (21/11/2026). Identity, inventory and the Stage 3.1 reconciliation are accepted by Long; the only open item is the waived row count above. This is read-only evidence: nothing destructive had run at that point (M0 and M1 ran later: §4A.4).

### 4A.3a Stage 3.1 — Source–Database Reconciliation (review only)

Static review on 21/11/2026 with `CAREERSYNC_DOTENV=0` and `AI_MODE=rules`: no PostgreSQL or Docker connection, no pytest, no Alembic command, no DDL/DML, no source or migration change. `.env` and `.mcp.json` were not opened. Metadata and the Alembic graph were read from files (lazy engine, `ast` parsing, `ScriptDirectory`).

**Findings**

- `Base.metadata` has **28** tables. **25** are expected at revision `0011` and match the database inventory exactly (no missing, no extra table). The other **3** — `interview_sessions`, `interview_turns`, `interview_quota` — are introduced by migration `0012`; they are expected to be absent now.
- Alembic graph is linear: `0001 → 0002 → … → 0011 → 0012`. One base (`0001`), **one head (`0012`)**, no `branch_labels`, no `depends_on`. `0012` has `down_revision = "0011"`: it is the direct successor.
- `0012` creates 3 tables, 6 explicit indexes (one partial unique, `uq_interview_sessions_active`), 1 unique constraint, 10 check constraints and 5 foreign keys (all `ON DELETE CASCADE`), plus the implicit primary-key indexes and two serial sequences. It changes no existing table and adds no enum, extension or data. `downgrade()` drops the same objects in dependency order.
- Name-level drift: the 80 named indexes/constraints in the migrations equal the 80 in the models. Column-level drift across `0001`–`0011` could not be assessed statically, and no test executes migrations `0001`–`0011`; the first real check is `alembic check` at M1.
- `db` fixture: setup = identity check → `drop_all` → `create_all` (all 28 tables); teardown = `drop_all`. `alembic_version` is not in `Base.metadata`, so the fixture never touches it.

**M0 → M1 verdict:** valid, with conditions. After an M0 test completes, the fixture leaves no application tables (only a stale `alembic_version = 0011`), so `alembic stamp --purge base` and `alembic upgrade head` build from empty without colliding with `create_all`. If M0 teardown does not complete, `0001` fails on an existing table.

**Plan corrections (accepted by Long on 21/11/2026; all applied in §4A.4 and recorded in D71)**

1. The exact M0 test is named, with a check that it ran rather than skipped.
2. The M1 prerequisites are written out: `DATABASE_URL` equal to `TEST_DATABASE_URL`, `CAREERSYNC_DOTENV` set to `0`, `python backend/tests/db_safety.py --app` passing first, and Alembic run from `backend/`. Without `DATABASE_URL`, `config.py` falls back to `localhost:5432`, not the Compose port `5434`, and `env.py` has no identity check of its own.
3. "Do not use Docker" is replaced by the real rule: only the existing container and volume; never `docker compose up` for the whole project, because its `init` service runs `alembic upgrade head` and `scripts/seed.py`.
4. The wipe is confirmed: all data are disposable; no automatic backup; no automatic seed.
5. `alembic check` differences are triaged by a fixed rule, and the QA stage is not passed while one is unresolved.

**Status:** Stage 3.1 closed by Long's acceptance. The plan was final at that point and no database-changing operation had run or been authorized; M0 and M1 later ran under it (§4A.4, D70).

### 4A.4 Destructive Reset & Migration Verification — executed 21/11/2026; migration QA passed (D70)

**Executed on 21/11/2026: M0 after Long's separate approval, then M1 after a second one. The migration QA passed; the outcome is in D70 and under "Result" at the end of this section.** The plan below is kept as the procedure, with the three amendments of 21/11/2026 marked *amended*. Writing or accepting a plan is never an approval to run it. What may be destroyed is recorded in D71.

**Approved scope (D71)**

- Everything in `careersync_db` is disposable test data and may be wiped (confirmed by Long). M0 removes every application table and all of its data. M1 recreates the schema through Alembic only and leaves the database empty.
- No automatic seed: demo data is added only if Long approves it later, explicitly. No automatic backup: none is taken before M0.
- Docker: use only the existing container `careersync-db-1` and its existing volume `careersync_pgdata`. Never run `docker compose up` for the whole project: its `init` service runs the Alembic upgrade and the seed script. Create no new database, container or volume. If the container is stopped, start that same container; do not recreate it.
- Never run `alembic downgrade base`. The only downgrade in this plan goes to revision `0011`.
- The safety guard of the test fixture (`backend/tests/db_safety.py`) is never bypassed or edited.

**Environment.** Long sets these in the terminal that runs the commands (under Claude for VS Code, in the `env` block described below). Never print, echo, paste or record a value other than the fixed ones below, and never open `.env` or `.mcp.json`.

| Name | Required value |
|---|---|
| `TEST_DATABASE_URL` | A PostgreSQL URL for host `127.0.0.1`, port `5434`, database `careersync_db`, with no query parameter other than `connect_timeout`, `application_name` or `sslmode`. The credentials stay inside the URL and are never shown. |
| `TEST_DATABASE_EXPECTED_NAME` | `careersync_db` |
| `TEST_DATABASE_CONFIRM_DESTRUCTIVE` | `drop-all-tables-in:careersync_db` (the fixed prefix and the database name, exactly) |
| `CAREERSYNC_DOTENV` | `0` |
| `AI_MODE` | `rules` |
| `DATABASE_URL` | Absent for the preflight and for M0. For M1 only: set to exactly the value of `TEST_DATABASE_URL`. |
| `PGHOST`, `PGHOSTADDR`, `PGPORT`, `PGDATABASE`, `PGSERVICE`, `PGSERVICEFILE`, `PGOPTIONS`, `PGTARGETSESSIONATTRS`, `PGLOADBALANCEHOSTS` | Absent. The guard refuses a variable that is present, even an empty one. |

The root `conftest.py` sets `CAREERSYNC_DOTENV` to `0`, removes `AI_MODE` and the LLM keys, and selects the hashing embedder, so pytest never calls a model. The variables above stay set anyway for the commands that are not pytest. Alembic reads only `DATABASE_URL` (`backend/migrations/env.py`) and has no identity check of its own, so the `--app` preflight below is the only guard in front of it. Without `DATABASE_URL`, `config.py` would fall back to `localhost:5432`, not to the Compose port.

**Interpreter (amended 21/11/2026).** Every Python, Alembic and pytest command in this section uses `d:\dev\project\CareerSync\.venv\Scripts\python.exe`: wherever a command below says `python`, run that interpreter, and run Alembic as `<that python> -m alembic`. The IDE terminal can have the `interview_poc` virtual environment active, and its `python` has none of the backend packages (the first run of the guard script failed with `ModuleNotFoundError` for `sqlalchemy`).

**Environment under Claude for VS Code (amended 21/11/2026).** The extension does not inherit variables from a separate terminal, so the environment above is supplied through the `env` block of `.claude/settings.local.json` (gitignored). The block applies to every command, so `DATABASE_URL` cannot be unset inside a session: the unset of M1.10 means removing it from the block. Remove the whole block when the QA ends. Its contents are never opened, printed or recorded.

**M0 smoke test: exactly one test**

`backend/tests/test_matching_models.py::test_seeker_preferences_store_recommendation_inputs`

```powershell
python -m pytest "backend/tests/test_matching_models.py::test_seeker_preferences_store_recommendation_inputs" -q -rs -p no:cacheprovider
```

Run from the repo root, only after the preflight. Why this test:

- It uses the destructive `db` fixture (through `world`, which depends on `db`), so setup runs the identity check, then `drop_all`, then `create_all` of every model table, and teardown runs `drop_all`.
- It has no skip or xfail marker and no condition, and it is a single plain function, not parametrized, so the node ID selects exactly one test.
- It touches only ordinary tables (companies, users, job postings and the three seeker-preference child tables). The child lists are ordered by id in the model, so the assertions do not depend on row order. It uses no JSON column, no database error and no clock.
- It makes no model call and no network call.

Why teardown runs: `db` is a function-scoped generator fixture, so the code after `yield` (close the session, `drop_all`, dispose the engine) runs as its finalizer after the test, whether the test passes or fails. `world` is finalized first and has no teardown of its own, so `db` is finalized last. Limits: the finalizer does **not** run if setup fails before `yield` (for example `drop_all` or `create_all` stops part-way) or if the process is killed. For that reason M0.2 below is mandatory. Also, if `TEST_DATABASE_URL` were missing, this same test would pass against in-memory SQLite and touch nothing. A pass proves nothing by itself; the M0.2 check does.

Expected result: pytest ends with the one test passed, none skipped or deselected, exit code zero.

**Sequence**

Preflight (no database change):

- [x] P1 The environment matches the table above. `DATABASE_URL` and the nine `PG*` names are absent. Presence checks print only true or false, never a value. *(Done: values compared in code, booleans only.)*
- [x] P2 `python backend/tests/db_safety.py --no-connect` exits with code `0`. *(Done with the `.venv` interpreter; the first attempt, under the `interview_poc` interpreter, failed on a missing package: see "Interpreter".)*
- [x] P3 `python backend/tests/db_safety.py` (read-only identity check, no `--app`) exits with code `0`. *(Done.)*
- [x] P4 Read-only Docker check: `careersync-db-1` is running, and no other `careersync` container is. Use `docker ps`, not `docker compose` (Compose reads `.env`). *(Done: only `careersync-db-1`, healthy.)*
- [x] P5 Read-only: no other session is connected to `careersync_db`. *(Done: no other client session, counted by a short script that prints only the count.)*
- [x] P6 `python -m pytest --collect-only -q` with the node ID above collects exactly that one test. Collection opens no database connection. *(Done.)*

M0 (needs Long's separate approval):

- [x] M0.1 Run the node ID command once. *(Done: one test, passed, none skipped or deselected, exit code `0`.)*
- [x] M0.2 Read-only post-check: `careersync_db` has no application table, and `alembic_version` still exists with value `0011`. If any application table remains: stop, do not start M1, report. *(Done: no application table; `alembic_version` held `0011`.)*

M1 (needs Long's approval after M0.2 is reported; Alembic is always `python -m alembic`, run from `backend/`):

- [x] M1.1 In the same terminal set `DATABASE_URL` to the value of `TEST_DATABASE_URL`, without echoing it. *(Done: under Claude for VS Code it came from the `env` block; compared equal to `TEST_DATABASE_URL` without printing.)*
- [x] M1.2 From the repo root, `python backend/tests/db_safety.py --app` exits with code `0`. Then change into `backend/`. *(Done.)*
- [x] M1.3 `python -m alembic stamp --purge base`, then `python -m alembic current` shows no revision. *(Done.)*
- [x] M1.4 `python -m alembic upgrade head` runs every revision from `0001` through `0012` without error. *(Done.)*
- [x] M1.5 `python -m alembic current` shows `0012 (head)`, and `python -m alembic heads` shows that one head only. *(Done.)*
- [x] M1.6 Read-only schema verification: 28 application tables plus `alembic_version` holding `0012`. For the three interview tables: columns and defaults, primary keys, five foreign keys all `ON DELETE CASCADE` (none from the quota table to a session), six explicit indexes (`uq_interview_sessions_active` unique and partial on the three active statuses), one unique constraint, ten named check constraints, `jsonb` for the JSON columns and `timestamptz` for the moments. *(Done: every item matched; every table empty except `alembic_version`.)*
- [x] M1.7 `python -m alembic check`. Record the complete output and classify every difference with the triage rule below. *(Done: one difference, `uq_job_criteria_job_name` on `job_criteria`; accepted by Long as cosmetic drift, D70, Q42.)*
- [x] M1.8 `python -m alembic downgrade 0011`; `alembic current` shows `0011`; read-only: the three interview tables are absent and the other 25 are unchanged. *(Amended 21/11/2026: `alembic check` stops below head with "Target database is not up to date", so do not run it here. Run a read-only `compare_metadata` through the Alembic API instead, set up like `backend/migrations/env.py` (connection and `target_metadata` only) and writing no revision file, and record its full list of differences.)* *(Done: eleven differences, namely the three interview tables and their six explicit indexes as additions, plus the `uq_job_criteria_job_name` pair.)*
- [x] M1.9 `python -m alembic upgrade head`; repeat M1.5 to M1.7. *(Done: same results; the other 25 tables are identical to the first time at head; the comparison at head also gave only the `uq_job_criteria_job_name` pair.)*
- [x] M1.10 End state: schema at head, `alembic_version` holding `0012`, no data, no seed. Unset `DATABASE_URL` in the terminal. *(End state verified. `DATABASE_URL` was unset inside the session, but the `env` block supplies it again to every command, so it stays set until Long removes it from the block.)*

**Alembic check triage.** Migration `0012` creates only the three interview tables and their own indexes and constraints. It changes no existing table, index or constraint (verified statically in Stage 3.1).

- Expected: `alembic check` reports no difference at head. At `0011` (M1.8) the comparison (`compare_metadata`; amended 21/11/2026, because `alembic check` does not run below head) may report only the three interview tables and their indexes as additions, because the models are ahead of that schema.
- Report every difference verbatim: the object, its table and the kind of change.
- A difference on an object of the three interview tables is a `0012` finding.
- A difference on any other object is classified as potential pre-existing drift **only after** checking that `0012` did not touch it: the object is not one of the interview objects, and the same difference appears at `0011` (M1.8) and again at head. Anything else stays unclassified and is reported as such.
- The QA stage is not marked passed while any difference is unresolved. A fix is a schema change (a new migration) and needs its own plan and Long's approval.

**M0 readiness checklist** (all true before Long is asked to approve M0):

- [x] Stage 3 and Stage 3.1 accepted by Long (21/11/2026).
- [x] Destructive scope recorded (D71).
- [x] Environment set by Long as in the table; P1 to P3 pass.
- [x] Only `careersync-db-1` is running (P4); no other session is connected (P5).
- [x] The node ID collects (P6).
- [x] Long's explicit approval of M0, in a separate message *(given 21/11/2026; M1 was approved separately afterwards)*.

**Result (21/11/2026)**

| Step | Outcome |
|---|---|
| Preflight P1 to P6 | Passed. |
| M0 | The smoke test ran once and passed, nothing skipped. The post-check found no application table and `alembic_version` = `0011`. |
| M1 | `upgrade head` applied every revision from `0001` through `0012`; `current` = `0012 (head)`; one head; 28 application tables plus `alembic_version`; the three interview tables match `0012` in every item of M1.6; no data. |
| Round trip | `downgrade 0011` removed only the three interview tables (the other 25 identical to head); `upgrade head` restored them with the same schema. |
| Comparison with the models | At `0011` (`compare_metadata`): the three interview tables and six indexes as additions, plus the `uq_job_criteria_job_name` pair. At head (`alembic check` twice, and `compare_metadata`): only that pair. |
| Accepted difference | `uq_job_criteria_job_name` on `job_criteria`: PostgreSQL stores `lower(TRIM(BOTH FROM name))`; the model and migration `0002` write `lower(trim(name))`. A cosmetic false positive, unrelated to the interview objects, accepted by Long on 21/11/2026. Open question: Q42. |
| End state | `0012 (head)`, `alembic_version` = `0012`, no data, no seed. |

The record is D70. Passing the migration QA said nothing about the PostgreSQL-gated tests; they ran afterwards and are recorded in §4A.5 and D77.

### 4A.5 PostgreSQL Test Tiers — passed (S1 to S5, 21 and 22/11/2026); schema restored and `alembic check` passed (22/11/2026); close-out done

**Status (22/11/2026): passed.** Every step passed after the remediation; the restore (R) ran under go-3 and ended with `alembic check` at exit code 0; the close-out is done, CO4 included (after Long's OK). The outcome record is D77, the Q42 record is D76. The sections below keep the plan as approved, the first failed runs and the remediation as they were written, with the boxes ticked for what was done. The results are in "Results of the PostgreSQL runs after the remediation" and "Restore, `alembic check` and close-out (go-3, 22/11/2026)".

**Update 21/11/2026: Long approved this plan and gave go-1; S1 and S3 ran and failed, S2 and S4 did not run (see "Go-1 outcome and remediation plan" at the end of this section); the runs after the remediation, and their results, are under "Results of the PostgreSQL runs after the remediation". The rest of the section is the plan as approved. Nothing destructive runs without a separate, explicit approval (A4 below).** Same database and same scope as §4A.4: `careersync_db` in `careersync-db-1`, all data disposable (D71). Every number below was measured read-only on 21/11/2026, with the database variables removed from the command: test collection, and one SQLite run in which every PostgreSQL-gated test skips. No PostgreSQL connection was made.

#### What a PostgreSQL run does to the database

The `db` fixture (`backend/tests/conftest.py`) checks the identity, then runs `drop_all` and `create_all` of the 28 model tables before every test, and `drop_all` after it. It never touches `alembic_version`. So: (1) each step wipes whatever the step before left; (2) after the last pytest step the database has no application table and `alembic_version` still reads `0012`, so the schema must be restored (R below); (3) the pytest steps need no Alembic and no `DATABASE_URL`; (4) a PostgreSQL-gated test that never ran cannot be assumed to pass: eight of these files say in their docstrings that they were written without a PostgreSQL to run against, so the first run may fail on a wrong assumption in a test as well as on a defect (see "Triage").

#### Measured inventory (collection and a SQLite run; numbers as of 21/11/2026)

**Tier A, the original 57:** the 12 tracked files that hold the PostgreSQL-gated tests that existed before the Stage 1 additions. The gated count per file adds up to exactly 57 (the SQLite skip count recorded in §4.2).

| File | Collected | PostgreSQL-gated | Also run on SQLite |
|---|---:|---:|---:|
| `backend/tests/test_career_api.py` | 15 | 2 | 13 |
| `backend/tests/test_company_projects_api.py` | 14 | 1 | 13 |
| `backend/tests/test_cv_review_api.py` | 10 | 2 | 8 |
| `backend/tests/test_evaluation_queue.py` | 13 | 5 | 8 |
| `backend/tests/test_interview_create_concurrency.py` | 3 | 3 | 0 |
| `backend/tests/test_interview_feedback_concurrency.py` | 12 | 12 | 0 |
| `backend/tests/test_interview_ingest_concurrency.py` | 9 | 9 | 0 |
| `backend/tests/test_interview_nul_postgres.py` | 9 | 9 | 0 |
| `backend/tests/test_interview_quota.py` | 48 | 9 | 39 |
| `backend/tests/test_offer_api.py` | 16 | 3 | 13 |
| `backend/tests/test_recommendations_api.py` | 34 | 1 | 33 |
| `backend/tests/test_talent_api.py` | 11 | 1 | 10 |
| **Total** | **194** | **57** | **137** |

Running the explicit file list runs all 194 of its tests, not only the 57: the other 137 also run on PostgreSQL for the first time. The 57 are the point; a failure among the 137 is a PostgreSQL-versus-SQLite finding and is triaged like any other.

**The Stage 1 files (N1 to N9 and the diagnostics):** six files, not yet committed, 83 gated tests: the 80 of N1 to N9 and the 3 raw JSONB diagnostics.

| File | Covers | Collected (all gated) |
|---|---|---:|
| `backend/tests/test_interview_cascade_postgres.py` | N3: foreign keys, cascades, partial unique index, checks | 17 |
| `backend/tests/test_interview_ingest_more_postgres.py` | N7 and N8 (ingestion): order and deadline under parallel requests | 11 |
| `backend/tests/test_interview_jsonb_postgres.py` | N4 (JSONB, surrogates), N5 (NUL), the 3 diagnostics | 34 |
| `backend/tests/test_interview_migration_postgres.py` | N1 and N2: `0012` up, down, up; the catalog | 12 |
| `backend/tests/test_interview_planner_race_postgres.py` | N6: a planner that outlived its lease | 2 |
| `backend/tests/test_interview_retention_postgres.py` | N8 (purge) and N9: retention under parallel requests | 7 |

**Other sets used by the steps**

| Set | Command scope | Collected | PostgreSQL-gated |
|---|---|---:|---:|
| Race set (8 files that run real threads and connections) | `test_evaluation_queue`, `test_interview_create_concurrency`, `test_interview_feedback_concurrency`, `test_interview_ingest_concurrency`, `test_interview_quota`, `test_interview_ingest_more_postgres`, `test_interview_planner_race_postgres`, `test_interview_retention_postgres` | 105 | 58 |
| JSONB surrogate step | `test_interview_jsonb_postgres.py` with `-k "surrogate or astral or basic_plane"` | 16 | 16 |
| Tier B | the 39 files matched by `backend/tests/test_interview_*.py` | 1430 | 125 |
| Tier C | `pytest` from the repo root (`ai/tests` and `backend/tests`) | 3597 | 140 |

The 140 gated tests of the whole suite are all in the 19 files above (12 of Tier A, 6 Stage 1 files, and none elsewhere): no other test skips. **Expected result of every step on PostgreSQL: every collected test passes, none skipped, none failed.** Numbers are re-collected at P6 before each step; any difference from this table is explained before the step runs.

#### Approvals needed from Long

- **A1** Approve this plan, including the close-out (CO) and the Q42 change drafted below.
- **A2** Approve the `backend/migrations/env.py` change for Q42 (CLAUDE.md: ask before changing `backend/migrations/`). It is applied at R2, not before.
- **A3** Tier C: yes or no. Recommendation: **yes** (see "Tier C recommendation").
- **A4** The explicit go for the destructive steps, in three parts: **go-1** covers S1 to S4 in order and continues only while every step is exactly as expected; **go-2** covers S5 (Tier C), if A3 is yes; **go-3** covers R (the restore). Each is a separate message, as M0 and M1 were.
- **A5** Two technical docs are outdated and CLAUDE.md says not to edit such a doc without Long's OK: `PROJECT_DOCUMENTATION.md` §9 (the `TEST_DATABASE_URL` row describes only the `_pgtest` mode) and `docs/how-to/run-locally.md` (the PostgreSQL paragraph). See CO2.

#### Environment and the `env` block

Which variables each step needs, and what Long changes in `.claude/settings.local.json` (its contents are never opened, printed or recorded; I check presence and equality only, as in M1):

| State | When | In the block | Not in the block |
|---|---|---|---|
| Now | | the five required variables and `DATABASE_URL` (left from M1) | the nine `PG*` names |
| B | before S0, through S5 (every pytest step) | `TEST_DATABASE_URL`, `TEST_DATABASE_EXPECTED_NAME`, `TEST_DATABASE_CONFIRM_DESTRUCTIVE`, `CAREERSYNC_DOTENV` = `0`, `AI_MODE` = `rules` | `DATABASE_URL` and the nine `PG*` names |
| C | R1 to R9 (Alembic) | state B plus `DATABASE_URL` equal to `TEST_DATABASE_URL` | the nine `PG*` names |
| D | after R9 | no `env` block | |

**What Long changes:** (1) before S0, remove `DATABASE_URL` from the block; (2) before R3, add `DATABASE_URL` equal to `TEST_DATABASE_URL`; (3) after R9, remove the whole block. After each change Long says so and I confirm the new state with presence and equality checks before running anything (a changed block applies to the commands after it, as in M1).

**Does the guard or the plan require `DATABASE_URL` absent for pytest?** The guard does not. `backend/tests/db_safety.py` reads `DATABASE_URL` only under `--app`, where it must equal `TEST_DATABASE_URL`; for pytest, the `db` fixture reads `TEST_DATABASE_URL` only. Nothing in pytest opens a connection through `DATABASE_URL`: the app's own engine (`backend/app/db/session.py`) is built lazily from it, its only user is `get_db`, which the API tests override, and the retention tests deliberately avoid `SessionLocal`. The plan does require it: the environment table of §4A.4 says absent for pytest and present only for Alembic and the purge script. This plan keeps that rule: one variable per role (pytest reads `TEST_DATABASE_URL`, guarded; Alembic reads `DATABASE_URL`, guarded by `--app`), and P1 can assert "absent". Leaving it set would not break pytest, but it would be a deviation from the approved procedure. Not recommended: removing it inside each command instead of in the block, because P1 could then no longer show it absent from the block.

#### Conventions for every command

- The interpreter is `d:\dev\project\CareerSync\.venv\Scripts\python.exe` (`$py` below); every command runs from the repo root, except Alembic, which runs from `backend/` (R4 onward).
- Flags for every pytest step: `-q -rfEs --tb=short -p no:cacheprovider`. No `-x` (a step reports all its failures), no reruns and no `--lf` (never run again to get green). The JSONB step uses `--tb=long`.
- One pytest process at a time, never in parallel: the fixture wipes the one shared database. No xdist is installed; none may be installed for this work.
- Never print a URL, a password or an approval value. Test data is synthetic; a failure's traceback is read before it is quoted anywhere.
- Steps S4 and S5 run in the background and are watched; the other steps run in the foreground.

#### Preflight (P1 to P7; no database change)

Before S1 all seven; before each later step, P3, P5 and that step's P6.

- [x] **P1** The environment is in state B: the five required variables set with the fixed values of §4A.4 (URL shape: host `127.0.0.1`, port `5434`, database `careersync_db`, only allowed query keys), `DATABASE_URL` absent, the nine `PG*` names absent. Booleans only.
- [x] **P2** `python backend/tests/db_safety.py --no-connect` exits `0`.
- [x] **P3** `python backend/tests/db_safety.py` (identity, read-only) exits `0`.
- [x] **P4** `docker ps`: only `careersync-db-1` is running, and it is healthy. If it is stopped, start that same container (`docker start careersync-db-1`), never recreate it, never use `docker compose` (D71).
- [x] **P5** No other client session on `careersync_db` (a count only).
- [x] **P6** `--collect-only -q` of the step's exact file list collects exactly the number in the inventory (194, 105, 16, 1430, 3597). Collection opens no database connection.
- [x] **P7** Read-only start state: `alembic_version` = `0012`, 28 application tables, no data (the M1 end state), and a baseline of `pg_stat_database` for `careersync_db` (`xact_commit`, `xact_rollback`, `tup_inserted`, `tup_deleted`; four numbers).

*Done: P1 to P7 before the first step of each series and P3, P5, that step's P6 and a counter baseline before each later step (the counts of P6 changed with the added tests; see the results). P7 as run recorded the start state as "no application table" by Long's decision that the restore comes at the end.*

#### How "executed, not skipped" is proved

A PostgreSQL-gated test skips when `TEST_DATABASE_URL` does not start with `postgresql`, so without the database it can only skip. A step is proved only when all of these hold:

1. The summary line has no `skipped` and no `failed` or `error`, and the `-rs` section is empty.
2. The `passed` count equals the P6 collection count for that step (the table above).
3. For S1 and S2 the gated tests are inside those counts, so 57 and 58 of them passed; the other tests in the same files passing on PostgreSQL is an additional result.
4. After the step, `pg_stat_database` for `careersync_db` moved: `xact_commit` and `tup_inserted` are higher than at P7 (read-only, printed as numbers). This is independent of pytest's own output.

A step that passes on SQLite alone proves nothing (M0 caveat); points 1 and 2 make that impossible here, because the gated tests would be counted as skipped.

#### Steps

All commands below use `$py = 'd:\dev\project\CareerSync\.venv\Scripts\python.exe'`.

**S1 — Tier A (go-1).** Expected: `194 passed`, nothing else. The duration of S1 is the measurement used to project S4 and S5; it is recorded.

```powershell
$tierA = @(
  'backend/tests/test_career_api.py',
  'backend/tests/test_company_projects_api.py',
  'backend/tests/test_cv_review_api.py',
  'backend/tests/test_evaluation_queue.py',
  'backend/tests/test_interview_create_concurrency.py',
  'backend/tests/test_interview_feedback_concurrency.py',
  'backend/tests/test_interview_ingest_concurrency.py',
  'backend/tests/test_interview_nul_postgres.py',
  'backend/tests/test_interview_quota.py',
  'backend/tests/test_offer_api.py',
  'backend/tests/test_recommendations_api.py',
  'backend/tests/test_talent_api.py'
)
& $py -m pytest @tierA -q -rfEs --tb=short -p no:cacheprovider
```

**S2 — the concurrency and race repeats (go-1).** Five consecutive runs of the race set. Run 1 is also the first execution of the three Stage 1 race files (`ingest_more`, `planner_race`, `retention`); the other five files already ran once in S1. Expected: `105 passed` in every run. The loop stops at the first run that is not clean. Five runs raise confidence and do not prove the absence of a race.

```powershell
$race = @(
  'backend/tests/test_evaluation_queue.py',
  'backend/tests/test_interview_create_concurrency.py',
  'backend/tests/test_interview_feedback_concurrency.py',
  'backend/tests/test_interview_ingest_concurrency.py',
  'backend/tests/test_interview_quota.py',
  'backend/tests/test_interview_ingest_more_postgres.py',
  'backend/tests/test_interview_planner_race_postgres.py',
  'backend/tests/test_interview_retention_postgres.py'
)
for ($i = 1; $i -le 5; $i++) {
  "--- race set, run $i of 5"
  & $py -m pytest @race -q -rfEs --tb=short -p no:cacheprovider
  if ($LASTEXITCODE -ne 0) { break }
}
```

**S3 — JSONB surrogate diagnostics (go-1), run before Tier B on purpose:** they are the one place where a failure is plausible and changes what happens next, and they are cheap. Tier B contains the same tests again. Expected: `16 passed`.

```powershell
& $py -m pytest backend/tests/test_interview_jsonb_postgres.py -q -rfEs --tb=long -p no:cacheprovider -k "surrogate or astral or basic_plane"
```

What each result means:

| Tests | Pass means | Fail means |
|---|---|---|
| `test_postgres_jsonb_cannot_hold_a_serialized_lone_surrogate` (2: lone high, lone low) | `jsonb` refuses a serialized lone surrogate: the hazard is real | `jsonb` accepts it: nothing is at risk there, and the test's assumption was wrong (a T1 finding) |
| `test_postgres_jsonb_keeps_an_astral_character_that_is_serialized_as_a_pair_of_escapes` (1) | an astral character survives as a pair of escapes | a valid character is damaged: a defect |
| `test_postgres_a_surrogate_in_a_model_feedback_ends_as_a_report_and_never_a_raw_error` (3) | the feedback service survives a surrogate in model text on PostgreSQL | a raw database error escapes the Feedback service: the follow-up risk is real |
| the 9 ingestion tests (candidate answer, interviewer line, closing line) and the basic-plane round trip (1) | the refusal and the round trip hold on PostgreSQL | a defect in the S3a refusal or in storage |

There is no Plan-service test with a surrogate; the raw `plan` update of the first row is the only Plan coverage. If the first row passes, the Plan path has the same hazard and no service-level test: that gap belongs in the remediation plan.

**S4 — Tier B (go-1).** Expected: `1430 passed`. Background run; the file list is built from the glob at run time and P6 must return 1430 first.

```powershell
$tierB = Get-ChildItem backend/tests -Filter 'test_interview_*.py' | Sort-Object Name | ForEach-Object { "backend/tests/$($_.Name)" }
& $py -m pytest @tierB -q -rfEs --tb=short -p no:cacheprovider
```

**S5 — Tier C (go-2, only if A3 is yes).** Expected: `3597 passed`. Background run; before it, if the S1 rate projects more than 90 minutes, ask Long first.

```powershell
& $py -m pytest -q -rfEs --tb=short -p no:cacheprovider
```

Duration is not measured. Each test costs a `drop_all`, a `create_all` and a `drop_all` of 28 tables. The SQLite runs took about 2 minutes (Tier B) and 4 minutes (whole suite); PostgreSQL will be slower by an amount only S1 shows.

#### Stop conditions

Stop means: run nothing further in the sequence, change no code, report counts and node IDs, and wait for Long.

1. Any of P1 to P7 differs from what is written (state B wrong, a refusal from the guard, a second container, another session, a collection count that differs, a start state that is not head and empty). Never bypass or edit `backend/tests/db_safety.py`.
2. A step's result is not exactly as expected: any failed, error or skipped test, or a passed count different from the collection count. Never run it again to get green. In S2, stop at the first run that is not clean and record how many of the five were clean.
3. **Any test of S3 fails: stop, do not run S4 or S5, and write a separate remediation plan** (its own section, its own approval). Edit no Feedback, Plan or ingestion code: the decision of D66 and the note of §4A.2 say the boundaries are not changed before these diagnostics decide whether the failure is real.
4. No output for 10 minutes in S1 to S4, or 20 minutes in S5: report. Only the pytest process may be stopped, and only after Long agrees; no database session is ever terminated.
5. Any message of the safety guard refusing, or an identity answer that is not `careersync_db`.

After a stop, the database may have no application table. Whether to restore at once or after a fix is Long's decision; the restore (R) is the same either way.

#### Triage of a failure (the tests were written without a database to run on)

| Class | Meaning | Next |
|---|---|---|
| T1 | A test assumed something about PostgreSQL that is not true | Test-only fix, own plan |
| T2 | A defect in application code or in a migration | Own plan; CLAUDE.md "Never" items need explicit confirmation |
| T3 | Interference between tests (leftover state, order) | Own plan |
| T4 | A race that failed in some of the five runs | Record the node ID and how many of five failed; a finding about the code or the test, never retried until green |
| T5 | Environment: container, connection, timeout | Fix the environment, rerun the step only with Long's go |

Every failure, its class and its node ID go into the tier-outcome record (CO3).

#### R — restore (go-3)

R0 first: after the last pytest step, a read-only post-check as M0.2: no application table, and `alembic_version` still present (`0012`, stale). If an application table remains (a killed run or a failed setup), do not run Alembic: run the M0 smoke test once more with Long's approval, because its teardown drops every table, and check again.

- [x] **R1** Long adds `DATABASE_URL` (equal to `TEST_DATABASE_URL`) to the block: state C. I confirm equality by comparison, no printing. *(Done 22/11/2026.)*
- [x] **R2** Apply the Q42 change to `backend/migrations/env.py` (draft below; only after A2). Every Alembic command from here uses the final file. *(Done, but after R5, in the order of Long's go-3 message: the filter does not run during `upgrade`, so R4 and R5 did not need it; `alembic check`, `current` and `heads` ran on the final file.)*
- [x] **R3** `python backend/tests/db_safety.py --app` exits `0`. Then change into `backend/`. *(Done, before R4.)*
- [x] **R4** `python -m alembic stamp --purge base`, then `python -m alembic current` shows no revision. *(Done.)*
- [x] **R5** `python -m alembic upgrade head` applies every revision from `0001` through `0012`; `alembic current` shows `0012 (head)`; `alembic heads` shows that one head. *(Done.)*
- [x] **R6** Read-only schema verification, the M1.6 list: 28 application tables plus `alembic_version` = `0012`; the three interview tables item by item; no data. *(Done: every item matched.)*
- [x] **R7** `python -m alembic check`. **Expected: exit code `0`** and "No new upgrade operations detected", because the Q42 filter removes the only difference found in M1.7 and M1.9. Record the full output. Any other difference stops the work and is reported as unclassified; do not mark the QA passed. *(Done: exit code `0`, "No new upgrade operations detected".)*
- [x] **R8** Negative control, read-only: the `compare_metadata` run of 21/11/2026, which does not use `env.py`, still reports exactly the `uq_job_criteria_job_name` pair and nothing else. That shows the filter, and only the filter, removed it. *(Done: exactly that pair, `remove_index` and `add_index` on `job_criteria`.)*
- [x] **R9** End state: head, `alembic_version` = `0012`, no data, no seed. Long removes the whole `env` block (state D). *(End state verified; the removal of the block is Long's, after the report.)*

If A2 is declined, R2 and R8 are skipped, and R7 is expected to show the known pair and exit non-zero, as accepted in D70; Q42 then stays open.

#### Q42 change, applied as drafted on 22/11/2026 (`backend/migrations/env.py`; D76)

Long's decision of 21/11/2026: filter `uq_job_criteria_job_name` out of the autogenerate comparison, explicit and narrow. The model expression stays `lower(trim(name))`: PostgreSQL normalizes it to `lower(TRIM(BOTH FROM name))` and Alembic compares the expression text, while SQLite cannot parse the `TRIM(BOTH FROM ...)` form, so the SQLite-run tests need the model as it is. `include_object` is used only by autogenerate and `alembic check`; it does not run during `upgrade` or `downgrade`, so no migration and no Compose `init` behaves differently. The only configure call of the online path gets the new argument:

```python
target_metadata = Base.metadata

# Q42, D70: PostgreSQL stores `lower(trim(name))` as `lower(TRIM(BOTH FROM name))` and Alembic compares the expression text, so
# `alembic check` reports this index as removed and added again although nothing differs. The model keeps `lower(trim(name))`
# because SQLite cannot parse `TRIM(BOTH FROM ...)`. Narrow on purpose: this one index name.
# shortcut: a real change to this index is also hidden from autogenerate, so review a change to it by hand.
IGNORED_INDEXES = frozenset({"uq_job_criteria_job_name"})


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "index" and name in IGNORED_INDEXES)

...
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
```

No automated test can import `env.py` (it runs Alembic when it is imported), so the proof is R5 (the file loads and upgrades), R7 (exit `0`) and R8 (only that pair was removed). A typo would fail at R3 to R5, before anything is claimed.

#### Tier C recommendation

**Yes, run Tier C (S5), after S1 to S4 are clean.**

- The whole suite has never run on PostgreSQL. CI runs `pytest -q` with no database, and every local run so far used SQLite, so the passing tests say nothing about the dialect the product runs on, apart from the 140 gated ones.
- Tiers A and B reach 57 plus 83 gated tests and the files around them. About 50 other test files use the database fixtures (an approximate count): JSON columns, ordering, case sensitivity, timestamps and constraint errors are untested on PostgreSQL there.
- No new risk: D71 already makes the database disposable, the fixture does in S5 what it does in S1 to S4, and R is the same restore.
- The cost is one more unattended run. The duration is unmeasured; S1 gives the rate, and over 90 minutes I ask first.
- Conditions: S1 to S4 clean; its own go (go-2); a failure in S5 is a finding in the classes above, not a reason to change code during the QA, and a failure outside the interview area is recorded and left for its own plan.
- Against it: time, and noise from tests written with SQLite behavior in mind. Finding those is the purpose.

#### Close-out after the run (CO; documentation and a local run, no database)

- [x] **CO1** *(Done 22/11/2026: the steps are ticked and the results are in "Results of the PostgreSQL runs after the remediation" and "Restore, `alembic check` and close-out".)* This section: tick the steps and record the real results per step: exact counts, skipped tests and why, durations, the `pg_stat_database` movement.
- [x] **CO2** *(Done 22/11/2026 under the A5 approval: the `TEST_DATABASE_URL` row and a new "PostgreSQL test database" paragraph in `PROJECT_DOCUMENTATION.md` §9, and the PostgreSQL paragraph of `docs/how-to/run-locally.md` §9. Two other mentions in `PROJECT_DOCUMENTATION.md` still say "disposable" (the Database row of §1 and a sentence of §3.7) and were left as they are: they are not wrong, and they were outside the approved edit.)* The PostgreSQL QA runbook (A5): `PROJECT_DOCUMENTATION.md` §9, `TEST_DATABASE_URL` row: it describes only the `_pgtest` mode; the approved mode, `TEST_DATABASE_EXPECTED_NAME`, `TEST_DATABASE_CONFIRM_DESTRUCTIVE` and the `db_safety.py` command are not documented there. `docs/how-to/run-locally.md`, the PostgreSQL paragraph: the same gap. Fold into them what the run proved (interpreter, the `env` block, preflight, restore). Only after Long's OK.
- [x] **CO3** *(Done 22/11/2026: D76 and D77 written, with the numbers reserved here; the Q42 row removed from §3.3. D76 carries its decision date, 2026-11-21, as the file's rule asks.)* `docs/DECISIONS.md`: two records, with the next free numbers at the time (D76 and D77 today; D73, D74 and D75 were taken on 21/11/2026 and 22/11/2026 by the surrogate rule, the CV-upload rule and the quota retry). D76: the Q42 decision and its implementation; remove the Q42 row from §3.3. D77: the tier outcome: results per step, every failure with its class, the JSONB diagnostics outcome, the Tier C decision and result, the restore and the `alembic check` result, the end state, and what is not covered.
- [x] **CO4** *(Done 22/11/2026 after Long's approval: in each of the eight files the sentence that said the tests were written, not run, now says they ran and passed on PostgreSQL on 2026-11-22 (D77); `test_interview_nul_postgres.py` also says that PostgreSQL does behave as its first two tests assume. Only those docstring sentences changed. Run afterwards on SQLite with the database variables removed from the command: the eight files collect 95 tests and all 95 skip (every test in them is PostgreSQL-gated), none failed; `backend/tests/docs` 44 passed. The skips prove nothing about PostgreSQL: the claim in the docstrings rests on the Tier B and Tier C runs of D77.)* The eight test files whose docstrings say they were written without a PostgreSQL (`test_interview_jsonb_postgres`, `test_interview_retention_postgres`, `test_interview_planner_race_postgres`, `test_interview_ingest_more_postgres`, `test_interview_cascade_postgres`, `test_interview_migration_postgres`, `test_interview_nul_postgres`, `test_interview_create_concurrency`): update that sentence to the verified result. A test-only edit; needs Long's OK.
- [x] **CO5** *(Done 22/11/2026: §1 progress lines, §4.2, §4A.1, §4A.2, the §4A.4 note, §9.1, §10, Current Blocking Issue, Next Priority, Open Items and the log. Production readiness is not claimed anywhere.)* M4 status in this tracker, keeping the four states apart (implemented, locally verified, verified on PostgreSQL, production-ready): §1 Overall Progress (the M4, safety hardening, surrogate hardening and test-tier lines), §4.2 (JSONB, row-lock and concurrency items), the "not run against PostgreSQL" notes of §4A.1 and §4A.2, the §10 table (M4, PostgreSQL safety hardening, PostgreSQL QA), Current Blocking Issue, Next Priority, Open Items (Q42, D76, D77, and the Feedback and Plan surrogate row, which D73 now covers) and a log row.
- [x] **CO6** *(Done 22/11/2026: 3525 passed, 140 skipped, 0 failed, exit code 0, 264.96 s; 3665 collected; the database variables were removed from the command.)* A full local run: `pytest` from the repo root with `CAREERSYNC_DOTENV=0` and `AI_MODE=rules` and the database variables removed from the command (SQLite; the 140 gated tests skip). Record the exact result.
- [x] **CO7** *(Done 22/11/2026: each row of the block was run from its own command; the PostgreSQL results are separate rows; the "no PostgreSQL connection" sentence now says it applies to the local rows.)* Refresh "Latest Local Verification" in §1 with the date and these results, each row from its own command so the numbers reproduce: full suite (`pytest` from the repo root); dedicated surrogate tests (`backend/tests/test_interview_surrogate.py`); test database safety guards (`backend/tests/test_db_safety.py`); architecture tests (the four files `ai/tests/test_interview_backend_boundary.py`, `test_interview_cv_boundary.py`, `test_interview_model_boundary.py` and `test_interview_transcript_boundary.py`, which sum to the 340 of the last block); documentation tests (`backend/tests/docs`, 44 today). Add the PostgreSQL step results as their own rows or block, never merged into the local suite, and reword the sentence that says no PostgreSQL connection was made so that it applies to the local rows only.
- [x] **CO8** *(Done 22/11/2026: 44 passed before, as last recorded, and 44 passed after the edits.)* Run `backend/tests/docs` and report before and after counts.
- [x] **CO9** *(Done 22/11/2026: reported to Long; nothing was staged or committed.)* A read-only `git status`, for Long, who commits.

#### Checklist (the items of the earlier list, now mapped to the steps)

- [x] **Tier A:** the original 57 PostgreSQL-gated tests, by the explicit 12-file list *(S1; passed on the second series, 194 collected then)*
- [x] Repeat the concurrency and race tests *(S2; five of five runs clean, before D75)*
- [x] **Tier B:** all `backend/tests/test_interview_*.py` tests, including N1 to N9 *(S4; passed on the second run, 1488 collected)*
- [x] Confirm the PostgreSQL-gated tests execute rather than skip *(counts and `pg_stat_database` in S1 to S5)*
- [x] Verify the PostgreSQL JSONB surrogate diagnostics *(S3; two failed on 21/11/2026 and led to D73, then passed)*
- [x] If the Feedback or Plan JSONB surrogate diagnostics fail, stop and create a separate remediation plan *(done: stopped, planned, D73 and D74)*
- [x] **Tier C:** the optional full suite against PostgreSQL *(S5; approved, 3665 passed, none skipped)*
- [x] Restore the schema with `alembic stamp --purge base` followed by `alembic upgrade head`, then `alembic check` at head *(R; 22/11/2026, `alembic check` exit code 0)*
- [x] Do not seed data by default *(no seed was run)*
- [x] Add D70 *(done 21/11/2026: it records the migration QA outcome only; the test tiers are not covered)*
- [x] Update the PostgreSQL QA runbook, add the tier-outcome record and the Q42 record, refresh the status and the verification block *(CO; D76, D77; CO4 done 22/11/2026)*

#### Go-1 outcome and remediation plan (21/11/2026; no code, test or document other than this section has changed)

Long approved the plan (A1 to A5) and gave go-1. S1 and S3 ran. S2 and S4 did not run, S5 (Tier C) and the restore (R) have not run. Nothing was fixed. By Long's decision the restore happens only at the end, after the remediation and the remaining steps. The database has no application table and `alembic_version` reads `0012` (stale). The `env` block is in state B (`DATABASE_URL` absent).

**Results**

| Step | Result | Time |
|---|---|---:|
| S1 preflight P1 to P7 | Passed; 194 collected | |
| S1 Tier A | **3 failed, 191 passed**, 0 skipped; 54 of the 57 gated tests passed. Stop condition 2. | 163.6 s |
| S2 | Not run | |
| S3 preflight P1, P3 to P6 | Passed; 16 collected | |
| S3 JSONB diagnostics | **2 failed, 14 passed**, 0 skipped. Stop condition 3. | 16.0 s |
| S4 | Not run | |

- Executed, not skipped: neither summary line shows a skip, and `pg_stat_database` (`xact_commit` / `tup_inserted`) moved from 1986 / 7597 before S1 to 5307 / 411606 after it, and from 5362 / 411607 before S3 to 5598 / 450195 after it.
- S1 ran as a background job, not in the foreground: a foreground command stops at 10 minutes, and a killed pytest would have forced a rerun. The rate was about 0.84 s per test, which projects Tier B at about 20 minutes and Tier C at about 50 (a projection, not a measurement; both are below the 90-minute question threshold).

**Failures and classes**

| # | Node ID (`backend/tests/` prefix omitted) | What happened | Class |
|---|---|---|---|
| 1 | `test_interview_feedback_concurrency.py::test_pg_in_rules_mode_parallel_requests_store_one_report_and_all_return_it` | `len({repr(data)}) == 1` gave 2 | T1 |
| 2 | `test_interview_feedback_concurrency.py::test_pg_a_session_whose_third_attempt_died_is_recovered_once_by_parallel_requests_without_a_model` | the same assertion | T1 |
| 3 | `test_interview_nul_postgres.py::test_pg_a_cv_with_nul_is_refused_before_the_model_and_nothing_is_stored` | `psycopg.DataError` in the setup: `build_world` inserts a CV with a NUL, before any code under test runs | T1 |
| 4 | `test_interview_jsonb_postgres.py::test_postgres_a_surrogate_in_a_model_feedback_ends_as_a_report_and_never_a_raw_error[a high surrogate]` | a raw `DataError` ("Unicode low surrogate must follow a high surrogate") reached the caller of `fb.ensure` | T2 |
| 5 | the same test, `[a low surrogate after text]` | the same | T2 |

The third case of that test (`a high and a low code point side by side`) passed.

**R-a. The two feedback concurrency tests (failures 1 and 2): test-only**

Cause, from the log and the code: the request that stores the report returns `report.to_data()` (insertion order), the others return the stored value read back (`_stored_result`), and `jsonb` orders object keys by length and then by bytes. The pytest output shows both: one dict starts with `gaps`, which can only be `jsonb` order (`to_data()` starts with `method`), and one ends `uncovered, notes, rules_sections, rubric_notice`, which can only be insertion order (`jsonb` puts `notes` first).

Read-only check, does anything depend on the key order of the feedback result? **No.**

- The route returns the report through `FeedbackReportOut` (`backend/app/schemas/interview.py`), so the key order of the HTTP response is the schema's field order, whatever the service dict looks like.
- There is no ETag, no hash and no cache of the feedback: every interview path carries `Cache-Control: no-store` (D67). The only canonical digest is `plan_digest` (sorted keys), which does not depend on order.
- No frontend code reads the feedback: in `frontend/src` the word appears only in CSS files.
- No snapshot or golden-file test exists. The only `repr(` comparisons of report data in `backend/tests` are the two failing lines. Lists keep their order in `jsonb`; only object keys are reordered.

Change: in `test_interview_feedback_concurrency.py`, replace the two `len({repr(r[1].data) for r in results}) == 1` lines with `assert all(r[1].data == results[0][1].data for r in results)`. Dict equality ignores key order and still compares every value and every list order. Canonical JSON with sorted keys would say the same in more code. The next line of the first test (`r.feedback == results[0][1].data`) already compares by equality.

Should the service return the read-back stored value on every path? **Recommendation: no.**

- For: after the store, a re-read makes "what you got is what is stored" true and removes the one real divergence besides key order, a model that writes a high and a low surrogate as two separate code points (stored as one emoji, returned as two code points to the request that stored it). After R-d rejects any surrogate, that case is gone.
- Against: one more query on the path of every generated report; a change inside a service whose boundaries D66 and §4A.2 say to leave alone until the diagnostics decide; and it can never be uniform, because provisional results (`quota`, `model_failed`, `plan_invalid`, `lease_lost`) are not stored and always carry the in-memory order.
- Nothing depends on the order, so the cost has no buyer.

**R-b. The NUL test (failure 3): test-only**

Cause: PostgreSQL refuses a NUL in a text column, so no stored CV can hold the state the test describes. The guard under test (`build_canonical_plan` → `has_nul(clean.text)` → `PlanRefused("nul_cv")`) is reachable only when the CV text comes from somewhere other than the table.

Proposed setup, same name and same assertions: use the default `world` fixture (a clean CV) and patch the one place the stored CV text is read, `interview_service._read_stored_cv` (its docstring: "the one place the stored masked CV text is read"): `monkeypatch.setattr(svc, "_read_stored_cv", lambda _db, _cv_id: SAMPLE_CV.replace("Spring Boot", f"Spring{NUL}Boot", 1))`. Keep today's assertions: 422 `INTERVIEW_NOT_AVAILABLE`, the session `aborted` with `plan_unavailable` and no plan, and `llm.calls == []`. Add one: no plan and no turn row exists for the session. A stored NUL would raise a `DataError`, so reaching the assertions already shows that no write of it was attempted.

What it proves: the refusal completes on PostgreSQL, before the model, with no database error. What it does not prove: that a real CV can reach the guard (R-c). The SQLite test `test_interview_nul.py` keeps testing the same guard with a really stored NUL.

**R-c. Can `cv_service.upload` receive a NUL? (read-only investigation)**

Path traced: `backend/app/api/v1/cv.py` `upload_cv` → `cv_service.upload(db, user, file.filename or "cv.pdf", data)` → `ai/parsing/pdf.py` `extract_text` (PyMuPDF `get_text("text", sort=True)`, then `rstrip` per line and `strip`) → `mask_pii` → `structure_cv` → `CvDocument(file_name=file_name[:255], masked_text=masked.text, ...)` → `db.commit()`. No step looks for U+0000, and `rstrip`, `strip` and `splitlines` do not remove it.

1. **`file_name`: a real path.** A raw NUL byte in the multipart `filename` reaches `UploadFile.filename` unchanged (probe with a throwaway FastAPI app: status 200, length 7 for `cv`, NUL, `.pdf`), and the service stores it unchecked in `cv_documents.file_name`. PostgreSQL refuses a NUL in text (failure 3 shows that `DataError` for the `cv_documents` INSERT). So a seeker with the AI consent who uploads a text PDF under such a filename should get an unhandled `DataError` (an HTTP 500) and no CV. Not run end to end on PostgreSQL.
2. **Extracted text: unprotected, not reproduced.** Two synthetic PDFs (PyMuPDF `insert_text` with a NUL and with control characters; a hand-written PDF whose font maps a glyph name to `/uni0000`): extraction never returned U+0000, and the second came back as the base character. That is not proof that no PDF can. No real CV was used.

If Long wants it fixed, it is product code with its own plan and approval (CLAUDE.md: it changes `cv_service`; a new 422 on an existing endpoint would also touch an API contract, which needs explicit confirmation). Options: for `file_name`, drop U+0000 (no contract change; recommended) or refuse with a 422; for the text, drop U+0000 in `extract_text` before the length check (one place) or refuse with the existing `CV_UNREADABLE`.

Tests that would cover it: a new test file for the CV upload (its name is chosen in the fix plan) with (1) an upload through the API with a synthetic in-memory PDF and a filename that holds a NUL, expecting the chosen behaviour and no 500; it runs on SQLite, where today the NUL is stored silently, so it is red before the fix; (2) a PostgreSQL-gated twin, red today with the `DataError`; (3) `extract_text` patched to return NUL text into `cv_service.upload`, as the same pair. New files change the Tier B and Tier C counts, which are re-collected at P6.

**R-d. The S3 failures (4 and 5) and the surrogate hazard**

What S3 established:

| Diagnostic | Result | Meaning |
|---|---|---|
| `test_postgres_jsonb_cannot_hold_a_serialized_lone_surrogate` (2) | passed | `jsonb` refuses a serialized lone surrogate: the hazard is real |
| the astral-character test (1), the basic-plane round trip (1) | passed | a valid character is kept |
| the 9 ingestion tests (candidate answer, interviewer line, closing line) | passed | the refusal of §4A.2 holds on PostgreSQL |
| the Feedback test (3) | 2 failed, 1 passed | a lone surrogate in model-written text escapes as a raw `DataError`: the follow-up risk is real. The side-by-side pair passed: the two escapes form a valid pair and `jsonb` stores one emoji. |

- **Feedback, effect today (by reading, not run):** `_claim` has already committed the attempt and the day's model-call reservation. `_finish` screens only for NUL (`has_nul`), so `_store` raises, `_finish` releases the lease and re-raises. The seeker gets a raw error and has used one of `INTERVIEW_FEEDBACK_MAX_ATTEMPTS` attempts and one reservation; after the last attempt the next request stores the rules report.
- **Plan (no service-level test exists and none was added):** the raw `plan` update refuses a lone surrogate (the two passes above), so the same hazard sits at `interview_service.create_session` (`plan=sealed.data`), outside the `try` around `build_canonical_plan`; `seal` checks `has_nul(data)` only. By reading: a surrogate in the model-written bank would give a raw error, a session left in `planning` until its lease ends (the one-active-session index blocks a new one), and the session and plan reservations spent. Not run, and not checked whether an earlier screen removes a surrogate from the bank. This is the gap §4A.5 S3 predicted.

Remediation is product code. D65 (6) and D66 (1) decided the NUL case, so a surrogate needs its own decision record and Long's approval, and the boundaries of §4A.2 stay untouched until then. Proposed:

- One check with the same placement and outcome as NUL: a helper next to `has_nul` that finds any code point U+D800 to U+DFFF in the same walk (`interview_ingest_service.py` already has the regex, `_SURROGATE`), called at the three sites that call `has_nul` on model-written data: `_finish` (drop the whole model report and use the rules report, as D66 (1)), `build_canonical_plan` for the bank, and `seal` for the data (`PlanRefused`, as for NUL). Open choice for Long: for the Plan, refuse as for NUL, or fall back to the rules bank.
- Tests, red before and green after, with no PostgreSQL needed: a model reply with a lone surrogate gives the provisional `model_failed` rules report, nothing stored and one attempt used (modelled on `test_interview_feedback_nul.py`); a model bank with a lone surrogate gives a 422 `INTERVIEW_NOT_AVAILABLE` and an aborted session (modelled on the NUL plan test). On SQLite both fail today, because SQLite stores the escape. On PostgreSQL the two failing S3 cases turn green, and a PostgreSQL Plan test is added to `test_interview_jsonb_postgres.py`.
- If Long declines the fix: the two cases stay red in S3 and again in S4 (Tier B contains the same test), so "every collected test passes" cannot hold. They would be recorded as known findings and deselected by an explicit `-k` or `--deselect`, which needs Long's approval.

**R-e. The sequence after the fixes**

Each run below is a new run with its own go from Long, as M0 and M1 were. It runs changed tests or code, so it is not a rerun to get green. The `env` block stays in state B until R1.

1. Approvals: R-a and R-b (test only: `test_interview_feedback_concurrency.py`, `test_interview_nul_postgres.py`); R-d (a decision record, the product fix, its tests); R-c (a decision, the fix, its tests). Long chooses which to include.
2. Local checks before any database step: `pytest` from the repo root on SQLite, with `TEST_DATABASE_URL`, `TEST_DATABASE_EXPECTED_NAME` and `TEST_DATABASE_CONFIRM_DESTRUCTIVE` removed from that command (state B has them in the block, so a bare `pytest` would run against PostgreSQL); `backend/tests/docs`. The P6 counts are re-taken, and any change from 194, 105, 16, 1430 and 3597 is explained before its step.
3. Preflight P1 to P7.
4. S1 again: expected 194 passed, plus any test added to those 12 files.
5. S2: five runs of the race set, 105 passed each.
6. S3 again: expected 16 passed, plus the new PostgreSQL Plan test.
7. S4: Tier B, 1430 passed plus new tests.
8. S5: Tier C (go-2), 3597 passed plus new tests.
9. R, the restore (go-3): R1 `DATABASE_URL` into the block, R2 the Q42 change in `backend/migrations/env.py`, R3 to R9; the end state is head, empty.
10. Close-out CO1 to CO9, with these five failures, their classes and the fixes in the tier-outcome record (CO3) and the list of CO4 extended if more test files change.

**Not covered:** the Plan surrogate path and the upload with a NUL on PostgreSQL have not been run; no real CV was used; a lone surrogate in a text column that takes user JSON text (outside the interview) was not examined.

**Remediation implemented (21/11/2026; SQLite only, nothing was run against PostgreSQL).** Long approved R-a, R-b, the surrogate fix (the Plan path included) and the CV-upload fix by sanitizing, and had D73 and D74 recorded.

- R-a: the two `repr()` comparisons in `test_interview_feedback_concurrency.py` compare by `==`. R-b: the NUL test patches `interview_service._read_stored_cv` and uses the `world` fixture. Both are PostgreSQL-only tests and skip on SQLite, so they stay unverified until the PostgreSQL steps.
- D73: `has_surrogate` in `interview_plan_service.py` (it shares the walk of `has_nul`), called with the outcome of a NUL at each place: in `_finish` of the feedback service (the whole model report is dropped, the failed-model-call path), for the bank (`surrogate_bank`) and at sealing (`surrogate_plan`). The cleaned-CV check (`nul_cv`) is unchanged. The pinned import list of the feedback service in `ai/tests/test_interview_backend_boundary.py` gained the one name.
- D74: `cv_service.upload` drops U+0000 from the file name (before the cut to 255 characters) and from the extracted text (before masking). Neither path can carry a lone surrogate (probed with synthetic input), so none is stripped. No new error code; the API contract is unchanged.
- New tests: `test_interview_surrogate_model_text.py` (49, including the service-level Plan test through `create_session`) and `test_cv_upload_nul.py` (10). With the surrogate checks switched off, 43 of the 49 fail (the 6 that pass are the valid-emoji cases and the four items the existing checks already drop); with the CV change reverted, 8 of the 10 fail (the two controls pass). No PostgreSQL-only Plan test was added: the service-level test is not gated and runs on PostgreSQL in Tier B.
- Correction to R-d: the Anthropic client parses the model's JSON text with `validate_json`, which refuses a lone surrogate escape as invalid JSON, so through that client a surrogate becomes a failed model call before the services see it. The S3 failure is real for a client that hands back a dict or an object, as the test doubles do (`FeedbackLlmOut.model_validate` accepts a surrogate in a `str` field; `model_validate_json` does not). D73 says so: the rule is a guard at the service boundary, not a failure seen in production.
- Local results, `TEST_DATABASE_*` and `DATABASE_URL` removed from each command: the two new files 59 passed; the changed and related files 137 passed, 21 skipped (the PostgreSQL-gated ones); `backend/tests/docs` 44 passed; `pytest` from the repo root 3516 passed, 140 skipped, 0 failed (227.6 s). The 140 skips are unchanged.
- New collection counts for P6: Tier A 194, the race set 105 and S3 16 are unchanged; Tier B 1479 (was 1430, the new surrogate file); Tier C 3656 (was 3597, both new files).
- The PostgreSQL runs that followed are recorded in the next subsection.

#### Results of the PostgreSQL runs after the remediation (21/11/2026 and 22/11/2026)

Facts as the runs reported them. The close-out items (CO1 to CO9) and the restore (R) have not been done. Every step ran under state B (`DATABASE_URL` absent from the `env` block) against `careersync_db` in `careersync-db-1`, one pytest process at a time, with `-q -rfEs --tb=short -p no:cacheprovider` (S3 with `--tb=long`), no `-x`, and no rerun of a step that had failed. Before the first step of each series: P1 to P7 (P4: only `careersync-db-1`, healthy; P5: 0 other client sessions; P7: `alembic_version` = `0012`, 0 application tables, no data, by Long's decision that the restore comes at the end). Before each later step: P3, P5, that step's P6 and a baseline of `pg_stat_database`. P6 counts used: S1 194, S2 105, S3 16 of 34, S4 1479 and S5 3656 in the second series; S4 1488 and S5 3665 in the third.

**All runs, in order** (counters are `xact_commit` / `tup_inserted` of `careersync_db`, before and after the step; times are those of pytest, with the wall-clock time where it differs):

| Run | Started | Result | Time | Counters before → after |
|---|---|---|---|---|
| S1, first | 21/11 15:46 | 3 failed, 191 passed, 0 skipped (194) | 163.6 s (wall 169 s) | 1986 / 7597 → 5307 / 411606 |
| S3, first | 21/11 | 2 failed, 14 passed, 0 skipped (16 of 34) | 16.0 s | 5362 / 411607 → 5598 / 450195 |
| S1, second (after R-a, R-b, D73, D74) | 21/11 16:28 | 194 passed, 0 skipped | 156.67 s (wall 162 s) | 6104 / 450196 → 9457 / 854526 |
| S2, second (5 runs of the race set) | 21/11 16:31 | 5 of 5 clean, 105 passed each, 0 skipped | 84.10, 84.92, 84.95, 105.52, 92.07 s (wall 469 s) | 9463 / 854526 → 20409 / 1983662 |
| S3, second | 21/11 16:39 | 16 passed, 18 deselected by the `-k` filter, 0 skipped | 13.64 s (wall 17 s) | 20414 / 1983662 → 20617 / 2022256 |
| S4, first | 21/11 16:40, ended 22/11 00:53 | 6 failed, 1473 passed, 0 skipped (1479) | 29612.39 s wall, which includes a machine suspend | 20623 / 2022256 → 38503 / 4955576 |
| Diagnostic: the race test, 30 runs | 22/11 01:02 | 30 of 30 passed (1 passed each) | 4.1 to 5.6 s each (pytest 1.37 to 2.91 s) | 38641 / 4955577 → 39514 / 5028584 |
| S4, second (after the five test fixes and D75) | 22/11 01:16 | 1488 passed, 0 skipped | 1081.23 s (wall 1088 s) | 39703 / 5028585 → 57648 / 7983067 |
| S5 (Tier C) | 22/11 01:34 | 3665 passed, 0 skipped | 1401.33 s (wall 1413 s) | 57655 / 7983067 → 79214 / 11468754 |

**Executed, not skipped.** The summary lines of S1 (second), S2, S3 (second), S4 (second) and S5 show no `skipped`, and there is no `-rs` section; each `passed` count equals the P6 count of its step (194; 105 in each of the 5 runs; 16; 1488; 3665). In S5 the PostgreSQL passed count equals the SQLite passed count plus its skips on the same code (3525 + 140 = 3665), so all 140 PostgreSQL-gated tests ran and passed. In every step `xact_commit` and `tup_inserted` rose, as in the table.

**The first failures, their class (the triage table of this section) and what was done**

| Run | Test | Cause | Class | Fix |
|---|---|---|---|---|
| S1 | `test_interview_feedback_concurrency.py::test_pg_in_rules_mode_parallel_requests_store_one_report_and_all_return_it` and `::test_pg_a_session_whose_third_attempt_died_is_recovered_once_by_parallel_requests_without_a_model` | compared `repr()` of the report dicts: the request that stored the report returns its own dict, the others the one `jsonb` gave back, with its keys in `jsonb` order (the log shows both orders) | T1 | R-a: compare by `==` |
| S1 | `test_interview_nul_postgres.py::test_pg_a_cv_with_nul_is_refused_before_the_model_and_nothing_is_stored` | the fixture inserts a CV with a NUL, and PostgreSQL refuses it (`DataError`) before the code under test runs | T1 | R-b: the `world` fixture, and `interview_service._read_stored_cv` patched |
| S3 | `test_interview_jsonb_postgres.py::test_postgres_a_surrogate_in_a_model_feedback_ends_as_a_report_and_never_a_raw_error[a high surrogate]` and `[a low surrogate after text]` | `jsonb` refuses a lone surrogate, and the feedback service screened only for NUL, so a raw `DataError` reached the caller (the third case, two code points side by side, passed) | T2 | D73: a surrogate is refused like a NUL at the feedback, the question bank and the sealing of a plan. The Anthropic client refuses a surrogate escape as invalid JSON, so D73 is a guard at the service boundary |
| S4 | `test_interview_api_create.py::test_a_cv_the_plan_refuses_is_422_not_available_and_the_session_is_closed` and `test_interview_nul.py::test_a_cv_with_nul_is_refused_before_any_model_sees_it` | the fixture stores a CV with a NUL (as the S1 failure above) | T1 | `_read_stored_cv` patched, a clean `build_world` |
| S4 | `test_interview_api_feedback_model.py::test_the_model_is_called_with_no_transaction_open_after_the_lease_the_attempt_and_the_reservation_were_committed_together` and `::test_a_failed_model_call_also_happens_outside_any_transaction_and_ends_with_a_fenced_release` | the tests look for `feedback_lease_token = ?` in the statement text; PostgreSQL's text has `= %(feedback_lease_token_1)s::VARCHAR` (the fence is there) | T1 | helper `fenced_by_lease_token`, which accepts both forms and still asserts the fence |
| S4 | `test_interview_models.py::test_a_bad_turn_is_refused[overrides0]` | the role `interviewer` is 11 characters, the column is `varchar(10)`: PostgreSQL raises `DataError` before the check constraint, the test expects `IntegrityError` | T1 | the invalid role is `observer` (8 characters) |
| S4 | `test_interview_feedback_concurrency.py::test_pg_five_sessions_in_parallel_never_take_more_than_the_daily_limit` | 2 reservations granted instead of 3 (2 `model_failed` and 3 `quota`); it had passed in S1 and in the 5 runs of S2 | T4 | traced and diagnosed below; D75 |

The comment in `test_interview_nul_postgres.py` that said SQLite tests the NUL guard with a really stored NUL was wrong (no test can store one on PostgreSQL) and was corrected. Local checks after the five test fixes: the changed files 132 passed and 9 skipped, `backend/tests/docs` 44 passed.

**The quota test of S4, traced and diagnosed (22/11/2026)**

- *Read-only trace.* Reason `quota` has one producer: `claim()` of `interview_quota_service.py` returning False (`_LIMITED` in the feedback service); no `except` maps an error to it. Server and pool: `lock_timeout`, `statement_timeout` and `idle_in_transaction_session_timeout` are 0, `deadlock_timeout` 1 s, isolation `read committed`, no per-database or per-role overrides, PostgreSQL 16.15; 0 deadlocks recorded for the database across S1 to S4; the engine pool is 5 plus 10 overflow (timeout 30 s) and the test needs at most 6 connections; the test clock is fixed (12:00 KST), so no lease or day boundary is involved; every change of the daily limit in the tests uses `monkeypatch`.
- *Diagnostic run.* The one test, 30 times, each in a fresh pytest process against PostgreSQL: 30 of 30 passed. Counting all runs of this test before the fix: 37 passed (S1 first and second, the 5 runs of S2, the 30 isolated runs) and 1 failed (S4, first); 0 failures in 30 isolated runs cannot rule out a rate of a few per cent.
- *Replay.* On in-memory SQLite, with the real `claim`: request A creates the row (used 1 of 3) and commits; request B's UPDATE matches no row (made to, as it would before A's commit) and its existence check then finds the row; `claim` answered False with the row at 1 of 3. The existing test of the creation race covers only the case where both the UPDATE and the existence check miss the row. That this interleaving caused the S4 failure is the match of its symptom, not a proof.
- *Fix, D75.* In `claim`, when the UPDATE matches no row and the row exists, the UPDATE is tried once more and its result is the answer. The module docstring has one added sentence. Why one retry is enough is in D75: a row that has been seen is committed and stays (the purge deletes only days before today, a deleted user takes the seeker's rows), and the retry waits for a concurrent writer and then tests `used < quota_limit` on the latest committed row.
- *Tests and local checks.* 9 new tests in `test_interview_quota.py` (3 cases for each of the 3 kinds): 9 red before the fix, 9 green after. The quota and feedback test files 157 passed, 21 skipped; `backend/tests/docs` 44 passed; `pytest` from the repo root, `TEST_DATABASE_*` and `DATABASE_URL` removed from the command, 3525 passed, 140 skipped, 0 failed (239.57 s), 3665 collected.

**The machine suspend.** The first S4 run was suspended: the machine entered Modern Standby on 21/11/2026 at 16:44:15 (after 288 of the 1479 tests) and left it on 22/11/2026 at 00:39:05. The log did not change for about 8 hours, the stall watcher reported a stall on waking (a false alarm of its own clock), and the pytest process went on by itself; its 29612 s are mostly the suspend, and the time awake was about 18 minutes (an estimate). Three of the six failures (positions 61, 161 and 162 of the collection) were in the log before 16:44, so they are from before the suspend; the other three (positions 555, 1063 and 1097) ran after it, the quota test (555) about 5 minutes after the machine woke. From the next runs on, the step runner holds the system awake (a process-scoped execution-state request, released when the script ends), and S4 (second) and S5 ran without a suspend.

**What the runs do not cover.** S1, S2 and S3 of the second series ran before D75 and before the five test fixes, and have not been rerun since; S2 (the five repeats of the race set) has not been run on the code with D75. S5 ran after every change and contains every test file of S1, S3 and S4 once. The upload with a NUL through the API and the extraction of a real CV have not been run against PostgreSQL beyond what the full suite contains.

#### Restore, `alembic check` and close-out (go-3, 22/11/2026)

Long gave go-3 with the `env` block in state C. Every Alembic command ran from `backend/` with `d:\dev\project\CareerSync\.venv\Scripts\python.exe -m alembic`. The read-only checks were short scripts in the session scratchpad that printed only counts, object names and the version; no value, URL or row was printed.

| Step | Result |
|---|---|
| R1, environment | `DATABASE_URL` present and equal to `TEST_DATABASE_URL` (compared in code, nothing printed); the five required variables present, `CAREERSYNC_DOTENV` = `0`, `AI_MODE` = `rules`; the nine `PG*` names absent. |
| Preflight | `db_safety.py --app` exit code `0` ("the rules passed and the server answered with the approved database"); `docker ps`: only `careersync-db-1`, up and healthy (P4); read-only probe: 0 other client sessions (P5), the approved database name, 0 application tables, `alembic_version` = `0012` (stale), as R0 expects. |
| R4 | `alembic stamp --purge base` exit code `0`; `alembic current` showed no revision. |
| R5 | `alembic upgrade head` applied every revision from `0001` through `0012` without error; `alembic current` showed `0012 (head)`; `alembic heads` showed that one head. |
| R6 | Read-only: 28 application tables plus `alembic_version` = `0012`; every application table empty (no row in any); the three interview tables: five foreign keys, all `ON DELETE CASCADE`, none from the quota table to a session; seven indexes besides the primary keys, which are the six explicit ones (`ix_interview_quota_kst_day`, `ix_interview_sessions_cv_profile_id`, `ix_interview_sessions_expires_at`, `ix_interview_sessions_job_id`, `ix_interview_sessions_seeker_created`, `uq_interview_sessions_active`) and the index of the unique constraint `uq_interview_turns_session_seq`; `uq_interview_sessions_active` unique and partial on `planning`, `created` and `live`; ten named check constraints; `jsonb` for six columns and `timestamptz` for nine. Same as D70. |
| R2 | `backend/migrations/env.py` changed as drafted: `IGNORED_INDEXES`, `include_object` and the argument of the one `context.configure` call of the online path, with the comment; the offline path is unchanged. Applied after R5 (see R2 above). |
| R7 | `alembic check` exit code `0`: "No new upgrade operations detected". `alembic current` and `alembic heads` on the final file: `0012 (head)`. |
| R8 | Read-only `compare_metadata` through the Alembic API, without `env.py`: two differences, `remove_index` and `add_index` of `uq_job_criteria_job_name` on `job_criteria`, and nothing else. So the filter, and only the filter, removed them. |
| R9, end state | `0012 (head)`, `alembic_version` = `0012`, 28 application tables, no data, no seed, 0 other client sessions. |

No pytest ran against PostgreSQL during the restore, so no `pg_stat_database` movement is recorded for it. Nothing wrote to the database after the Alembic commands.

**State of the database and the environment (22/11/2026, after the restore).** `careersync_db` is at `0012 (head)` with 28 application tables, all empty; no seed, no backup, no other client session. The `env` block was in state C (state B plus `DATABASE_URL`) during the restore. Long removed it afterwards (state D): a presence check on 22/11/2026 (booleans only) found none of the five required variables, `DATABASE_URL` or the nine `PG*` names set in the session.

**Status:** Passed. Plan approved by Long on 21/11/2026 (A1 to A5). After the remediation S1, S2 and S3 passed, and after the five test fixes and D75 S4 and S5 passed, as recorded above; the restore (R) and `alembic check` passed on 22/11/2026. The close-out is done, CO1 to CO9 (CO4, the docstrings of eight test files, after Long's OK). The migration QA passed earlier (§4A.4, D70). The database is at `0012` and empty; the `env` block has been removed (state D).

---

## 5. Phase 5 — Realtime Interview Agent (M5)

**Mục tiêu:** Implement the realtime interview agent and connect it to the M4 session lifecycle.

- [ ] Review and approve the M5 implementation plan
- [ ] Implement the planned LiveKit realtime agent
- [ ] Connect the agent to the existing interview session API/services
- [ ] Implement agent-owned `record_end` behavior for closing turn/event persistence
- [ ] Detect session deletion/404 and stop or disconnect the agent
- [ ] Ensure consent and session lifecycle rules are respected
- [ ] Add tests for disconnect, deletion and end-of-session behavior
- [ ] Verify model/agent boundaries and avoid bypassing the approved `compose()` / `ask()` flow

**Important:** `interview_poc/` is a separate avatar/realtime proof of concept. Its existence or successful manual avatar testing does not mean M5 is implemented or production-ready.

**Status:** Not Started

---

## 6. Phase 6 — AI Interview Frontend Integration (M6)

**Mục tiêu:** Integrate the interview experience into CareerSync's frontend after the backend/agent integration path is ready.

- [ ] Review and approve the M6 implementation plan
- [ ] Connect the frontend to interview consent and session creation
- [ ] Implement the interview session experience
- [ ] Implement session history and detail views
- [ ] Implement session end and deletion flows
- [ ] Integrate feedback display
- [ ] Handle loading, errors, expired sessions and unavailable agent states
- [ ] Add frontend tests and end-to-end coverage

**Status:** Not Started

---

## 7. Phase 7 — CareerSync Chatbot Feature

**Mục tiêu:** Track the chatbot as a feature inside CareerSync, not as a separate project.

- [ ] Consolidate the latest chatbot scope and milestone plan from the current implementation records
- [ ] Record implemented backend and frontend components
- [ ] Record integration points with CareerSync's existing job/user data
- [ ] Record privacy, data-access and model-call boundaries
- [ ] Record exact test evidence and remaining limitations
- [ ] Update this section after each completed chatbot implementation batch

**Status:** In Progress — detailed task-level status must be synchronized from the latest chatbot implementation report before marking individual items complete.

---

## 8. Phase 8 — Integration, System Testing & Bug Fixing

**Mục tiêu:** Validate the complete CareerSync platform after M5, M6 and chatbot feature integration are ready.

### 8.1 Functional Integration

- [ ] Verify AI Interview session creation and lifecycle through the real application flow
- [ ] Verify realtime agent connection and disconnection
- [ ] Verify interview history, detail, deletion and feedback
- [ ] Verify chatbot end-to-end workflows
- [ ] Verify integration with existing job and candidate workflows

### 8.2 Privacy, Security & Reliability

- [ ] Resolve Q24
- [ ] Resolve Q35 before production model use
- [ ] Resolve Q39
- [ ] Review authentication and authorization for every new route
- [ ] Verify sensitive data is not exposed in responses or logs
- [ ] Verify model failures and invalid outputs fail safely
- [ ] Verify concurrency and race conditions against PostgreSQL
- [ ] Verify retention and deletion behavior

### 8.3 Final Validation

- [ ] Run the complete backend test suite
- [ ] Run PostgreSQL integration and migration tests
- [ ] Run frontend tests
- [ ] Run end-to-end tests for key user and recruiter workflows
- [ ] Fix critical bugs
- [ ] Re-run regression tests
- [ ] Confirm clean startup and setup instructions

**Status:** Not Started as a complete platform-wide validation phase. Component-level local tests have passed as recorded above.

---

## 9. Phase 9 — Documentation & Release Readiness

**Mục tiêu:** Keep project documentation aligned with the actual implementation and prepare the platform for release.

### 9.1 Documentation

- [x] Maintain product and decision documentation baseline
- [x] Maintain technical architecture documentation baseline
- [x] Update PostgreSQL QA runbook after actual database QA *(22/11/2026: `PROJECT_DOCUMENTATION.md` §9, the `TEST_DATABASE_URL` row and the new "PostgreSQL test database" paragraph, and `docs/how-to/run-locally.md` §9)*
- [x] Add D70 after the PostgreSQL migration QA *(21/11/2026)*
- [x] Add D76 (Q42) and D77 (the tier outcome, the restore and `alembic check`) *(22/11/2026)*
- [ ] Synchronize the chatbot implementation status and documentation
- [ ] Synchronize M5/M6 implementation documentation after completion
- [ ] Record final test evidence and known limitations
- [ ] Verify setup instructions against a clean environment

### 9.2 Release Readiness

- [ ] Resolve production blockers Q24, Q35 and Q39
- [ ] Review environment variables and deployment configuration
- [ ] Verify no credentials, `.env` files or local secrets are included
- [ ] Review migrations and database restore procedure
- [ ] Verify monitoring, logging and operational retention requirements
- [ ] Complete final regression tests
- [ ] Approve production-readiness status explicitly

**Status:** In Progress — foundational documents exist; the PostgreSQL QA close-out is done, and unresolved decisions remain.

---

## 10. Current Project Status

| Phase / Track | Status | Notes |
|---|---|---|
| M0 — Architecture & documentation | Completed | Baseline docs and D51–D58 recorded. |
| M1 — Pure rules engine | Completed | Local tests pass. |
| M2 — LLM turn integration | Completed | Structured output and deterministic fallback. |
| M2.1 — CV privacy guard | Implemented and locally verified | Vocabulary-based masking has known limits. |
| M2.1.1 — Architecture/serialization guards | Completed | Local architecture tests pass. |
| M3 — Evidence-grounded feedback | Completed | Quote-grounded; no score/ranking/verdict. |
| M4 — Database and seeker API | Implemented, locally verified and verified on PostgreSQL; not production-ready | S1–S4.5 implemented; migration QA passed (D70); the gated tests, the JSONB diagnostics and the concurrency tests passed on PostgreSQL (D77). Q24, Q35, Q39 and M5 are open. |
| PostgreSQL safety hardening | Completed; exercised on PostgreSQL | W1/W2/W3/W5 and 80 N1–N9 tests added; the guards ran in front of every PostgreSQL step and the N1–N9 tests passed on PostgreSQL (D77). |
| PostgreSQL QA | Passed: migration QA (M0 + M1) 21/11/2026; test tiers, restore and `alembic check` 22/11/2026 | Tiers A, B and C passed after the fixes of D73 to D75 (outcome D77); the schema was restored, and `alembic check` exits 0 with the filter of D76. The database is at `0012` (28 application tables), no data, no seed. Scope in D71; procedures and results in §4A.4 and §4A.5. The close-out is complete (CO4, the docstrings of eight test files, done 22/11/2026). |
| M5 — Realtime agent | Not Started | Planned around LiveKit. |
| M6 — Frontend integration | Not Started | Depends on M5/API integration plan. |
| Chatbot feature | In Progress | Part of CareerSync; task-level status needs synchronization. |
| Platform integration/release | Not Started | Depends on QA, M5/M6 and open decisions. |

### Current Blocking Issue

**No technical blocker.** The migration QA (M0 + M1) passed on 21/11/2026 (D70). The PostgreSQL test tiers passed, the schema was restored and `alembic check` exits 0 (22/11/2026; D76, D77). The documentation guards run clean: Q41 is closed by D72, which exempts this tracker from three of them. What stands between this and a release is not PostgreSQL QA: Q24, Q35 and Q39 are open and M5 and M6 are not started.

### Next Priority

1. Phase 5 (M5): review and approve its plan. Q39 has to be decided before M5 (D65 binds M5 to it); Q35 before production model use; Q24 stays open.

### Open Items and Decisions

| Item | Status | Handling |
|---|---|---|
| Q24 | Open | Keep unresolved; use the authoritative decision record for exact scope. |
| Q35 — processor disclosure / consent | Open — production blocker | Per D52 and Q35, PII-masked text goes to Groq (the Interview Agent's per-turn analysis), and the candidate's raw voice goes to LiveKit Inference for speech recognition and, with the turn detector pinned to `v1` in the PoC, for turn detection. Masking is best effort (D39, D53). Whether these processors need the same legal check as Q29, and a notice that names them to the candidate, is open. Current consent wording does not name the processors (D65). Resolve before production use; do not call current consent legal approval. |
| Q39 — consent withdrawal during a live session | Open | Keep unresolved until explicitly decided and documented. |
| Q41 — tracker vs doc-drift guards | Closed 21/11/2026 (D72) | Long excluded this tracker from the English-only, hand-typed-test-count and referenced-ID guards: it is a working tracker, not a source of decisions. One named entry, `TRACKER` in `backend/tests/docs/markdown.py`, applied by those three tests only; every other guard, the folder-tree guard included, still reads it. The tracker's own text is not changed by this. |
| Q42 — `alembic check` false positive on `uq_job_criteria_job_name` | Closed 22/11/2026 (D76) | Cosmetic: PostgreSQL stores `lower(TRIM(BOTH FROM name))`; the model and migration `0002` write `lower(trim(name))`. Long decided (21/11/2026) to filter that one index name out of the comparison in `backend/migrations/env.py` and keep the model expression (SQLite cannot parse the `TRIM(BOTH FROM ...)` form). Applied on 22/11/2026; `alembic check` exits 0 at head and a comparison without `env.py` still shows exactly that pair. The Q42 row was removed from `docs/DECISIONS.md` §3. Limit: a real change to that index is hidden from autogenerate too, so review it by hand. |
| D76 | Recorded 22/11/2026 | The Q42 decision and its implementation (the `include_object` filter, its scope and limit, the `alembic check` result). |
| D77 | Recorded 22/11/2026 | The outcome of the PostgreSQL test tiers, the restore and `alembic check`: the eleven failures with their classes (eight test-only fixes, D73, D75), the passing runs, the JSONB result, the restore, the end state, and what is not covered. D73 to D75 hold the three product fixes. |
| D71 | Recorded 21/11/2026 | Scope of the PostgreSQL QA reset: all data in `careersync_db` disposable, no automatic seed, no automatic backup, existing container and volume only. It is a scope record, not an approval of M0. |
| D70 | Recorded 21/11/2026 | Outcome of the PostgreSQL migration QA (M0 + M1): the results, the eleven-difference comparison at `0011`, the accepted `uq_job_criteria_job_name` drift with the `pg_get_indexdef` evidence, and the end state `0012` with no data and no seed. It does not cover the guard mode, W1/W3/W5, the `_pgtest` documentation discrepancy or the PostgreSQL test tiers, which the earlier plan listed for D70. |
| Feedback/Plan surrogate behavior in PostgreSQL JSONB | Closed (D73) | The diagnostics found it on PostgreSQL (two failed); D73 refuses a surrogate like a NUL at the feedback, the question bank and the sealing of a plan; the diagnostics and the service-level Plan test pass on PostgreSQL (D77). A guard at the service boundary: the Anthropic client already refuses a surrogate escape as invalid JSON. |
| Physical retention purge | Not configured | 30-day logical read hiding and lazy purge exist; physical purge requires an external scheduler. |
| M5 deletion handling | Not implemented | Future agent must detect deleted session/404 and stop or disconnect. |
| M5 closing event | Not implemented | Future agent's `record_end` flow owns closing turn/agent event persistence. |
| Chatbot task-level progress | Needs synchronization | Chatbot remains a CareerSync feature; do not create a separate project tracker. |

---

## 11. Git & Change-Control Status

**Last reported Git state — refresh before acting:**

- Branch: `feature/ai-avatar-poc`.
- Last shared commit: `8a094f1` — `feat: add AI interviewsystem and avatar POC`.
- The branch was reported synchronized with `origin/feature/ai-avatar-poc` at that point.
- PostgreSQL safety hardening, N1–N9 tests and Unicode surrogate hardening were added after that commit and were still uncommitted in the last reported working-tree state.
- `.mcp.json` was reported as untracked. Do not open, read, stage or commit it as part of this workflow.

Before creating a commit:

- [ ] Refresh `git status`
- [ ] Review the complete diff
- [ ] Verify no credentials, `.env`, `.mcp.json` or local database configuration are staged
- [ ] Confirm the exact files to include
- [ ] Obtain the user's explicit instruction before staging/committing/pushing

**Rule:** Never commit, amend or push merely because an implementation batch or test suite completed.

---

## 12. Progress Update Log

Use this section to record major completed or blocked batches. Record actual outcomes, not planned work.

| Date (KST) | Update | Status / evidence |
|---|---|---|
| 20/11/2026 | M0–M3 AI Interview core | Implemented and locally verified. |
| 20/11/2026 | M4 S1–S4.5 database and seeker API | Implemented; local verification passed; PostgreSQL verification pending. |
| 20/11/2026 | PostgreSQL safety hardening W1/W2/W3/W5 and N1–N9 tests | 283 safety tests passed; full suite after Stage 1: 3,329 passed, 137 skipped. PostgreSQL-gated tests were not run against PostgreSQL. |
| 20/11/2026 | Unicode surrogate hardening | 127 dedicated tests passed; latest full suite: 3,456 passed, 140 skipped. PostgreSQL JSONB diagnostics pending. |
| 20/11/2026 | PostgreSQL Stage 3 preflight attempt | Blocked before connection: `TEST_DATABASE_URL` absent; exit code 2; no connection, read or write occurred. |
| 21/11/2026 | PostgreSQL Stage 3 read-only identity/inventory | Reported by Long: `careersync_db` on PostgreSQL 16.15 (`careersync-db-1`, `127.0.0.1:5434`), Alembic `0011`, 25 application tables, 0 other connections, inside a `READ ONLY` transaction. Stage 3 not marked complete. |
| 21/11/2026 | Stage 3.1 source–database reconciliation (static) | 28 model tables = 25 at `0011` (match the inventory) + 3 from `0012`; linear graph `0001→…→0012`, one head; 80/80 named indexes/constraints match. No DB, Docker, pytest, Alembic or DDL/DML used. Five plan corrections proposed, awaiting Long. |
| 21/11/2026 | Stage 3.1 accepted by Long; QA plan finalized; D71 recorded; Q41 opened | M0 smoke test chosen (`backend/tests/test_matching_models.py::test_seeker_preferences_store_recommendation_inputs`); environment, M0 to M1 sequence, Alembic check triage and readiness checklist written in §4A.4. Documentation only: no database, Docker, pytest or Alembic use. The repo's doc-guard functions were called directly on the two edited files: `docs/DECISIONS.md` clean; `PROJECT_PROGRESS.md` fails the guards named in Q41. |
| 21/11/2026 | PostgreSQL migration QA: M0 reset and M1 restore executed and passed; D70 written; Q42 opened | Preflight P1 to P6 passed. The one M0 smoke test passed with nothing skipped, and the post-check found no application table (`alembic_version` = `0011`). M1: `upgrade head` through `0012`, 28 application tables plus `alembic_version`, the three interview tables checked item by item, no data. The round trip through `0011` was clean. Comparison with the models: at `0011`, the three interview tables and six indexes as additions plus the `uq_job_criteria_job_name` pair; at head, only that pair, accepted by Long as cosmetic drift (Q42). Database left at `0012`, no seed, no backup. Procedure amended in §4A.4 (interpreter, VS Code `env` block, `compare_metadata` at `0011`). Not run: the PostgreSQL-gated test tiers. Documentation guards afterwards: four still fail (the three of Q41 and the folder-tree guard); D70 is no longer undefined. |
| 21/11/2026 | Documentation cleanup | `PROJECT_PROGRESS.md` added to the folder tree of `PROJECT_DOCUMENTATION.md` (the folder-tree guard now passes); the stale "not written yet" wording removed from Q41; the Q35 row aligned with D52 and Q35 (Groq and LiveKit Inference). Documentation guards afterwards: only the three of Q41 still fail (the ID guard on the Unicode-range reference, the language guard, the hand-typed counts); every other guard passes. |
| 21/11/2026 | Q41 decided and closed; D72 written | Long excluded this tracker from the English-only, hand-typed-test-count and referenced-ID guards. Implemented as one named entry (`TRACKER`, with a reason comment) in `backend/tests/docs/markdown.py`, passed as `skip` to `guarded_docs` by those three tests only, plus one helper test that pins the scope (the other guards and the link guard still read the tracker). The Q41 row was removed from `docs/DECISIONS.md` §3. Documentation guards afterwards: all pass; before, the three of Q41 failed. Full suite afterwards (SQLite, PostgreSQL-gated tests skipped): 3457 passed, 140 skipped, exit code 0. |
| 21/11/2026 | §4A.5 plan for the PostgreSQL test tiers written; Q42 decided | Planning only: nothing destructive ran, no pytest against PostgreSQL, no Alembic command that writes. Measured read-only with the database variables removed: Tier A is 12 files, 194 collected, 57 of them PostgreSQL-gated; the six Stage 1 files hold 83 gated tests (80 of N1 to N9 and 3 diagnostics); Tier B is 39 files, 1430 collected, 125 gated; the whole suite is 3597 collected, 140 gated, all in those 19 files. The plan sets the steps, the `env` block states (`DATABASE_URL` absent for pytest, present only for the restore), the proof that gated tests executed, stop conditions, the restore and `alembic check`, a recommendation for Tier C (yes), and the close-out. The Q42 filter for `backend/migrations/env.py` is drafted, not applied. Waiting for Long's approval. |
| 21/11/2026 and 22/11/2026 | PostgreSQL test tiers S1 to S5 run; eleven failures fixed in three groups; D73, D74 and D75 written | First series: Tier A 3 failed and the JSONB diagnostics 2 failed (stop conditions 2 and 3). Remediation: the `jsonb` key-order and NUL tests fixed (test only), D73 (a surrogate refused like a NUL in the feedback and the plan), D74 (the CV upload drops U+0000). Second series: S1 194 passed; S2 five of five runs of 105 clean; S3 16 passed; S4 first run 6 failed (five test assumptions and one race in the daily-quota claim); five test fixes and D75 (one retry in `claim`); S4 second run 1488 passed; S5 (Tier C) 3665 passed, none skipped. Details in §4A.5 and D77. |
| 22/11/2026 | Restore (go-3) and `alembic check`; Q42 change applied; close-out; D76 and D77 written | Guard `--app` passed; `alembic stamp --purge base` and `upgrade head` gave `0012 (head)`, one head, 28 application tables, all empty, the three interview tables as in D70. The Q42 filter was applied to `backend/migrations/env.py`: `alembic check` exit code 0; a comparison without `env.py` still showed exactly the `uq_job_criteria_job_name` pair. Runbook folded into `PROJECT_DOCUMENTATION.md` §9 and `docs/how-to/run-locally.md` §9; Q42 removed from `docs/DECISIONS.md` §3. Local after the edits (SQLite, database variables removed): full suite 3525 passed, 140 skipped; `backend/tests/docs` 44 passed. Not done: CO4. Waiting for Long to remove the `env` block. |
| 22/11/2026 | CO4 done: eight test docstrings updated; `env` block removed by Long | In `test_interview_jsonb_postgres`, `_retention_postgres`, `_planner_race_postgres`, `_ingest_more_postgres`, `_cascade_postgres`, `_migration_postgres`, `_nul_postgres` and `test_interview_create_concurrency`, the sentence that said the tests were written, not run, now says they ran and passed on PostgreSQL on 2026-11-22 (D77). Only those docstring sentences changed. Local SQLite run (database variables removed from the command): the eight files collect 95 tests, all 95 skipped (all PostgreSQL-gated), none failed; `backend/tests/docs` 44 passed. The full suite was not rerun for this docstring-only change; its last result stays 3525 passed, 140 skipped. A presence check found none of the QA variables set in the session (state D). |

Add a new row whenever a coherent implementation, verification, migration, decision or blocker changes the project state.

---

## 13. Rules for Maintaining This Tracker

1. Mark a task `[x]` only after its implementation or deliverable has been verified.
2. Use `[ ]` for tasks that have not started, are blocked or are not yet complete; explain the blocker in the relevant section.
3. Do not mark a milestone or phase Completed while critical acceptance criteria remain.
4. Keep **implemented**, **locally verified**, **verified on PostgreSQL**, and **production-ready** as separate states.
5. Record exact test commands and actual result counts, including skipped tests and why they were skipped.
6. Update the progress log after each coherent completed batch or important blocker.
7. Keep open decisions Q24, Q35 and Q39 visible until formally resolved.
8. Do not treat a plan, prompt, code review or skipped PostgreSQL test as proof that PostgreSQL behavior passed.
9. Do not execute destructive database operations until the read-only inventory has been reviewed and the user has explicitly approved the operation.
10. Never bypass database safety guards. Never read `.env` or `.mcp.json` for this QA workflow.
11. Never record passwords, tokens, complete database URLs, connection strings, PII or other secrets in this file.
12. Refresh Git state before describing the branch as clean or synchronized. Do not commit/push without explicit user instruction.
13. Keep the Chatbot tracked as a CareerSync feature, not as a separate project.
14. When this file conflicts with a newer approved decision or actual test output, update the tracker to match the authoritative source; do not silently change the underlying decision.

---

## 14. Related Project Documents

Use repository source documents for detailed specifications and decision history; this tracker is a progress overview, not a replacement for them.

- `PRODUCT.md` — product requirements and scope.
- `DECISIONS.md` — decision records and unresolved questions.
- `PROJECT_DOCUMENTATION.md` — technical architecture and implementation documentation.
- `backend/tests/db_safety.py` — test database safety enforcement.
- `backend/tests/` — automated tests, including PostgreSQL-gated tests.
- `interview_poc/` — separate avatar/realtime proof of concept.

