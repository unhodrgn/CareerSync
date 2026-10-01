import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL.match(v):
        raise ValueError("올바른 이메일 형식이 아닙니다.")
    return v


class RegisterIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["seeker", "company"]
    display_name: str = Field(min_length=1, max_length=50)
    company_name: str | None = Field(None, max_length=100, description="Required when role is company")
    consent_privacy: bool = Field(description="Consent to personal data processing; must be true")
    consent_ai: bool = Field(description="Acknowledges AI analysis is advisory only; must be true")

    _email = field_validator("email")(_clean_email)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("비밀번호는 영문과 숫자를 모두 포함해야 합니다.")
        return v

    @field_validator("display_name", "company_name")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

    @model_validator(mode="after")
    def _rules(self) -> "RegisterIn":
        if not (self.consent_privacy and self.consent_ai):
            raise ValueError("개인정보 처리 및 AI 분석 안내에 모두 동의해야 가입할 수 있습니다.")
        if self.role == "company" and not self.company_name:
            raise ValueError("기업 회원은 회사명을 입력해야 합니다.")
        if self.role == "seeker":
            self.company_name = None
        return self


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: Literal["seeker", "company"]
    display_name: str
    company_id: int | None
    consent_version: str | None
    created_at: datetime
