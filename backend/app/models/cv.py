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
    profile: Mapped[dict] = mapped_column(JsonType)
    schema_version: Mapped[str] = mapped_column(String(20))
    # "rules", "llm:<model>" or "seeker" (edited by the seeker)
    method: Mapped[str] = mapped_column(String(60))
    # Only a confirmed profile can be used to apply
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[CvDocument] = relationship(back_populates="profiles")
