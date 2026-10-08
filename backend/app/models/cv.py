"""Seeker CVs: the uploaded document (PII-masked text only) and its structured profile versions.

The original PDF is not stored. Each seeker edit creates a new profile version, so an evaluation
always points at the exact profile it scored.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class CvDocument(Base):
    __tablename__ = "cv_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    pages: Mapped[int] = mapped_column(SmallInteger)
    # Text after PII masking; the LLM and the evidence check only ever see this
    masked_text: Mapped[str] = mapped_column(Text)
    # Kinds of personal data found and masked, e.g. ["email", "phone"]
    masked_kinds: Mapped[list] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profiles: Mapped[list["CvProfile"]] = relationship(
        back_populates="document", order_by="CvProfile.version", cascade="all, delete-orphan"
    )


class CvProfile(Base):
    __tablename__ = "cv_profiles"
    __table_args__ = (UniqueConstraint("cv_document_id", "version", name="uq_cv_profiles_document_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_document_id: Mapped[int] = mapped_column(ForeignKey("cv_documents.id", ondelete="CASCADE"), index=True)
    seeker_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(20))
    # "rules", "llm:<model>" or "seeker" (edited by the seeker)
    method: Mapped[str] = mapped_column(String(60))
    # Only a confirmed profile can be used to apply
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    summary: Mapped[str] = mapped_column(Text, default="")

    document: Mapped[CvDocument] = relationship(back_populates="profiles")

    skills: Mapped[list["CvSkill"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="CvSkill.id"
    )
    experiences: Mapped[list["CvExperience"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="CvExperience.id"
    )
    projects: Mapped[list["CvProject"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="CvProject.id"
    )
    educations: Mapped[list["CvEducation"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="CvEducation.id"
    )
    certificates: Mapped[list["CvCertificate"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="CvCertificate.id"
    )


class CvSkill(Base):
    __tablename__ = "cv_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_profile_id: Mapped[int] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True
    )
    skill_name: Mapped[str] = mapped_column(String(100))

    profile: Mapped["CvProfile"] = relationship(back_populates="skills")


class CvExperience(Base):
    __tablename__ = "cv_experiences"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_profile_id: Mapped[int] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True
    )
    org: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(100), default="")
    start: Mapped[str | None] = mapped_column(String(7), nullable=True)
    end: Mapped[str | None] = mapped_column(String(7), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(500), default="")

    profile: Mapped["CvProfile"] = relationship(back_populates="experiences")


class CvProject(Base):
    __tablename__ = "cv_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_profile_id: Mapped[int] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(500), default="")

    profile: Mapped["CvProfile"] = relationship(back_populates="projects")
    techs: Mapped[list["CvProjectTech"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="CvProjectTech.id"
    )


class CvProjectTech(Base):
    __tablename__ = "cv_project_techs"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_project_id: Mapped[int] = mapped_column(
        ForeignKey("cv_projects.id", ondelete="CASCADE"), index=True
    )
    tech_name: Mapped[str] = mapped_column(String(100))

    project: Mapped["CvProject"] = relationship(back_populates="techs")


class CvEducation(Base):
    __tablename__ = "cv_educations"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_profile_id: Mapped[int] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True
    )
    school: Mapped[str] = mapped_column(String(100), default="")
    major: Mapped[str] = mapped_column(String(100), default="")
    degree: Mapped[str] = mapped_column(String(20), default="")
    source: Mapped[str] = mapped_column(String(500), default="")

    profile: Mapped["CvProfile"] = relationship(back_populates="educations")


class CvCertificate(Base):
    __tablename__ = "cv_certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_profile_id: Mapped[int] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="")
    date: Mapped[str | None] = mapped_column(String(7), nullable=True)
    source: Mapped[str] = mapped_column(String(500), default="")

    profile: Mapped["CvProfile"] = relationship(back_populates="certificates")