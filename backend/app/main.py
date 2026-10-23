"""FastAPI entrypoint."""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai.embedding.model import configured_model, get_embedder
from ai.llm.client import check_llm_config, llm_model
from app.api.v1 import applications, auth, career, companies, criteria, cv, jobs, preferences, recommendations, talent, users
from app.core.errors import AppError

# uvicorn configures only its own loggers, so INFO lines reach the console through this one
log = logging.getLogger("uvicorn.error")


def warm_up_embedder(mode: str) -> None:
    """Load the embedding model once and say which one scores. Runs off the startup path: the first e5 load can
    download about 1 GB, longer than the Compose healthcheck waits. A fallback to hashing in llm mode is an
    error in the log; the backend keeps running."""
    try:
        name, wanted = get_embedder().name, configured_model()
    except Exception:  # noqa: BLE001  (a warm-up failure must not end silently)
        log.exception("Embedding model warm-up failed")
        return
    if name == wanted:
        log.info("Embedding model ready: %s", name)
    elif mode == "llm":
        log.error("Embedding model %s is not available; scoring uses %s (AI_MODE=llm)", wanted, name)
    else:
        log.warning("Embedding model %s is not available; scoring uses %s", wanted, name)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail fast: an invalid AI_MODE, or AI_MODE=llm without a key, stops startup (no silent fallback)
    mode = check_llm_config()
    if mode == "llm":
        log.info("AI_MODE=llm, LLM_MODEL=%s", llm_model())  # never the key
    else:
        log.info("AI_MODE=rules (no LLM calls)")
    threading.Thread(target=warm_up_embedder, args=(mode,), name="embedder-warm-up", daemon=True).start()
    yield


app = FastAPI(title="CareerSync API", lifespan=lifespan)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(criteria.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(cv.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(talent.router, prefix="/api")
app.include_router(career.router, prefix="/api")


@app.exception_handler(AppError)
def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, **exc.extra})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
