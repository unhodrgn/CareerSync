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

An empty or whitespace-only value counts as unset (the default is used), except `AI_MODE` (empty = `rules`) and `LLM_API_KEY` (empty = no key).

The variables you are most likely to set are below. Every variable the code reads, with its default (also `LLM_EFFORT`, `JWT_EXPIRE_MINUTES` and the data file paths), is in [PROJECT_DOCUMENTATION.md §9](../../PROJECT_DOCUMENTATION.md#9-environment-and-configuration).

| Variable | Required | Notes |
| --- | --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | yes | Must match the Docker container. Or set one `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/careersync_db` instead |
| `JWT_SECRET_KEY` | for anything shared | Any long random string. A built-in dev value is used if it is missing or empty; while this or `TALENT_ID_SECRET` uses its dev value, the backend logs one warning at startup (names only, never values) |
| `TALENT_ID_SECRET` | for anything shared | Another long random string: key for the anonymous IDs companies see in talent recommendation. Changing it changes those IDs. A dev default is used if missing or empty |
| `AI_MODE` | no | `rules` (default; also when empty) or `llm`. In `rules`, CV analysis uses rules, `project` criteria are scored from the CV's 프로젝트 entries and `other` criteria by keyword retrieval (D28); no LLM is called, even with a key. Any other value stops the backend at startup |
| `LLM_API_KEY` | only with `AI_MODE=llm` | Anthropic API key. With `AI_MODE=llm` and no key the backend does not start. `ANTHROPIC_API_KEY` is not read |
| `LLM_MODEL` | no | Defaults to claude-sonnet-5-5 (also when empty) |
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
| Company | `hr@nextcode.test` | 넥스트코드: one published backend job with criteria, one draft frontend job. Edit criteria, try a blocked one (e.g. "키 175cm 이상"), see 지원자 순위 and 인재 추천 of a job |
| Company | `hr@cloudlab.test` | 클라우드랩: one published data engineer job |
| Seeker | `seeker@demo.test` | No CV yet. Upload the synthetic demo CV `data/demo/demo_cv.pdf` in 내 이력서, confirm it, set 희망 조건, see 추천 공고, apply to a job, check 지원 현황 |
| Seeker | `seeker2@demo.test` | Ready-made: the same demo CV uploaded and confirmed, 희망 조건 서울 · 정규직, in the talent pool. Shows 추천 공고, 취업 준비 and the CV self-check at once, and appears in 인재 추천 for the companies |

The demo CV is made up (`scripts/make_demo_cv.py` builds it). Both seekers carry the CV's name, so the name is masked before any text reaches the LLM.

A typical demo: log in as the seeker, upload and confirm a CV, apply to the 넥스트코드 backend job; then log in as `hr@nextcode.test`, open the job in 공고 관리 and its 지원자 순위 tab to see the ranked applicant with per-criterion scores and evidence.

## 9. Run the tests

From the **repo root**, with the venv active:

```bash
pytest
```

Every test must pass. Some are skipped: the PostgreSQL tests (see `TEST_DATABASE_URL`), and the tests in `ai/tests/test_e5_quality.py`, which run only when `intfloat/multilingual-e5-base` is already in the Hugging Face cache (they never download it). Tests need no database, no network and no API key: they use in-memory SQLite, the hashing embedder and a fake LLM, and they ignore your `.env`. Running `pytest` inside `backend/` runs only the backend tests (including the doc-drift guards in `backend/tests/docs/`).

To run the API tests against PostgreSQL instead, set `TEST_DATABASE_URL` (the tests drop and recreate all tables, so point it at a separate database).

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
