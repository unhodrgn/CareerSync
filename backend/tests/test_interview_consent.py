"""Consent to store a practice-interview transcript (M4 S2): the approved draft wording, pinned to its version, and the check.
The check is exercised in the create flow in test_interview_create.py (order, and no side effect when it fails)."""
import hashlib
import json

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.application import AI_NOTICE
from app.services import interview_consent_service as consent

# SHA-256 of the consent text (version, title, retention days and every item). Changing a word fails this test; a new wording
# needs a new `INTERVIEW_CONSENT_VERSION` and a new pin, so a stored consent always names the text that was shown.
PINNED = "8fe160e2b5c819f0c803e5ffe673e257b44653a433b37d7ca9748f0885fadbdd"


def digest(text) -> str:
    payload = {"version": text.version, "title": text.title, "retention_days": text.retention_days, "items": [[i.key, i.text] for i in text.items]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def test_the_wording_is_pinned_to_its_version():
    text = consent.current()
    assert text.version == settings.INTERVIEW_CONSENT_VERSION == "2026-11-16"
    assert digest(text) == PINNED, "the consent text changed: bump INTERVIEW_CONSENT_VERSION and re-pin"


def test_the_text_says_what_the_consent_requires():
    text = consent.current()
    items = {i.key: i.text for i in text.items}
    assert list(items) == ["processing", "purpose", "retention", "access", "deletion", "separate"]
    assert text.retention_days == settings.INTERVIEW_RETENTION_DAYS == 30
    assert "텍스트로만 저장" in items["processing"] and "음성과 영상은 저장되지 않습니다" in items["processing"]
    assert "완벽하지 않아" in items["processing"]  # masking is best effort, and the text says so
    assert "피드백 리포트" in items["purpose"]
    assert "30일" in items["retention"] and "삭제 대상" in items["retention"]
    assert "본인만" in items["access"] and "기업은" in items["access"]
    assert "직접 삭제" in items["deletion"]
    assert "AI 분석 동의와 별개" in items["separate"]


def test_the_text_does_not_promise_automatic_deletion_or_claim_approval():
    """Deletion needs a scheduler that no deployment has configured yet, and the wording is a draft."""
    everything = " ".join([consent.current().title, *(i.text for i in consent.current().items)])
    for claim in ("자동", "즉시", "법적", "승인", "인증", "보장"):
        assert claim not in everything, claim


def test_the_consent_is_separate_from_the_ai_notice():
    everything = " ".join(i.text for i in consent.current().items)
    assert AI_NOTICE not in everything and "참고용" not in everything
    assert not hasattr(consent.current(), "notice")


def test_the_retention_sentence_follows_the_setting(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_RETENTION_DAYS", 7)
    text = consent.current()
    assert text.retention_days == 7 and "7일" in {i.key: i.text for i in text.items}["retention"]
    assert digest(text) != PINNED  # a different text: it would need a new version


# ── The check ──


def test_an_explicit_consent_to_the_current_version_passes():
    consent.require(True, "2026-11-16")


@pytest.mark.parametrize("given", [None, False, "true", 1, 0, "", [], {"consent": True}])
def test_anything_but_an_explicit_true_is_refused(given):
    with pytest.raises(AppError) as error:
        consent.require(given, "2026-11-16")
    assert (error.value.status_code, error.value.code) == (409, "INTERVIEW_CONSENT_REQUIRED")
    assert error.value.extra == {"current_version": "2026-11-16"}


@pytest.mark.parametrize("version", [None, "", "2026-11-15", "2026-11-17", "2026-11-16 ", 20261116, "v1"])
def test_only_the_exact_current_version_passes(version):
    with pytest.raises(AppError) as error:
        consent.require(True, version)
    assert (error.value.status_code, error.value.code) == (409, "INTERVIEW_CONSENT_OUTDATED")
    assert error.value.extra == {"current_version": "2026-11-16"}


def test_the_missing_consent_is_reported_before_the_version():
    with pytest.raises(AppError) as error:
        consent.require(False, "an old version")
    assert error.value.code == "INTERVIEW_CONSENT_REQUIRED"


def test_the_version_comes_from_the_setting(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_CONSENT_VERSION", "2027-01-01")
    consent.require(True, "2027-01-01")
    with pytest.raises(AppError) as error:
        consent.require(True, "2026-11-16")
    assert error.value.code == "INTERVIEW_CONSENT_OUTDATED" and error.value.extra == {"current_version": "2027-01-01"}
