# Run CareerSync locally (manual setup)

PostgreSQL runs in Docker; the backend and the frontend run on your machine. For the one-command demo, use [Docker Compose](run-with-docker.md) instead. Something fails? See [Troubleshooting](troubleshooting.md).

Commands: **bash** (macOS/Linux/Git Bash) and **PowerShell** (Windows) where they differ.

You need **two terminals** in the end: the backend runs in terminal 1 and the frontend in terminal 2, while PostgreSQL runs in Docker in the background.

## 0. Prerequisites

| Tool | Version | Check |
| --- | --- | --- |
| Git | any | `git --version` |
| Python | **3.11 or newer** | `python --version` (Windows: `py -3.11 --version`) |
| Node.js | **20.19+ (20.x) or 22.12+** (Vite 8 needs it; npm comes with it) | `node --version` |
| Docker Desktop | running | `docker ps` must not print an error |

On Windows, start Docker Desktop and wait until it says "Engine running" before step 2.

## 1. Clone the repository

```bash
git clone https://github.com/unhodrgn/CareerSync.git
cd CareerSync
```

Commands run from the **repo root** unless they `cd backend` / `cd frontend`.

## 2. Start PostgreSQL in Docker (port 5433)

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

## 3. Create the `.env` file (repo root)

```bash
cp .env.example .env
```

```powershell
Copy-Item .env.example .env
```

The file must be **`.env` in the repo root**, not in `backend/`. The backend, `alembic` and `scripts/seed.py` all read it on startup. Variables already set in the shell win over `.env`.

The defaults already match the Docker command above:

```env
DB_HOST=127.0.0.1
DB_PORT=5433
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=careersync_db

JWT_SECRET_KEY=replace_with_a_secure_random_secret
TALENT_ID_SECRET=replace_with_another_secure_random_secret

# Optional
AI_MODE=llm
LLM_PROVIDER=groq
LLM_API_KEY=
EMBEDDING_MODEL=intfloat/multilingual-e5-base
```

An empty or whitespace-only value counts as unset (the default is used), except `AI_MODE` (empty = `rules`) and `LLM_API_KEY` (empty = no key, falling back to `GROQ_API_KEY` when `LLM_PROVIDER=groq`).

