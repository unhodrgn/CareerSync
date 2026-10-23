"""EMBEDDING_MODEL: unset, empty or whitespace only means the default (e5), like Compose's `${EMBEDDING_MODEL:-…}`.
Only the configured name is read here; no model is loaded."""
import pytest

from ai.embedding.model import DEFAULT_MODEL, HashingEmbedder, configured_model


@pytest.mark.parametrize("blank", [None, "", "  \t "], ids=["missing", "empty", "whitespace"])
def test_unset_or_blank_means_the_default(monkeypatch, blank):
    if blank is None:
        monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    else:
        monkeypatch.setenv("EMBEDDING_MODEL", blank)
    assert configured_model() == DEFAULT_MODEL


def test_a_set_value_is_used(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", HashingEmbedder.name)
    assert configured_model() == HashingEmbedder.name
