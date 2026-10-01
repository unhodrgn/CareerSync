"""FastAPI entrypoint."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import auth, companies, criteria, jobs, users
from app.core.errors import AppError

app = FastAPI(title="CareerSync API")

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(criteria.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


@app.exception_handler(AppError)
def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, **exc.extra})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
