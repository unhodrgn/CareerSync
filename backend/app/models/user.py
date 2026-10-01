"""Users and companies.

Minimal stub: only the columns the criteria feature needs (role + company ownership).
The auth/profile work extends these tables.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('seeker', 'company')", name="ck_users_role"),
        CheckConstraint("role <> 'company' OR company_id IS NOT NULL", name="ck_users_company_has_company"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(10))
    # 1 recruiter account = 1 company (README assumption)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
