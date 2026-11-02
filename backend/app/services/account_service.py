"""The signed-in user's own account: changing the display name (docs/DECISIONS.md D46).

A seeker's name is locked once they have uploaded a CV: name masking (D39) used the name of that moment, and the
stored masked text would not hide a different name. The lock is "has any CV document", checked under a row lock on
the user that `cv_service.upload` takes too, so a rename and an upload cannot interleave. There is no CV deletion
(D34); if it comes, a seeker without documents has no stored masked text, so renaming is safe again. Companies are
never locked.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import CvDocument, User


def lock_user_row(db: Session, user_id: int) -> str:
    """`SELECT … FOR UPDATE` on the user (a no-op on SQLite); returns the display name as stored now."""
    return db.scalar(select(User.display_name).where(User.id == user_id).with_for_update())


def rename(db: Session, user: User, display_name: str) -> User:
    if user.role == "seeker":
        lock_user_row(db, user.id)
        if db.scalar(select(CvDocument.id).where(CvDocument.seeker_id == user.id).limit(1)) is not None:
            raise AppError(
                409,
                "NAME_LOCKED",
                "이력서를 올린 뒤에는 이름을 바꿀 수 없습니다. 이력서의 개인정보를 가릴 때 이 이름을 사용했기 때문입니다.",
            )
    user.display_name = display_name
    db.commit()
    db.refresh(user)
    return user
