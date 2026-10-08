"""Seeker CV upload, analysis, review and confirmation.

Flow: PDF → text → PII masking → structuring (LLM or rules) → seeker edits and confirms.
Only a confirmed profile can be used to apply. Every edit is a new profile version.
"""
import hashlib
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.parsing.extract import normalize_profile, structure_cv, total_experience_months
from ai.parsing.pdf import PdfError, extract_text
from ai.parsing.pii import mask_pii
from ai.parsing.profile import CV_SCHEMA_VERSION, CvProfile as ProfileData
from app.core.errors import AppError
from app.models import (
    CvCertificate,
    CvDocument,
    CvEducation,
    CvExperience,
    CvProfile,
    CvProject,
    CvProjectTech,
    CvSkill,
    User,
)
from app.schemas.cv import CvOut
from app.services import ai_runtime


def _seeker_only(user: User) -> None:
    if user.role != "seeker":
        raise AppError(403, "SEEKER_ONLY", "구직자 회원만 사용할 수 있습니다.")


def _not_found() -> AppError:
    return AppError(404, "CV_NOT_FOUND", "이력서를 찾을 수 없습니다.")


def _fill_relational_profile(row: CvProfile, data: ProfileData) -> None:
    row.summary = data.summary

    row.skills = [
        CvSkill(skill_name=skill)
        for skill in data.skills
    ]

    row.experiences = [
        CvExperience(
            org=item.org,
            role=item.role,
            start=item.start,
            end=item.end,
            description=item.description,
            source=item.source,
        )
        for item in data.experiences
    ]

    row.projects = [
        CvProject(
            name=item.name,
            role=item.role,
            description=item.description,
            source=item.source,
            techs=[
                CvProjectTech(tech_name=tech)
                for tech in item.tech
            ],
        )
        for item in data.projects
    ]

    row.educations = [
        CvEducation(
            school=item.school,
            major=item.major,
            degree=item.degree,
            source=item.source,
        )
        for item in data.education
    ]

    row.certificates = [
        CvCertificate(
            name=item.name,
            date=item.date,
            source=item.source,
        )
        for item in data.certificates
    ]


def to_profile_data(row: CvProfile) -> ProfileData:
    return ProfileData(
        skills=[item.skill_name for item in row.skills],
        experiences=[
            {
                "org": item.org,
                "role": item.role,
                "start": item.start,
                "end": item.end,
                "description": item.description,
                "source": item.source,
            }
            for item in row.experiences
        ],
        projects=[
            {
                "name": item.name,
                "role": item.role,
                "tech": [tech.tech_name for tech in item.techs],
                "description": item.description,
                "source": item.source,
            }
            for item in row.projects
        ],
        education=[
            {
                "school": item.school,
                "major": item.major,
                "degree": item.degree,
                "source": item.source,
            }
            for item in row.educations
        ],
        certificates=[
            {
                "name": item.name,
                "date": item.date,
                "source": item.source,
            }
            for item in row.certificates
        ],
        summary=row.summary,
    )


def to_out(p: CvProfile) -> CvOut:
    data = to_profile_data(p)
    return CvOut(
        id=p.id,
        document_id=p.cv_document_id,
        file_name=p.document.file_name,
        pages=p.document.pages,
        version=p.version,
        profile=data,
        method=p.method,
        confirmed=p.confirmed_at is not None,
        confirmed_at=p.confirmed_at,
        masked_kinds=list(p.document.masked_kinds or []),
        total_experience_months=total_experience_months(data.experiences, date.today().strftime("%Y-%m")),
        created_at=p.created_at,
    )


def upload(db: Session, user: User, file_name: str, data: bytes) -> CvProfile:
    _seeker_only(user)
    try:
        pdf = extract_text(data)
    except PdfError as e:
        raise AppError(422, e.code, e.message) from e
    masked = mask_pii(pdf.text, [user.display_name] if user.display_name else [])
    profile, method = structure_cv(masked.text, ai_runtime.skills(), ai_runtime.llm())
    doc = CvDocument(
        seeker_id=user.id,
        file_name=file_name[:255] or "cv.pdf",
        sha256=hashlib.sha256(data).hexdigest(),
        pages=pdf.pages,
        masked_text=masked.text,
        masked_kinds=list(masked.masked),
    )
    new_profile = CvProfile(
        seeker_id=user.id,
        version=1,
        schema_version=CV_SCHEMA_VERSION,
        method=method,
    )

    _fill_relational_profile(new_profile, profile)

    doc.profiles.append(new_profile)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc.profiles[-1]


def latest(db: Session, user: User) -> CvProfile:
    """The newest profile version of the seeker's newest CV."""
    _seeker_only(user)
    p = db.scalars(
        select(CvProfile)
        .where(CvProfile.seeker_id == user.id)
        .order_by(CvProfile.cv_document_id.desc(), CvProfile.version.desc())
        .limit(1)
    ).first()
    if p is None:
        raise _not_found()
    return p


def latest_confirmed(db: Session, user: User) -> CvProfile | None:
    p = latest(db, user)
    return p if p.confirmed_at is not None else None


def get_own(db: Session, user: User, profile_id: int) -> CvProfile:
    _seeker_only(user)
    p = db.get(CvProfile, profile_id)
    if p is None or p.seeker_id != user.id:
        raise _not_found()
    return p


def update(db: Session, user: User, profile_id: int, data: ProfileData, confirm: bool) -> CvProfile:
    """Save the seeker's edits as a new version of the same document."""
    current = get_own(db, user, profile_id)
    newest = max(p.version for p in current.document.profiles)
    cleaned = normalize_profile(data, ai_runtime.skills())
    p = CvProfile(
        cv_document_id=current.cv_document_id,
        seeker_id=user.id,
        version=newest + 1,
        schema_version=CV_SCHEMA_VERSION,
        method="seeker",
        confirmed_at=datetime.now(UTC) if confirm else None,
    )

    _fill_relational_profile(p, cleaned)

    db.add(p)
    db.commit()
    db.refresh(p)
    return p
