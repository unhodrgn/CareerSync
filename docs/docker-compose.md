# Run the demo with Docker Compose

Install and start Docker Desktop (Linux containers). From the repository root:

```powershell
# Create .env only if it does not exist:
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# The demo embedding is intfloat/multilingual-e5-base (default; ~1 GB on the first run).
# For a quick try without the download, set EMBEDDING_MODEL=hashing-ngram-v1 in .env.
docker compose up --build -d
docker compose ps -a
```

Open http://localhost:3000. API health: http://localhost:8000/health.
Swagger: http://localhost:8000/docs.

Demo accounts: seeker@demo.test (no CV yet; upload data/demo/demo_cv.pdf),
seeker2@demo.test (demo CV confirmed, preferences set, in the talent pool),
hr@nextcode.test, hr@cloudlab.test. All demo passwords: demo1234.
The seed runs on every `docker compose up`, so an existing demo database gets
seeker2@demo.test on the next start without a reset.

The first build downloads Python/Node dependencies and can take several minutes.
Compose waits for PostgreSQL, runs Alembic and the idempotent seed script,
then starts the backend and frontend. The init container exiting with code 0 is normal.
No host Python or Node installation is needed.

Stop any locally running uvicorn/Vite processes (Ctrl+C) first: they use ports
8000 and 3000. The database uses host port 5434, so the manually created
careersync-db container on port 5433 can stay running. Compose uses a separate
database volume; existing local data is not imported.

Inside Compose, the backend always connects to db:5432. Host DB_HOST,
DB_PORT and DATABASE_URL settings do not override that internal connection.
DB_USER, DB_PASSWORD and DB_NAME are shared by the database and backend.
Changing credentials after the database volume is initialized does not change
the credentials already stored in PostgreSQL.

Optional .env variables: COMPOSE_DB_PORT (5434), COMPOSE_BACKEND_PORT (8000),
COMPOSE_FRONTEND_PORT (3000). Access the corresponding port if changed.
AI_MODE defaults to rules. AI_MODE=llm needs LLM_API_KEY, otherwise the backend
does not start; in rules mode the key is ignored.
EMBEDDING_MODEL defaults to intfloat/multilingual-e5-base (docs/DECISIONS.md D26); the
model is downloaded once into the model-cache volume and kept across restarts.

```powershell
docker compose logs --tail=100 init backend frontend
docker compose down
# Start again, preserving data:
docker compose up --build -d
```

For demo verification: log in as seeker, upload and confirm a text PDF CV,
apply to the Nextcode job, then log in as hr@nextcode.test and view applicants.
Job recommendations are real (`GET /api/recommendations/jobs`): the seeker's 추천 공고
page shows a band (매우 적합 / 적합 / 참고), never a percentage. Jobs still being
analyzed are counted as pending and appear after 새로고침.

Local dev/demo setup (Vite dev server), not production. Ports bind to localhost
only. `docker compose down -v` deletes the demo database and model cache.
