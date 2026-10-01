"""Shared FastAPI dependencies."""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    user_id = decode_access_token(credentials.credentials) if credentials else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "인증이 필요합니다.", headers={"WWW-Authenticate": "Bearer"})
    return user


def get_company_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "company":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "기업 회원만 사용할 수 있습니다.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CompanyUser = Annotated[User, Depends(get_company_user)]