Use `127.0.0.1` for `DB_HOST`, not `localhost`: on Windows `localhost` resolves to `::1` first, Docker publishes PostgreSQL only on `127.0.0.1`, and the connection hangs ([troubleshooting](troubleshooting.md#the-backend-hangs-on-the-database-connection-on-windows-with-db_hostlocalhost)). The code default is still `localhost`.

The variables you are most likely to set are below. Every variable the code reads, with its default (also `LLM_EFFORT`, `JWT_EXPIRE_MINUTES` and the data file paths), is in [PROJECT_DOCUMENTATION.md §9](../../PROJECT_DOCUMENTATION.md#9-environment-and-configuration).

| Variable | Required | Notes |
| --- | --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | yes | Must match the Docker container. Or set one `DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/careersync_db` instead |
| `JWT_SECRET_KEY` | for anything shared | Any long random string. A built-in dev value is used if it is missing or empty; while this or `TALENT_ID_SECRET` uses its dev value, the backend logs one warning at startup (names only, never values) |
| `TALENT_ID_SECRET` | for anything shared | Another long random string: key for the anonymous IDs companies see in talent recommendation. Changing it changes those IDs. A dev default is used if missing or empty |
| `AI_MODE` | no | `rules` (code default when unset/empty) or `llm` (`.env.example` sets `llm` for demo, D91). In `rules`, CV analysis uses rules, `project` criteria are scored from the CV's 프로젝트 entries and `other` criteria by keyword retrieval (D28); no LLM is called, even with a key. Any other value stops the backend at startup |
| `LLM_PROVIDER` | no | `groq` (default) or `anthropic` (`DEFAULT_PROVIDER = "groq"`, D91) |
| `LLM_API_KEY` | only with `AI_MODE=llm` | API key for the active `LLM_PROVIDER` (`GROQ_API_KEY` is used as fallback when `LLM_PROVIDER=groq` and `LLM_API_KEY` is blank). With `AI_MODE=llm` and no key the backend does not start. `ANTHROPIC_API_KEY` is not read |
| `LLM_MODEL` | no | Provider default when unset/empty (`openai/gpt-oss-120b` for `groq`, `claude-sonnet-5-5` for `anthropic`) |
| `GROQ_API_KEY` | with Groq `llm` mode | Used directly by the voice `agent`, and by the backend as fallback when `LLM_PROVIDER=groq` and `LLM_API_KEY` is blank |
| `EMBEDDING_MODEL` | no | `intfloat/multilingual-e5-base` (about 1 GB) downloads in the background when the backend first starts; until it is loaded, the first CV upload or evaluation waits for it. Set **`hashing-ngram-v1`** to skip the download (faster, but matches spelling, not meaning). Empty also means e5 now; an empty value used to fall back to the hashing embedder |

> 🔒 Never commit `.env`. It is in `.gitignore`; only `.env.example` with placeholders is committed.

## 4. Backend: virtual environment and dependencies

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

## 5. Create the tables and load demo data

```bash
cd backend
alembic upgrade head
python ../scripts/seed.py
cd ..
```

PowerShell is the same (`cd backend`, `alembic upgrade head`, `python ..\scripts\seed.py`, `cd ..`).

`alembic` **must run inside `backend/`** (that is where `alembic.ini` is). On an empty database the seed then prints:

```
job   넥스트코드 · 백엔드 개발자 (Java/Spring) (published)
job   넥스트코드 · 프론트엔드 개발자 (React) (draft)
added hr@nextcode.test
job   클라우드랩 · 데이터 엔지니어 (published)
added hr@cloudlab.test
added seeker@demo.test
added seeker2@demo.test
cv    seeker2@demo.test · demo_cv.pdf (rules)
cv    seeker2@demo.test · confirmed as version 2
pref  seeker2@demo.test · 서울, 정규직, talent pool on

All demo accounts use the password: demo1234
```

The seed is safe to run again; existing accounts are skipped (`seeker2@demo.test` only gets the steps it is still missing). It never calls the LLM: it runs in `AI_MODE=rules` whatever `.env` says, so no API key is needed.

## 6. Run the backend (terminal 1)

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

`uvicorn` **must also run inside `backend/`**, otherwise you get `ModuleNotFoundError: No module named 'app'`.

Check it:

- http://localhost:8000/health → `{"status":"ok"}`
- http://localhost:8000/docs → Swagger UI for every endpoint

## 7. Run the frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**. The Vite dev server forwards `/api` to `http://127.0.0.1:8000`, so start the backend first. No CORS setup is needed.

## 8. Log in with a demo account

All passwords are `demo1234`.

| Role | Email | What to try |
| --- | --- | --- |
| Company | `hr@nextcode.test` | 넥스트코드: one published backend job with criteria, one draft frontend job. Edit criteria, try a blocked one (e.g. "키 175cm 이상", height of at least 175 cm), see 지원자 순위 (Applicant ranking) and 인재 추천 (Talent recommendation) of a job |
| Company | `hr@cloudlab.test` | 클라우드랩: one published data engineer job |
| Seeker | `seeker@demo.test` | No CV yet. Upload the synthetic demo CV `data/demo/demo_cv.pdf` in 내 이력서 (My CV), confirm it, set 희망 조건 (Preferences), see 추천 공고 (Recommended jobs), apply to a job, check 지원 현황 (My applications) |
| Seeker | `seeker2@demo.test` | Ready-made: the same demo CV uploaded and confirmed, 희망 조건 서울 · 정규직 (Seoul, full-time), in the talent pool. Shows 추천 공고, 취업 준비 (Job preparation) and the CV self-check at once, and appears in 인재 추천 for the companies |
| Seeker | `seeker3@demo.test` | Demo CV uploaded and confirmed only (no preferences, not in talent pool): dedicated second seeker account for practice interview checks |

The demo CV is made up (`scripts/make_demo_cv.py` builds it). Both seekers carry the CV's name, so the name is masked before any text reaches the LLM.

A typical demo: log in as the seeker, upload and confirm a CV, apply to the 넥스트코드 backend job; then log in as `hr@nextcode.test`, open the job in 공고 관리 (Job management) and its 지원자 순위 tab to see the ranked applicant with per-criterion scores and evidence.

## 9. Run the tests

From the **repo root**, with the venv active:

```bash
pytest
```

Every test must pass. Some are skipped: the PostgreSQL tests (see `TEST_DATABASE_URL`), and the tests in `ai/tests/test_e5_quality.py`, which run only when `intfloat/multilingual-e5-base` is already in the Hugging Face cache (they never download it). Tests need no database, no network and no API key: they use in-memory SQLite, the hashing embedder and a fake LLM, and they ignore your `.env`. Running `pytest` inside `backend/` runs only the backend tests (including the doc-drift guards in `backend/tests/docs/`).

To run the tests against PostgreSQL instead, set `TEST_DATABASE_URL`. The tests drop every application table before and after each test, so point it at a database that may be wiped, never at your working database. `backend/tests/db_safety.py` refuses a URL that is not a loopback PostgreSQL before any connection. Two modes pass it: a database whose name ends in `_pgtest`, or any other name that you approve by typing `TEST_DATABASE_EXPECTED_NAME` (the name) and `TEST_DATABASE_CONFIRM_DESTRUCTIVE` (`drop-all-tables-in:` and the name) in the same terminal, with an explicit port in the URL. Run the checker first (`python backend/tests/db_safety.py`), keep the libpq `PG*` variables and `DATABASE_URL` unset while pytest runs, and run one pytest process at a time. A test that is skipped has not run, so a PostgreSQL run counts only when no test is skipped. Afterwards the database has no application tables: rebuild it with `alembic stamp --purge base` and `alembic upgrade head` (see [PostgreSQL test database](../../PROJECT_DOCUMENTATION.md#9-environment-and-configuration) for the full steps).

The Interview Agent (`interview_agent/`, M5) has its own virtual environment and its own tests. `python scripts/run_all_tests.py -q` runs both suites, each in its own environment. Setting up the agent's environment, running its text driver and its voice worker against a local backend, the environment variables of both (the voice interview also needs a LiveKit Cloud project and, for the model mode, a Groq key) and the live checklist are in `interview_agent/README.md`. The backend and the agent need the same `INTERVIEW_AGENT_SECRET` (at least 32 characters).

Frontend type check and production build:

```bash
cd frontend
npm run build
```

## 10. After `git pull`

After every pull:

```bash
source .venv/bin/activate            # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
cd backend && alembic upgrade head && cd ..
cd frontend && npm install && cd ..
```

## Voice interview with Docker Compose

The practice interview by voice (M5) runs as the `agent` service of Compose, next to the backend. It needs a LiveKit Cloud project (URL, API key and secret) and, to use the per-turn model, a Groq key. The service is in the `voice` profile, so a plain `docker compose up` does not start it and needs none of these keys. The React interview screens come with M6; until then a small developer page in `interview_agent/devclient/` is the way in. Every new session counts against the seeker's 3 sessions a day (KST), and a session is never refunded.

1. Add to `.env` (repo root; placeholders are in `.env.example`): `INTERVIEW_AGENT_SECRET` (any random string of at least 32 characters; the backend and the agent get the same value from this one line), `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `GROQ_API_KEY` for the model mode. Without the first four the join route answers 503; the rest of the app is not affected.
2. Choose the agent's mode. `INTERVIEW_AGENT_AI_MODE` (`rules` or `llm`) sets it for the agent only; when it is unset the agent follows `AI_MODE`. Both default to `llm` (Groq) in `.env.example` / `docker-compose.yml` (D91). Shell variables win over `.env`, so override in PowerShell when running only the agent in `llm` mode and keeping backend rules:

   ```powershell
   $env:AI_MODE = "rules"                  # optional override: keep backend in rules mode
   $env:INTERVIEW_AGENT_AI_MODE = "llm"    # the agent: Groq for the per-turn analysis (needs GROQ_API_KEY)
   docker compose --profile voice up --build -d
   docker compose --profile voice ps -a    # agent: healthy once it is registered with LiveKit
   docker compose --profile voice logs -f agent
   ```

   `--profile voice` is needed on every command that should include the agent (`ps`, `logs`, `down`). The first build installs the agent's pinned packages (a few minutes). The log must show `registered worker`; a session then logs `voice session <id>: stt=… detector=turn-detector-v1 …`.
3. Start the test page in a second window, from the repo root. It uses only the standard library, so the repo's `.venv` (or any Python 3.11+) is enough; the agent's own virtual environment is not needed with Compose:

   ```powershell
   python -m interview_agent.devclient.serve        # http://127.0.0.1:8788/ in Chrome
   ```

   The page forwards `/api/` to `http://127.0.0.1:8000` (the published backend port; set `INTERVIEW_AGENT_BACKEND_URL` first if you changed `COMPOSE_BACKEND_PORT`). Log in as `seeker2@demo.test` or `seeker3@demo.test` (password `demo1234`; both have the demo CV confirmed), tick the consent, enter the job id (the 넥스트코드 (Nextcode) backend job is normally 1) and press **면접 시작** (Start interview). Allow the microphone. Press **종료** (End) to stop.
4. Stop with `docker compose --profile voice down`. Name the profile: a plain `docker compose down` names none, so it may leave the agent container (and the network it uses) behind.

To change only the agent (for example its mode or the model timeout) without touching the backend, set the variable and run `docker compose --profile voice up -d --no-deps agent`. `INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS` (default 3) is passed on the same way.

The agent container reads no `.env` file: Compose passes the variables listed above, and the service sets `INTERVIEW_AGENT_BACKEND_URL` to `http://backend:8000` (the Compose network). The agent's other settings (speech models, voice, endpointing delays, status poll) keep their defaults under Compose; the manual run in [`interview_agent/README.md`](../../interview_agent/README.md) sets them. Timing reports are written inside the container (`/app/interview_agent/.runs`) and lost when it is removed; the same numbers are in `docker compose --profile voice logs agent` (`session summary: {...}`), and `docker compose --profile voice cp agent:/app/interview_agent/.runs/. interview_agent/.runs/` copies the files out first.

The text driver needs no LiveKit or Groq key (rules mode; the shared secret is still needed). With the stack up:

```powershell
docker compose --profile voice run --rm -e INTERVIEW_DEMO_PASSWORD=demo1234 agent python -m interview_agent.text_cli --job-id 1 --email seeker2@demo.test --consent
```

If the agent container keeps restarting, `docker compose --profile voice logs agent` names the missing variable (never its value). For a LiveKit `401` or a hang on the database connection, see [troubleshooting](troubleshooting.md#livekit-answers-401-in-the-voice-interview-although-the-keys-are-right).

## Command reference

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
