"""Text normalization applied before blocklist matching."""
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC (full-width → half-width, compatibility jamo), lowercase, collapse whitespace.

    Spaces are kept on purpose: matching on a space-stripped form joins neighbouring words
    and causes false blocks (e.g. "통신 장비" → "통신장비" contains "신장").
    Patterns that must survive spacing tricks use \\s* themselves.
    """
    return _WS.sub(" ", unicodedata.normalize("NFKC", text)).strip().lower()
