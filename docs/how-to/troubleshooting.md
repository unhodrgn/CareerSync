# Troubleshooting

Problems with the [manual setup](run-locally.md) and how to fix them. For Docker Compose, see [its guide](run-with-docker.md).

## `password authentication failed for user "postgres"` or `connection ... port 5432 failed`

The backend is talking to the wrong PostgreSQL. With `DB_PORT=5432` it reaches a PostgreSQL installed on your machine (with a different password) or nothing at all.

- Make sure `.env` exists **in the repo root** (not `backend/.env`) and says `DB_PORT=5433`, `DB_PASSWORD=postgres`.
- Make sure no `DB_PORT`, `DB_PASSWORD` or `DATABASE_URL` is left over in the shell, since shell variables win over `.env`. PowerShell: `Get-ChildItem Env:DB_*`, then `Remove-Item Env:DB_PORT`. bash: `env | grep DB_`, then `unset DB_PORT`.
- If you started the container with a different password, either fix `.env` or reset the database (see the [command reference](run-locally.md#command-reference)). Changing `POSTGRES_PASSWORD` later has no effect on an existing volume.

## `Connection refused` on port 5433

The container is not running. `docker ps -a` shows it; start it with `docker start careersync-db`. If `docker` itself errors, Docker Desktop is not started.

## `port is already allocated` when running `docker run`

Something else uses 5433. Either stop it, or publish another port (`-p 5434:5432`) and set `DB_PORT=5434` in `.env`. If the error is `name "/careersync-db" is already in use`, the container already exists: use `docker start careersync-db`.

## `No 'script_location' key found` or `Path doesn't exist: migrations`

`alembic` was run from the repo root. Run it from `backend/`: `cd backend`, then `alembic upgrade head`.

## `ModuleNotFoundError: No module named 'app'`

`uvicorn` was run from the repo root. Run it from `backend/`.

## `ModuleNotFoundError` for `dotenv`, `fitz`, `sentence_transformers`, `argon2` ... (often right after `git pull`)

Either the venv is not active (no `(.venv)` in the prompt) or new dependencies were added. Activate the venv and run `pip install -r backend/requirements.txt` again from the repo root.

## `relation "..." does not exist` or `column ... does not exist`

A migration has not been applied, usually after a pull. `cd backend`, then `alembic upgrade head`.

## PowerShell says `running scripts is disabled on this system` when activating the venv

Allow local scripts once for your user, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

## The first CV upload or evaluation is very slow or fails offline

The backend starts downloading the `multilingual-e5-base` model (about 1 GB) in the background when it first starts; a CV upload or evaluation that comes before the download has finished waits for it. Set `EMBEDDING_MODEL=hashing-ngram-v1` in `.env` and restart the backend to skip it. If the model cannot be loaded, the backend also falls back to the hashing embedder on its own. The backend logs which model scores: `Embedding model ready: …`, or a line saying the configured model is not available and which one is used instead (an error with `AI_MODE=llm`, a warning otherwise). The startup log also shows `AI_MODE` and, in llm mode, `LLM_MODEL` (never the key).

## CV analysis or project criteria look basic

That is the rules mode (`AI_MODE=rules`, the default); extraction and judgment criteria use rules and keyword retrieval. Set `AI_MODE=llm` and an Anthropic API key (`LLM_API_KEY`) in `.env` and restart the backend for LLM-refined results; with `AI_MODE=llm` and no key the backend does not start. A wrong key shows up as an authentication error in the backend log and the evaluation is marked failed; recruiters can re-run it with 다시 분석 in 지원자 관리.

## The frontend shows network errors or "인증이 필요합니다"

- Network errors: the backend is not running on port 8000. Start it first. If it runs elsewhere, start Vite with `VITE_API_TARGET`, e.g. `VITE_API_TARGET=http://127.0.0.1:8001 npm run dev` (PowerShell: `$env:VITE_API_TARGET="http://127.0.0.1:8001"; npm run dev`).
- "인증이 필요합니다" (401): the login expired after 2 hours, or the database was reset. Log in again.

## `npm run dev` fails with a syntax or engine error

Node is too old for Vite 8. Check `node --version` and install Node 22 LTS (or 20.19+ on the 20.x line).
