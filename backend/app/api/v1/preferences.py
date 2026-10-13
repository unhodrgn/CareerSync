"""Seeker preferences (input for Pref) and the talent-pool opt-in."""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.preference import PreferenceIn, PreferenceOut
from app.services import preference_service as svc

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("/me", response_model=PreferenceOut, summary="The seeker's preferences (empty when never saved)")
def get_my_preferences(db: DbSession, user: CurrentUser):
    return svc.to_out(svc.get_mine(db, user))


@router.put("/me", response_model=PreferenceOut, summary="Replace the seeker's preferences and talent-pool opt-in")
def put_my_preferences(body: PreferenceIn, db: DbSession, user: CurrentUser):
    return svc.to_out(svc.replace_mine(db, user, body))
