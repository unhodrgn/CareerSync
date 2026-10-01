"""Users and companies. 1 recruiter account = 1 company (README assumption)."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("length(intro) <= 1000", name="ck_companies_intro_len"),
        CheckConstraint("length(talent_profile) <= 1000", name="ck_companies_talent_profile_len"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    intro: Mapped[str] = mapped_column(Text, default="", server_default="")
    # 인재상: later given to scoring as company context
    talent_profile: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('seeker', 'company')", name="ck_users_role"),
        CheckConstraint("role <> 'company' OR company_id IS NOT NULL", name="ck_users_company_has_company"),
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Shown to recruiters on applications; never sent to the LLM
    display_name: Mapped[str] = mapped_column(String(50), default="", server_default="")
    role: Mapped[str] = mapped_column(String(10))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    # Consent to personal data processing and to advisory AI analysis (개인정보 보호법 제37조의2)
    consent_privacy_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_ai_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
