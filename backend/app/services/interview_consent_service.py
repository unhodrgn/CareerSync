"""Consent to store the transcript of a practice interview (docs/DECISIONS.md D53; Q36).

One consent per session, given when the session is created: `require` checks it, and the session stores its version and
time. It is separate from the global AI-analysis consent (`users.consent_*`, D17) and from `AI_NOTICE`: it covers
storing the masked transcript, not the use of AI. Nothing of the interview is read or processed before it passes
(`interview_service.create_session` calls `require` before it touches the criteria, the CV or a model).

The wording below is an implementation draft that Long approved as such. It is not a legal approval, and the processors that
see the text (Q35) are not named in it. A change of the text needs a new `INTERVIEW_CONSENT_VERSION`; a test pins both.
The retention sentence says the record "becomes subject to deletion": it does not promise a deletion that only a scheduled
`scripts/purge_interviews.py` run (or the lazy purge) carries out.
"""
from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import AppError

TITLE = "모의 면접 대화 내용 저장 동의"


@dataclass(frozen=True)
class ConsentItem:
    key: str
    text: str


@dataclass(frozen=True)
class ConsentText:
    version: str
    title: str
    retention_days: int
    items: tuple[ConsentItem, ...]


def current() -> ConsentText:
    days = settings.INTERVIEW_RETENTION_DAYS
    return ConsentText(
        version=settings.INTERVIEW_CONSENT_VERSION,
        title=TITLE,
        retention_days=days,
        items=(
            ConsentItem(
                "processing",
                "모의 면접에서 말씀하신 내용은 글로 바뀌어, 개인정보를 가린 텍스트로만 저장됩니다. "
                "가리는 처리는 완벽하지 않아 일부 개인정보가 남을 수 있습니다. 음성과 영상은 저장되지 않습니다.",
            ),
            ConsentItem("purpose", "저장 목적은 면접 후 피드백 리포트를 만들고 다시 볼 수 있게 하는 것입니다."),
            ConsentItem(
                "retention",
                f"보관 기간은 모의 면접을 만든 날부터 {days}일입니다. {days}일이 지난 기록은 열람할 수 없으며 삭제 대상이 됩니다.",
            ),
            ConsentItem("access", "본인만 볼 수 있습니다. 기업은 면접 내용과 피드백을 볼 수 없습니다."),
            ConsentItem("deletion", "언제든지 직접 삭제할 수 있습니다."),
            ConsentItem("separate", "이 동의는 AI 분석 동의와 별개이며, 면접을 시작할 때마다 확인합니다."),
        ),
    )


def require(consent_transcript: object, consent_version: object) -> None:
    """Pass only for an explicit `True` and exactly the current version; raise 409 otherwise. The consent is checked before
    the version, so a client that did not consent is told so whatever version it sent."""
    if consent_transcript is not True:
        raise AppError(409, "INTERVIEW_CONSENT_REQUIRED", "모의 면접 대화 내용 저장에 동의해 주세요.", current_version=settings.INTERVIEW_CONSENT_VERSION)
    if consent_version != settings.INTERVIEW_CONSENT_VERSION:
        raise AppError(
            409,
            "INTERVIEW_CONSENT_OUTDATED",
            "동의 문구가 변경되었습니다. 새로고침 후 최신 내용을 확인해 주세요.",
            current_version=settings.INTERVIEW_CONSENT_VERSION,
        )
