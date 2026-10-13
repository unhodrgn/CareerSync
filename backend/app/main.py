"""FastAPI entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai.llm.client import check_llm_config
from app.api.v1 import applications, auth, companies, criteria, cv, jobs, preferences, recommendations, talent, users
from app.core.errors import AppError


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fail fast: an invalid AI_MODE, or AI_MODE=llm without a key, stops startup (no silent fallback)
    check_llm_config()
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


@app.exception_handler(AppError)
def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, **exc.extra})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
