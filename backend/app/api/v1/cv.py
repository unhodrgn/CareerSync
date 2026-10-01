"""Seeker CV routes: upload a PDF, read the analysis, edit and confirm it."""
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from ai.parsing.pdf import MAX_BYTES
from app.core.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.schemas.cv import CvOut, CvUpdate
from app.services import cv_service

router = APIRouter(prefix="/cv", tags=["cv"])


@router.post("", response_model=CvOut, status_code=status.HTTP_201_CREATED, summary="Upload a PDF CV and analyze it")
async def upload_cv(file: Annotated[UploadFile, File(description="Text PDF, at most 5 pages and 5 MB")], db: DbSession, user: CurrentUser):
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise AppError(422, "CV_TOO_LARGE", "이력서 파일은 5MB 이하여야 합니다.")
    return cv_service.to_out(cv_service.upload(db, user, file.filename or "cv.pdf", data))


@router.get("/me", response_model=CvOut, summary="Latest version of the seeker's newest CV")
def my_cv(db: DbSession, user: CurrentUser):
    return cv_service.to_out(cv_service.latest(db, user))


@router.get("/{profile_id}", response_model=CvOut, summary="One CV profile version (own only)")
def get_cv(profile_id: int, db: DbSession, user: CurrentUser):
    return cv_service.to_out(cv_service.get_own(db, user, profile_id))


@router.put("/{profile_id}", response_model=CvOut, summary="Save edits as a new version; confirm=true makes it usable to apply")
def update_cv(profile_id: int, body: CvUpdate, db: DbSession, user: CurrentUser):
    return cv_service.to_out(cv_service.update(db, user, profile_id, body.profile, body.confirm))
