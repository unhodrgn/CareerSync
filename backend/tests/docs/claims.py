"""Numbers the docs quote in prose, each tied to the code value it quotes. A claim is searched in every guarded doc: it
must be found at least once, and every match must carry the code's values. Rewording a sentence a claim watches
fails the guard on purpose: update the pattern here (or the doc back)."""
from collections.abc import Callable
from dataclasses import dataclass

from ai.parsing import pdf
from app.core.config import settings as s


@dataclass(frozen=True)
class Claim:
    id: str
    pattern: str  # one group per quoted number
    values: Callable[[], tuple]
    source: str  # where the values live, for the failure message


def _bands() -> tuple:
    lowest = s.RECO_FIT_WEIGHT * s.RECO_MIN_FIT + s.RECO_PREF_WEIGHT * s.RECO_MIN_PREF
    return (s.RECO_BAND_HIGH, s.RECO_BAND_MID, s.RECO_BAND_HIGH - 1, lowest, s.RECO_BAND_MID - 1)


CONFIG = "backend/app/core/config.py"
CLAIMS = (
    Claim(
        "criteria-limits",
        r"(?:[Aa]t most|max) (\d+), integer weights summing to (\d+)",
        lambda: (s.CRITERIA_MAX_ITEMS, s.CRITERIA_WEIGHT_TOTAL),
        f"{CONFIG} CRITERIA_MAX_ITEMS, CRITERIA_WEIGHT_TOTAL",
    ),
    Claim(
        "reco-final",
        r"(\d+(?:\.\d+)?)\s*[×·]\s*Fit\s*\+\s*(\d+(?:\.\d+)?)\s*[×·]\s*Pref",
        lambda: (s.RECO_FIT_WEIGHT, s.RECO_PREF_WEIGHT),
        f"{CONFIG} RECO_FIT_WEIGHT, RECO_PREF_WEIGHT",
    ),
    Claim(
        "reco-thresholds",
        r"Fit ≥ (\d+)\s*(?:\*\*)?(?:and|và)(?:\*\*)?\s*Pref ≥ (\d+)",
        lambda: (s.RECO_MIN_FIT, s.RECO_MIN_PREF),
        f"{CONFIG} RECO_MIN_FIT, RECO_MIN_PREF",
    ),
    Claim("talent-thresholds", r"Pref ≥ (\d+), Fit ≥ (\d+)", lambda: (s.RECO_MIN_PREF, s.RECO_MIN_FIT), f"{CONFIG} RECO_MIN_PREF, RECO_MIN_FIT"),
    Claim("importance", r"핵심 ≥ (\d+), 중요 ≥ (\d+)", lambda: (s.IMPORTANCE_HIGH, s.IMPORTANCE_MID), f"{CONFIG} IMPORTANCE_HIGH, IMPORTANCE_MID"),
    Claim(
        "match-bands",
        r"매우 적합(?:\*\*)? (?:Final )?≥ (\d+) · (?:\*\*)?적합(?:\*\*)? (\d+)–(\d+) · (?:\*\*)?참고(?:\*\*)? (\d+)–(\d+)",
        _bands,
        f"{CONFIG} RECO_BAND_HIGH, RECO_BAND_MID; the lowest Final from RECO_*_WEIGHT and RECO_MIN_*",
    ),
    Claim("match-bands-short", r"Final ≥ (\d+) / (\d+)–(\d+) / (\d+)–(\d+)", _bands, f"{CONFIG} RECO_BAND_HIGH, RECO_BAND_MID"),
    Claim("token-hours", r"(\d+) h access token", lambda: (s.JWT_EXPIRE_MINUTES / 60,), f"{CONFIG} JWT_EXPIRE_MINUTES"),
    Claim("token-expired-hours", r"expired after (\d+) hours", lambda: (s.JWT_EXPIRE_MINUTES / 60,), f"{CONFIG} JWT_EXPIRE_MINUTES"),
    Claim(
        "pdf-pages-mb",
        r"≤ (\d+) pages, ≤ (\d+) MB",
        lambda: (pdf.MAX_PAGES, pdf.MAX_BYTES / 1024 / 1024),
        "ai/parsing/pdf.py MAX_PAGES, MAX_BYTES",
    ),
    Claim(
        "pdf-mb-pages",
        r"≤ (\d+) MB, ≤ (\d+) pages",
        lambda: (pdf.MAX_BYTES / 1024 / 1024, pdf.MAX_PAGES),
        "ai/parsing/pdf.py MAX_BYTES, MAX_PAGES",
    ),
    Claim(
        "reco-caps-d16",
        r"at most \*\*(\d+)\*\* evaluations queued per call.*?\*\*(\d+)\*\*/seeker/day.*?at most \*\*(\d+)\*\* times",
        lambda: (s.RECO_MAX_NEW_EVALUATIONS, s.RECO_DAILY_NEW_EVALUATIONS, s.EVALUATION_MAX_ATTEMPTS),
        f"{CONFIG} RECO_MAX_NEW_EVALUATIONS, RECO_DAILY_NEW_EVALUATIONS, EVALUATION_MAX_ATTEMPTS",
    ),
    Claim(
        "talent-caps-d19",
        r"(\d+) queued per call \(always\), (\d+)/company/day",
        lambda: (s.TALENT_MAX_NEW_EVALUATIONS, s.TALENT_DAILY_NEW_EVALUATIONS),
        f"{CONFIG} TALENT_MAX_NEW_EVALUATIONS, TALENT_DAILY_NEW_EVALUATIONS",
    ),
    Claim("offer-limit-d20", r"At most (\d+) offers/company/day", lambda: (s.OFFER_DAILY_LIMIT,), f"{CONFIG} OFFER_DAILY_LIMIT"),
    Claim("offer-expiry-d20", r"expires after (\d+) days", lambda: (s.OFFER_EXPIRY_DAYS,), f"{CONFIG} OFFER_EXPIRY_DAYS"),
    Claim("jd-drafts-d24", r"\*\*(\d+) LLM drafts/company/day KST\*\*", lambda: (s.JD_DAILY_LLM_DRAFTS,), f"{CONFIG} JD_DAILY_LLM_DRAFTS"),
)
