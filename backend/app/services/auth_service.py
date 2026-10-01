"""Registration and login."""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.models import Company, User
from app.schemas.auth import RegisterIn


def register(db: Session, data: RegisterIn) -> User:
    """Create the user, and for a company account its company, in one transaction."""
    if db.scalar(select(User.id).where(func.lower(User.email) == data.email)) is not None:
        raise AppError(409, "EMAIL_TAKEN", "이미 가입된 이메일입니다.")
    now = datetime.now(UTC)
    company = None
    if data.role == "company":
        company = Company(name=data.company_name)
        db.add(company)
        db.flush()
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        role=data.role,
        company_id=company.id if company else None,
        consent_privacy_at=now,
        consent_ai_at=now,
        consent_version=settings.CONSENT_VERSION,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    """The user for these credentials. Unknown email and wrong password give the same error."""
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not verify_password(password, user.password_hash if user else None):
        raise AppError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")
    return user
