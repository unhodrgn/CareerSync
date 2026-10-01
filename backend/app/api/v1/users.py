"""Current user."""
from fastapi import APIRouter

from app.core.deps import CurrentUser
from app.schemas.auth import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut, summary="Get the current user")
def me(user: CurrentUser):
    return user
