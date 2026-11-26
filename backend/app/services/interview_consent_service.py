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

TITLE = "Consent to storing practice interview transcripts"


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
                "What you say in a practice interview is transcribed and stored only as text with personal data masked. "
                "Masking is not perfect, so some personal data may remain. Audio and video are not stored.",
            ),
            ConsentItem("purpose", "The transcript is stored to create a feedback report after the interview and to let you review it later."),
            ConsentItem(
                "retention",
                f"Transcripts are kept for {days} days from the day the practice interview is created. After {days} days a record can no longer be viewed and becomes subject to deletion.",
            ),
            ConsentItem("access", "Only you can see it. Companies cannot see your interview or its feedback."),
            ConsentItem("deletion", "You can delete it yourself at any time."),
            ConsentItem("separate", "This consent is separate from AI analysis consent and is asked each time you start an interview."),
        ),
    )


def require(consent_transcript: object, consent_version: object) -> None:
    """Pass only for an explicit `True` and exactly the current version; raise 409 otherwise. The consent is checked before
    the version, so a client that did not consent is told so whatever version it sent."""
    if consent_transcript is not True:
        raise AppError(409, "INTERVIEW_CONSENT_REQUIRED", "Please consent to storing the practice interview transcript.", current_version=settings.INTERVIEW_CONSENT_VERSION)
    if consent_version != settings.INTERVIEW_CONSENT_VERSION:
        raise AppError(
            409,
            "INTERVIEW_CONSENT_OUTDATED",
            "The consent text has changed. Refresh and review the latest version.",
            current_version=settings.INTERVIEW_CONSENT_VERSION,
        )
