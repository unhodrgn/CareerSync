"""Registration and login."""
from fastapi import APIRouter, status

from app.core.config import settings
from app.core.deps import DbSession
from app.core.security import create_access_token
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Register as seeker or company")
def register(body: RegisterIn, db: DbSession):
    return auth_service.register(db, body)


@router.post("/login", response_model=TokenOut, summary="Log in; returns a bearer access token")
def login(body: LoginIn, db: DbSession):
    user = auth_service.authenticate(db, body.email, body.password)
    return TokenOut(access_token=create_access_token(user.id), expires_in=settings.JWT_EXPIRE_MINUTES * 60)
