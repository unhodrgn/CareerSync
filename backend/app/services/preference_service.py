"""Seeker preferences: desired locations, employment types, role keywords, and the talent-pool opt-in.

One row per seeker (`seeker_preferences`, unique `seeker_id`) with three child tables. PUT replaces
the whole set. Pref itself is computed by `ai.scoring.pref.pref_score` (docs/DECISIONS.md D15).
"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai.scoring.pref import Preferences
from app.core.errors import AppError
from app.models import (
    SeekerJobKeyword,
    SeekerPreference,
    SeekerPreferredEmploymentType,
    SeekerPreferredLocation,
    User,
)
from app.schemas.preference import PreferenceIn, PreferenceOut


def _seeker_only(user: User) -> None:
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 사용할 수 있습니다.")


def _find(db: Session, seeker_id: int) -> SeekerPreference | None:
    return db.scalars(select(SeekerPreference).where(SeekerPreference.seeker_id == seeker_id)).first()


def to_out(pref: SeekerPreference | None) -> PreferenceOut:
    if pref is None:
        return PreferenceOut(
            locations=[], employment_types=[], job_keywords=[], profile_public=False, profile_public_at=None, updated_at=None
        )
    return PreferenceOut(
        locations=[x.location for x in pref.locations],
        employment_types=[x.employment_type for x in pref.employment_types],
        job_keywords=[x.keyword for x in pref.job_keywords],
        profile_public=pref.profile_public,
        profile_public_at=pref.profile_public_at,
        updated_at=pref.updated_at,
    )


def to_preferences(pref: SeekerPreference | None) -> Preferences:
    """Plain object for `ai.scoring.pref.pref_score`; no row means no preferences."""
    if pref is None:
        return Preferences()
    return Preferences(
        locations=tuple(x.location for x in pref.locations),
        employment_types=tuple(x.employment_type for x in pref.employment_types),
        job_keywords=tuple(x.keyword for x in pref.job_keywords),
    )


def get_mine(db: Session, user: User) -> SeekerPreference | None:
    _seeker_only(user)
    return _find(db, user.id)


def _get_or_create(db: Session, seeker_id: int) -> SeekerPreference:
    pref = _find(db, seeker_id)
    if pref is not None:
        return pref
    try:
        with db.begin_nested():
            pref = SeekerPreference(seeker_id=seeker_id)
            db.add(pref)
    except IntegrityError:
        pref = _find(db, seeker_id)  # a concurrent first PUT created it
    return pref


def replace_mine(db: Session, user: User, data: PreferenceIn) -> SeekerPreference:
    _seeker_only(user)
    pref = _get_or_create(db, user.id)
    pref.locations.clear()
    pref.employment_types.clear()
    pref.job_keywords.clear()
    db.flush()  # delete old children before inserting values that may repeat them
    pref.locations.extend(SeekerPreferredLocation(location=v) for v in data.locations)
    pref.employment_types.extend(SeekerPreferredEmploymentType(employment_type=v) for v in data.employment_types)
    pref.job_keywords.extend(SeekerJobKeyword(keyword=v) for v in data.job_keywords)
    if data.profile_public and not pref.profile_public:
        pref.profile_public_at = datetime.now(UTC)
    elif not data.profile_public:
        pref.profile_public_at = None
    pref.profile_public = data.profile_public
    pref.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(pref)
    return pref
