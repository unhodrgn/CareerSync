"""Test-wide settings: no network calls. The LLM is off and the hashing embedder is used,
so every test is deterministic; tests that need an LLM pass a fake client explicitly."""
import os

os.environ["EMBEDDING_MODEL"] = "hashing-ngram-v1"
for key in ("LLM_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(key, None)
