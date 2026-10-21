# 🎯 CareerSync

**Criteria-Based Hiring & Job Matching Platform**

A multi-company recruiting platform where each company's own evaluation criteria are used both to score applicants and to recommend jobs to people who haven't applied yet.

Soongsil University RISE Capstone project. This is a working prototype under active development; the [Status](#-status) section says what runs today and what is still planned.

Decisions and scope: [`docs/DECISIONS.md`](docs/DECISIONS.md) (source of truth). Technical reference: [`PROJECT_DOCUMENTATION.md`](PROJECT_DOCUMENTATION.md).

[Status](#-status) · [Run It Locally](#️-run-it-locally) · [Troubleshooting](#️-troubleshooting) · [API](#-api-overview) · [Project Structure](#-project-structure)

---

## 📌 Overview

CareerSync connects a company's real hiring criteria with a job seeker's skills and preferences, and returns an explainable match result to both sides.

- **Companies** struggle most with finding candidates (44.5%) and reviewing applications (41.0%).
- **Job seekers** don't know what a company actually values, or how well their CV fits before applying.

The core idea: **one set of company-defined criteria powers two things**: scoring submitted applicants and recommending jobs to non-applicants, on a single shared platform.

> AI never accepts or rejects a candidate; application status changes only by recruiter action.

## 🚦 Status

| Feature | Status | What exists today |
| --- | --- | --- |
| 🔐 Authentication | ✅ Done | Register as seeker or company with privacy and AI consent, JWT login (2 h access token, Argon2id passwords), re-consent screen, seeker can withdraw AI consent |
| 🏢 Company profile | ✅ Done | Name, intro, 인재상 (talent profile), running projects (shown on the public company page and usable as context for AI JD drafts) |
| 📝 Job postings | ✅ Done | Draft → published → closed; after publish only deadline, location and salary note can change. AI drafts a JD for a draft job and suggests a criteria draft from the JD |
| ⚖️ Criteria & weights | ✅ Done | Per-job criteria (max 10, integer weights summing to 100), live guardrail that blocks discriminatory criteria with the law that forbids them |
| 📄 CV analysis | ✅ Done | Upload a text PDF (≤ 5 pages, ≤ 5 MB), PII is masked, skills/education/experience/projects/certificates are extracted, the seeker edits and confirms (each save is a new version); AI self-check of the CV (strengths, improvements) |
| 📊 Applicant evaluation | ✅ Done | Apply → background scoring → recruiter sees applicants ranked by Fit with per-criterion score, evidence and comment, with quick filters. Weight edits re-rank without new AI calls |
| 🧑‍💼 Recruiter workflow | ✅ Done | Status changes (검토 전, 서류 검토, 면접 예정, 보류, 합격, 불합격) only happen when the recruiter clicks |
| 🎯 Job recommendation | ✅ Done | 추천 공고: jobs matching the seeker's preferences and the job's criteria, shown with a match band (매우 적합 / 적합 / 참고), no scores |
| 🧭 Job preparation | ✅ Done | 취업 준비 for a job: skills the job asks for that the CV lacks with a learning plan, and interview practice questions |
| 🔎 Talent recommendation (인재 추천) | ✅ Done | Companies see anonymous opted-in seekers per published job and send offers; contact details only after the seeker accepts |
| 🐳 `docker compose up` | ✅ Done | Starts DB, migrations + demo seed, backend and frontend. See [Compose guide](docs/docker-compose.md) |

## 🧠 How Scoring Works

| Step | Approach |
| --- | --- |
| CV / JD structuring | LLM with JSON output when `AI_MODE=llm`, rule-based otherwise (default `AI_MODE=rules`); skill names are normalized with `data/skills.yaml` and experience months are always computed in code. Prompts are versioned in `ai/prompts/v1/` |
| Skill, experience, education, certificate criteria | Rule-based scoring; skills matched with a dictionary and declared groups of related skills (`data/skills.yaml`); `intfloat/multilingual-e5-base` embeddings for retrieval |
| Project / other (judgment) criteria | LLM with a rubric and evidence quoted from the CV; in `AI_MODE=rules`, keyword retrieval is used instead |
| Fit score | Weighted sum of stored per-criterion scores, recomputed from the current weights |
| Criteria guardrail | `data/blocklist.yaml`: 채용절차법 제4조의3 items plus gender, age, religion, disability, each tagged with its law |
| Privacy | Name, email and phone are masked before any text is sent to the LLM |

Pretrained models only; nothing is trained from scratch. The LLM is always called through `LLMClient` (`ai/llm/client.py`), so the model can be swapped without touching callers.

## 🧰 Tech Stack

| Layer | Technologies |
| --- | --- |
| Frontend | React 19 · TypeScript · Vite · React Router (Korean UI, desktop-first) |
| Backend | Python 3.11+ · FastAPI · SQLAlchemy 2 · Alembic · Pydantic 2 |
| AI | Anthropic API behind `LLMClient` (optional) · sentence-transformers (multilingual-e5-base) · PyMuPDF |
| Database | PostgreSQL 16 (tests use in-memory SQLite) |
| Auth | JWT (PyJWT) · Argon2id |
| Infrastructure | Docker (for PostgreSQL) · Git / GitHub |

```
Browser ──► Vite dev server :3000 ──(/api proxy)──► FastAPI :8000 ──► PostgreSQL :5433 (Docker)
                                                        │
                                                        └──► ai/ (parsing, scoring, guardrails) ──► LLM API (optional)
```

## 🐳 Run with Docker Compose

With Docker Desktop running, create `.env` from `.env.example` if needed, then run `docker compose up --build -d`. The demo embedding `intfloat/multilingual-e5-base` is the default and downloads about 1 GB on the first run (kept in the `model-cache` volume); set `EMBEDDING_MODEL=hashing-ngram-v1` only for a quick try. Open http://localhost:3000. See [the full guide](docs/docker-compose.md) for ports, logs and stopping the app. This uses a separate database from the manual setup below.

## ⚙️ Run It Locally

Commands: **bash** (macOS/Linux/Git Bash) and **PowerShell** (Windows) where they differ.

You need **three terminals** in the end: PostgreSQL runs in Docker in the background, the backend runs in terminal 1, the frontend in terminal 2.

### 0. Prerequisites

| Tool | Version | Check |
| --- | --- | --- |
| Git | any | `git --version` |
| Python | **3.11 or newer** | `python --version` (Windows: `py -3.11 --version`) |
| Node.js | **20.19+ or 22.12+** (Vite 8 needs it; npm comes with it) | `node --version` |
| Docker Desktop | running | `docker ps` must not print an error |

On Windows, start Docker Desktop and wait until it says "Engine running" before step 2.

### 1. Clone the repository

```bash
git clone https://github.com/unhodrgn/CareerSync.git
cd CareerSync
```

Commands run from the **repo root** unless they `cd backend` / `cd frontend`.

### 2. Start PostgreSQL in Docker (port 5433)

The container listens on **5433** on your machine, so it does not collide with a PostgreSQL already installed on Windows/macOS (which usually holds 5432).

```bash
docker run -d --name careersync-db \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=careersync_db \
  -p 5433:5432 -v careersync-pgdata:/var/lib/postgresql/data postgres:16
```

```powershell
docker run -d --name careersync-db `
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=careersync_db `
  -p 5433:5432 -v careersync-pgdata:/var/lib/postgresql/data postgres:16
```

Check it is up: `docker ps` should show `careersync-db` with `0.0.0.0:5433->5432/tcp`.

You only run `docker run` once. Later (after a reboot) just start the existing container:

```bash
docker start careersync-db
```

The `careersync-pgdata` volume keeps the data when the container stops.

### 3. Create the `.env` file (repo root)

```bash
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

The file must be **`.env` in the repo root**, not in `backend/`. The backend, `alembic` and `scripts/seed.py` all read it on startup. Variables already set in the shell win over `.env`.

The defaults already match the Docker command above:

```env
DB_HOST=localhost
DB_PORT=5433
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=careersync_db

JWT_SECRET_KEY=replace_with_a_secure_random_secret
TALENT_ID_SECRET=replace_with_another_secure_random_secret

# Optional
AI_MODE=rules
LLM_API_KEY=
EMBEDDING_MODEL=intfloat/multilingual-e5-base
```

| Variable | Required | Notes |
| --- | --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | yes | Must match the Docker container. Or set one `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/careersync_db` instead |
| `JWT_SECRET_KEY` | for anything shared | Any long random string. A dev default is used if empty |
| `TALENT_ID_SECRET` | for anything shared | Another long random string: key for the anonymous IDs companies see in talent recommendation. Changing it changes those IDs. A dev default is used if missing |
| `AI_MODE` | no | `rules` (default; also when empty) or `llm`. In `rules`, CV analysis and project/other criteria use rules and keyword retrieval and no LLM is called, even with a key. Any other value stops the backend at startup |
| `LLM_API_KEY` | only with `AI_MODE=llm` | Anthropic API key. With `AI_MODE=llm` and no key the backend does not start. `ANTHROPIC_API_KEY` is not read |
| `LLM_MODEL` | no | Defaults to claude-sonnet-5-5 |
| `EMBEDDING_MODEL` | no | `intfloat/multilingual-e5-base` downloads about 1 GB on the first CV upload or evaluation. Set **`hashing-ngram-v1`** to skip the download (faster, but matches spelling, not meaning) |

> 🔒 Never commit `.env`. It is in `.gitignore`; only `.env.example` with placeholders is committed.

### 4. Backend: virtual environment and dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

**Activate the venv again in every new terminal** before running `alembic`, `uvicorn`, `pytest` or the seed script.

`sentence-transformers` pulls in PyTorch, so the first install takes a few minutes and several GB. On Linux, installing the CPU build first keeps it much smaller: `pip install torch --index-url https://download.pytorch.org/whl/cpu`, then the requirements.

### 5. Create the tables and load demo data

```bash
cd backend
alembic upgrade head
python ../scripts/seed.py
cd ..
```

PowerShell is the same (`cd backend`, `alembic upgrade head`, `python ..\scripts\seed.py`, `cd ..`).

`alembic` **must run inside `backend/`** (that is where `alembic.ini` is). Expected output ends with `Running upgrade 0010 -> 0011 ...` and then:

```
added hr@nextcode.test
added hr@cloudlab.test
added seeker@demo.test

All demo accounts use the password: demo1234
```

The seed is safe to run again; existing accounts are skipped.

### 6. Run the backend (terminal 1)

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

`uvicorn` **must also run inside `backend/`**, otherwise you get `ModuleNotFoundError: No module named 'app'`.

Check it:

- http://localhost:8000/health → `{"status":"ok"}`
- http://localhost:8000/docs → Swagger UI for every endpoint

### 7. Run the frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**. The Vite dev server forwards `/api` to `http://127.0.0.1:8000`, so start the backend first. No CORS setup is needed.

### 8. Log in with a demo account

All passwords are `demo1234`.

| Role | Email | What to try |
| --- | --- | --- |
| Company | `hr@nextcode.test` | 넥스트코드: one published backend job with criteria, one draft frontend job. Edit criteria, try a blocked one (e.g. "키 175cm 이상"), see 지원자 순위 and 인재 추천 of a job |
| Company | `hr@cloudlab.test` | 클라우드랩: one published data engineer job |
| Seeker | `seeker@demo.test` | Upload a text PDF CV in 내 이력서, confirm it, set 희망 조건, see 추천 공고, apply to a job, check 지원 현황 |

A typical demo: log in as the seeker, upload and confirm a CV, apply to the 넥스트코드 backend job; then log in as `hr@nextcode.test`, open the job in 공고 관리 and its 지원자 순위 tab to see the ranked applicant with per-criterion scores and evidence.

### 9. Run the tests

From the **repo root**, with the venv active:

```bash
pytest
```

Expected: `528 passed, 15 skipped` (the skipped tests need PostgreSQL, see `TEST_DATABASE_URL`). The 8 tests in `ai/tests/test_e5_quality.py` run only when `intfloat/multilingual-e5-base` is already in the Hugging Face cache (they never download it); without it expect `520 passed, 23 skipped`. Tests need no database, no network and no API key: they use in-memory SQLite, the hashing embedder and a fake LLM, and they ignore your `.env`. Running `pytest` inside `backend/` only runs the 203 backend tests.

To run the API tests against PostgreSQL instead, set `TEST_DATABASE_URL` (the tests drop and recreate all tables, so point it at a separate database).

Frontend type check and production build:

```bash
cd frontend
npm run build
```

### 10. After `git pull`

After every pull:

```bash
source .venv/bin/activate            # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
cd backend && alembic upgrade head && cd ..
cd frontend && npm install && cd ..
```

## 🧪 Quick Command Reference

| Task | Where | Command |
| --- | --- | --- |
| Start the database | anywhere | `docker start careersync-db` |
| Activate the venv | repo root | `source .venv/bin/activate` / `.\.venv\Scripts\Activate.ps1` |
| Install backend deps | repo root | `pip install -r backend/requirements.txt` |
| Apply migrations | `backend/` | `alembic upgrade head` |
| Load demo data | `backend/` or root | `python ../scripts/seed.py` / `python scripts/seed.py` |
| Run the backend | `backend/` | `uvicorn app.main:app --reload --port 8000` |
| Run the frontend | `frontend/` | `npm install` then `npm run dev` → http://localhost:3000 |
| Run all tests | repo root | `pytest` |
| Build the frontend | `frontend/` | `npm run build` |
| Open a SQL shell | anywhere | `docker exec -it careersync-db psql -U postgres -d careersync_db` |
| Reset the database | anywhere | `docker rm -f careersync-db` and `docker volume rm careersync-pgdata`, then step 2 and step 5 again |

## 🛠️ Troubleshooting

### `password authentication failed for user "postgres"` or `connection ... port 5432 failed`

The backend is talking to the wrong PostgreSQL. With `DB_PORT=5432` it reaches a PostgreSQL installed on your machine (with a different password) or nothing at all.

- Make sure `.env` exists **in the repo root** (not `backend/.env`) and says `DB_PORT=5433`, `DB_PASSWORD=postgres`.
- Make sure no `DB_PORT`, `DB_PASSWORD` or `DATABASE_URL` is left over in the shell, since shell variables win over `.env`. PowerShell: `Get-ChildItem Env:DB_*`, then `Remove-Item Env:DB_PORT`. bash: `env | grep DB_`, then `unset DB_PORT`.
- If you started the container with a different password, either fix `.env` or reset the database (see the command reference). Changing `POSTGRES_PASSWORD` later has no effect on an existing volume.

### `Connection refused` on port 5433

The container is not running. `docker ps -a` shows it; start it with `docker start careersync-db`. If `docker` itself errors, Docker Desktop is not started.

### `port is already allocated` when running `docker run`

Something else uses 5433. Either stop it, or publish another port (`-p 5434:5432`) and set `DB_PORT=5434` in `.env`. If the error is `name "/careersync-db" is already in use`, the container already exists: use `docker start careersync-db`.

### `No 'script_location' key found` or `Path doesn't exist: migrations`

`alembic` was run from the repo root. Run it from `backend/`: `cd backend`, then `alembic upgrade head`.

### `ModuleNotFoundError: No module named 'app'`

`uvicorn` was run from the repo root. Run it from `backend/`.

### `ModuleNotFoundError` for `dotenv`, `fitz`, `sentence_transformers`, `argon2` ... (often right after `git pull`)

Either the venv is not active (no `(.venv)` in the prompt) or new dependencies were added. Activate the venv and run `pip install -r backend/requirements.txt` again from the repo root.

### `relation "..." does not exist` or `column ... does not exist`

A migration has not been applied, usually after a pull. `cd backend`, then `alembic upgrade head`.

### PowerShell says `running scripts is disabled on this system` when activating the venv

Allow local scripts once for your user, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### The first CV upload or evaluation is very slow or fails offline

The first use downloads the `multilingual-e5-base` model (about 1 GB). Set `EMBEDDING_MODEL=hashing-ngram-v1` in `.env` and restart the backend to skip it. If the model cannot be loaded, the backend also falls back to the hashing embedder on its own.

### CV analysis or project criteria look basic

That is the rules mode (`AI_MODE=rules`, the default); extraction and judgment criteria use rules and keyword retrieval. Set `AI_MODE=llm` and an Anthropic API key (`LLM_API_KEY`) in `.env` and restart the backend for LLM-refined results; with `AI_MODE=llm` and no key the backend does not start. A wrong key shows up as an authentication error in the backend log and the evaluation is marked failed; recruiters can re-run it with 다시 분석 in 지원자 관리.

### The frontend shows network errors or "인증이 필요합니다"

- Network errors: the backend is not running on port 8000. Start it first. If it runs elsewhere, start Vite with `VITE_API_TARGET`, e.g. `VITE_API_TARGET=http://127.0.0.1:8001 npm run dev` (PowerShell: `$env:VITE_API_TARGET="http://127.0.0.1:8001"; npm run dev`).
- "인증이 필요합니다" (401): the login expired after 2 hours, or the database was reset. Log in again.

### `npm run dev` fails with a syntax or engine error

Node is too old for Vite 8. Check `node --version` and install Node 22 LTS (or 20.19+).

## 🔌 API Overview

Base URL `http://localhost:8000`. Request/response schemas as currently implemented are at **http://localhost:8000/docs**; the API in `PROJECT_DOCUMENTATION.md` §4 is the standard. All endpoints except register, login, `/health`, `GET /api/jobs` and `GET /api/jobs/{job_id}` need `Authorization: Bearer <token>`.

### Auth & users

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/auth/register` | Register as seeker or company (consents required) |
| POST | `/api/auth/login` | Log in, returns a bearer token |
| GET | `/api/users/me` | Current user (`consent_required` → show the consent screen) |
| POST | `/api/users/me/consent` | Consent again to the current consent text |
| DELETE | `/api/users/me/consent/ai` | Seeker withdraws AI-analysis consent |

### Companies

| Method | Endpoint | Description |
| --- | --- | --- |
| GET / PUT | `/api/companies/me` | Own company profile |
| GET | `/api/companies/{company_id}` | Public company profile with its running projects |
| GET / POST | `/api/companies/me/projects` | Company: list / add running projects |
| PUT / DELETE | `/api/companies/me/projects/{project_id}` | Company: replace / delete a running project |

### Jobs

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/jobs` | Create a draft job |
| GET | `/api/jobs` | Published jobs, newest first |
| GET | `/api/jobs/mine` | Own company's jobs in every status |
| GET / PATCH / DELETE | `/api/jobs/{job_id}` | Detail, edit (limited after publish), delete a draft |
| POST | `/api/jobs/{job_id}/publish` | Publish (needs a JD and a valid criteria set) |
| POST | `/api/jobs/{job_id}/close` | Close (final) |
| POST | `/api/jobs/{job_id}/analyze` | AI reads the JD and suggests criteria (not saved; blocked suggestions left out) |
| POST | `/api/jobs/{job_id}/jd-draft` | AI drafts a JD for a draft job (not saved) |

### Criteria

| Method | Endpoint | Description |
| --- | --- | --- |
| GET / PUT | `/api/jobs/{job_id}/criteria` | Read or replace the criteria set |
| POST | `/api/jobs/{job_id}/criteria/copy-from/{source_job_id}` | Copy criteria from another own job (API only; the UI does not offer it) |
| POST | `/api/criteria/check` | Guardrail check for one criterion (used live in the editor) |

### CV

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/cv` | Upload a PDF and analyze it |
| GET | `/api/cv/me` | Latest version of the seeker's CV |
| GET / PUT | `/api/cv/{profile_id}` | Read a version, or save edits as a new version (`confirm=true` to make it usable) |
| POST | `/api/cv/{profile_id}/review` | Seeker: AI self-check of a CV version (strengths, improvements) |

### Applications & evaluation

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/jobs/{job_id}/applications` | Apply with the confirmed CV; scoring starts in the background |
| GET | `/api/applications/mine` | Seeker's own applications |
| GET | `/api/jobs/{job_id}/applications` | Applicants ranked by Fit (recruiter only); filters `status`, `min_fit`, `evaluation_status` |
| GET | `/api/applications/{application_id}/evaluation` | Per-criterion score, evidence, comment |
| POST | `/api/applications/{application_id}/evaluation/retry` | Retry a failed evaluation |
| PUT | `/api/applications/{application_id}/status` | Recruiter changes the status |
| GET / PUT | `/api/preferences/me` | Seeker's job preferences and talent-pool opt-in |
| GET | `/api/recommendations/jobs` | Recommended jobs with a match band (매우 적합 / 적합 / 참고) |
| GET | `/api/jobs/{job_id}/talent` | Company: anonymous opted-in seekers for a job, ranked by Fit |
| POST | `/api/talent-offers` | Company sends an offer to an anonymous seeker |
| GET | `/api/talent-offers/sent` | Company's sent offers (contact only after accepted) |
| POST | `/api/talent-offers/{offer_id}/cancel` | Company cancels a pending offer |
| GET | `/api/talent-offers/mine` | Seeker's received offers |
| POST | `/api/talent-offers/{offer_id}/accept` · `/reject` | Seeker answers an offer |
| POST | `/api/jobs/{job_id}/roadmap` | Seeker: skills the job asks for that the CV lacks, with a learning plan |
| POST | `/api/jobs/{job_id}/interview-questions` | Seeker: interview practice questions for a job |

## 📁 Project Structure

```
CareerSync/
├── .env.example                 # Copy to .env (repo root)
├── conftest.py                  # Test-wide settings: no network, no .env, hashing embedder
├── pyproject.toml               # pytest config (run pytest from the repo root)
├── docker-compose.yml           # DB, init, backend and frontend
├── docs/
│   ├── DECISIONS.md             # Decisions and scope (source of truth)
│   ├── docker-compose.md        # Compose guide
│   ├── PROGRESS_BACKEND_AI.md   # Backend/AI progress and issue list
│   └── reference/               # Project proposal, design document and market research (PDF)
├── backend/
│   ├── alembic.ini              # Run alembic from backend/
│   ├── migrations/versions/     # 0001 … 0011
│   ├── requirements.txt         # Backend + AI + test dependencies
│   ├── app/
│   │   ├── main.py              # FastAPI app (run uvicorn from backend/)
│   │   ├── core/                # Settings (.env loading), JWT, dependencies, errors
│   │   ├── api/v1/              # auth, users, companies, jobs, criteria, cv, applications, preferences, recommendations, talent, career
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic; calls ai/ through ai_runtime
│   │   └── db/                  # Engine and session
│   └── tests/                   # API tests (SQLite in memory)
├── ai/
│   ├── llm/client.py            # LLMClient (Anthropic); None unless AI_MODE=llm
│   ├── prompts/v1/              # cv_structure, jd_analyze, jd_draft, rubric_score, roadmap, interview_questions, cv_review
│   ├── jd/                      # JD drafts for companies
│   ├── parsing/                 # PDF → text, PII masking, CV/JD structuring
│   ├── embedding/               # e5 / hashing embedders, skill dictionary
│   ├── scoring/                 # Per-criterion scorers, Fit and Pref (shared by evaluation and recommendations)
│   ├── guardrails/              # Criteria blocklist, evidence check
│   ├── career/                  # Skill gaps, roadmap, interview questions, CV self-check
│   └── tests/
├── data/
│   ├── blocklist.yaml           # Disallowed criteria with their legal basis
│   ├── interview_blocklist.yaml # Disallowed interview question topics
│   ├── learning_resources.yaml  # Verified learning resources for the roadmap
│   └── skills.yaml              # Skill dictionary, aliases and related-skill groups
├── scripts/
│   ├── seed.py                  # Demo companies, jobs, criteria and accounts
│   ├── docker_init.py           # Compose init: migrations + seed
│   └── smoke_test.py            # End-to-end check of a running app over HTTP
└── frontend/                    # React + TypeScript + Vite
    ├── vite.config.ts           # Port 3000, /api proxy to :8000
    └── src/
        ├── api/                 # Fetch client and error texts
        ├── auth/                # Login state and role guard
        ├── components/          # Layouts and shared UI (common, seeker, company)
        ├── i18n/                # UI text (ko)
        ├── pages/               # public/*, seeker/*, company/*
        ├── routes/              # Router and paths
        ├── styles/              # Design tokens and global CSS
        └── types/               # API types
```

## 🔄 Core User Flows

### Flow A: Job seeker

```
Register → Upload CV → AI analysis → Edit & confirm → Set preferences → Recommended jobs (match band)
        → Prepare for a job (skill gaps, interview questions) → Apply → Track status in 지원 현황
        → (opted in) Answer anonymous offers from companies in 받은 제안
```

### Flow B: Company

```
Register → Company profile + running projects → Create job → (optional) AI drafts the JD and suggests criteria
        → Set criteria + weights (blocked if discriminatory) → Publish
        → Applicants ranked by Fit → Per-criterion score + evidence → Recruiter updates status
        → 인재 추천: anonymous seekers ranked by Fit → Send offer → Contact after acceptance
```

## 📏 Scoring Rules

| Rule | Value |
| --- | --- |
| Criteria per job | At most 10, integer weights summing to 100 |
| Fit score | Weighted sum of per-criterion scores (0–100) |
| Weight edits after publish | Allowed, re-ranked instantly without re-calling AI |
| Seeker visibility of weights | Criterion name + category + importance (핵심 ≥ 25, 중요 ≥ 10, else 일반), no raw numbers; guests see names only (D30, D35) |
| Final score (job recommendation) | `0.5 × Fit + 0.5 × Pref`, recommend only when Fit ≥ 40 and Pref ≥ 40 |

Coefficients live in `backend/app/core/config.py`.

## 🎯 MVP Scope (plan)

**Assumptions:** IT/Software jobs only · Korean UI · 1 recruiter account = 1 company · text-based PDF CVs (≤ 5 MB, ≤ 5 pages) · synthetic demo data.

**Out of scope:** OCR, HWP/DOCX, scraping job sites, multiple recruiters per company, email notifications, interview scheduling, preference model trained from logs, admin screen, payments, mobile app.

**Targets** (demo scale, ≤ 100 seekers, ≤ 50 jobs): CRUD p95 < 500 ms · CV analysis ≤ 60 s · evaluation after applying ≤ 30 s · every criterion score has evidence · no name, email or phone sent to the LLM.

## 🔒 Legal & Ethics

- 채용절차법 제4조의3 (disallowed criteria are blocked at input)
- 개인정보 보호법 제37조의2 (consent and explanation for automated processing)
- AI 기본법

The product does not collect sensitive group attributes. A bias audit on synthetic labeled data is planned.

## 🗓️ Timeline

| Milestone | Date |
| --- | --- |
| Requirement Freeze | 2026-10-07 |
| Design Freeze | 2026-10-13 |
| Prototype Complete | 2026-10-18 |
| Coding starts | 2026-10-19 |
| Recommendation MVP | 2026-11-29 |
| Final demo | before 2026-12-13 |
