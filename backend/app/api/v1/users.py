"""Current user, display name and consent."""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.auth import ConsentIn, UserOut, UserUpdate
from app.services import account_service, consent_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut, summary="Get the current user (consent_required: show the consent screen)")
def me(user: CurrentUser):
    return user


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Change the display name (email is read-only); a seeker's name is locked after the first CV upload (D46)",
)
def update_me(body: UserUpdate, db: DbSession, user: CurrentUser):
    return account_service.rename(db, user, body.display_name)


@router.post("/me/consent", response_model=UserOut, summary="Consent (again) to the current consent text version")
def consent(body: ConsentIn, db: DbSession, user: CurrentUser):
    return consent_service.consent(db, user, body)


@router.delete(
    "/me/consent/ai",
    response_model=UserOut,
    summary="Withdraw AI-analysis consent (seeker): no new CV analysis, apply, recommendation or re-scoring",
)
def withdraw_ai_consent(db: DbSession, user: CurrentUser):
    return consent_service.withdraw_ai(db, user)
