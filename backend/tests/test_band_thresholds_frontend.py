"""The score guide on the seeker pages states the band thresholds in words (매우 적합 80~100 · 적합 60~79 · 참고
40~59, D16). It reads them from BAND_THRESHOLDS in frontend/src/types/recommendation.ts; this keeps that constant equal
to the backend config, so the guide can never silently disagree with the bands the API sends."""
import re
from pathlib import Path

from app.core.config import settings

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "frontend" / "src" / "types" / "recommendation.ts"


def _frontend_thresholds() -> dict[str, float]:
    text = SOURCE.read_text(encoding="utf-8")
    block = re.search(r"BAND_THRESHOLDS\s*=\s*\{([^}]*)\}", text)
    assert block, f"BAND_THRESHOLDS not found in {SOURCE}"
    return {name: float(value) for name, value in re.findall(r"(\w+)\s*:\s*(\d+(?:\.\d+)?)", block.group(1))}


def test_band_thresholds_match_backend_config():
    lowest = settings.RECO_FIT_WEIGHT * settings.RECO_MIN_FIT + settings.RECO_PREF_WEIGHT * settings.RECO_MIN_PREF
    assert _frontend_thresholds() == {
        "veryGood": settings.RECO_BAND_HIGH,
        "good": settings.RECO_BAND_MID,
        "reference": lowest,
    }
