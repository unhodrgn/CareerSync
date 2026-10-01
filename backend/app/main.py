"""FastAPI entrypoint."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import criteria, jobs
from app.services.criteria_service import CriteriaError

app = FastAPI(title="CareerSync API")

app.include_router(criteria.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


@app.exception_handler(CriteriaError)
def _criteria_error(_: Request, exc: CriteriaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, **exc.extra})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
