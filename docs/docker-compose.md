# Run the demo with Docker Compose

Install and start Docker Desktop (Linux containers). From the repository root:

```powershell
# Create .env only if it does not exist:
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# For a fast no-key demo, set EMBEDDING_MODEL=hashing-ngram-v1 in .env.
docker compose up --build -d
docker compose ps -a
```

Open http://localhost:3000. API health: http://localhost:8000/health.
Swagger: http://localhost:8000/docs.

Demo accounts: seeker@demo.test, hr@nextcode.test, hr@cloudlab.test.
All demo passwords: demo1234.

The first build downloads Python/Node dependencies and can take several minutes.
Compose waits for PostgreSQL, runs Alembic and the existing idempotent seed script,
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
LLM_API_KEY is optional; without a key the existing rule-based mode is used.
The model cache persists if you choose the e5 embedder.

```powershell
docker compose logs --tail=100 init backend frontend
docker compose down
# Start again, preserving data:
docker compose up --build -d
```

For demo verification: log in as seeker, upload and confirm a text PDF CV,
apply to the Nextcode job, then log in as hr@nextcode.test and view applicants.
Job recommendation percentages remain demo values; Compose does not implement
the recommendation API.

This is a local development/demo setup using Vite, not production hosting.
Ports bind only to localhost. Do not use docker compose down -v unless you
intend to delete this demo database and model cache.
