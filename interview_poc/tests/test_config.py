"""Settings: names of missing variables are reported, values never, and only this folder's .env is ever loaded."""
import re
from pathlib import Path

import pytest

import config
from config import ConfigError, load_settings

FULL = {
    "LIVEKIT_URL": "wss://example.livekit.cloud",
    "LIVEKIT_API_KEY": "key-value-1",
    "LIVEKIT_API_SECRET": "secret-value-1",
    "ANAM_API_KEY": "anam-value-1",
    "ANAM_AVATAR_ID": "avatar-id-1",
    "GROQ_API_KEY": "llm-value-1",
    "AI_MODE": "llm",
}


def test_full_agent_settings_load_with_defaults():
    s = load_settings(FULL)
    assert s.llm_model == "openai/gpt-oss-120b"  # the Groq model of the PoC, never switched silently
    assert s.reasoning_effort == "low" and s.groq_api_key == "llm-value-1"
    assert s.avatar_enabled is True and s.mask_names == ()


def test_missing_names_are_listed_without_values():
    env = {**FULL, "GROQ_API_KEY": "  ", "ANAM_API_KEY": ""}
    with pytest.raises(ConfigError) as e:
        load_settings(env)
    message = str(e.value)
    assert "GROQ_API_KEY" in message and "ANAM_API_KEY" in message
    assert not any(v in message for v in FULL.values())


def test_the_old_llm_api_key_is_not_a_substitute_for_groq_api_key():
    env = {k: v for k, v in FULL.items() if k != "GROQ_API_KEY"} | {"LLM_API_KEY": "old-anthropic-value"}
    with pytest.raises(ConfigError, match="GROQ_API_KEY") as e:
        load_settings(env)
    assert "old-anthropic-value" not in str(e.value)


def test_reasoning_effort_is_sent_by_default_only_to_gpt_oss_models():
    assert load_settings({**FULL, "LLM_MODEL": "openai/gpt-oss-20b"}).reasoning_effort == "low"
    assert load_settings({**FULL, "LLM_MODEL": "llama-3.3-70b-versatile"}).reasoning_effort == ""  # a model without reasoning rejects the field
    assert load_settings({**FULL, "POC_LLM_REASONING_EFFORT": " High "}).reasoning_effort == "high"  # explicit and case-insensitive


def test_an_anthropic_model_name_is_refused_for_the_llm_roles_and_never_echoed():
    with pytest.raises(ConfigError, match="Groq only") as e:
        load_settings({**FULL, "LLM_MODEL": "claude-sonnet-5-5"})  # e.g. a stale value in an old .env
    assert "claude-sonnet" not in str(e.value)
    with pytest.raises(ConfigError, match="Groq only"):
        load_settings({"GROQ_API_KEY": "x", "AI_MODE": "llm", "LLM_MODEL": "Claude-Opus"}, role="llm")
    token_env = {k: FULL[k] for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")} | {"LLM_MODEL": "claude-sonnet-5-5"}
    assert load_settings(token_env, role="token").livekit_url  # the token server needs no LLM, so a stale LLM_MODEL does not stop it


def test_the_llm_needs_ai_mode_llm_even_with_a_key():
    for mode in (None, "", "rules", "true"):
        env = {k: v for k, v in FULL.items() if k != "AI_MODE"} | ({"AI_MODE": mode} if mode is not None else {})
        with pytest.raises(ConfigError, match="AI_MODE=llm"):
            load_settings(env)
    assert load_settings({**FULL, "AI_MODE": " LLM "}).llm_model  # case-insensitive, like docs/DECISIONS.md D12


def test_avatar_off_does_not_need_anam_keys():
    env = {k: v for k, v in FULL.items() if not k.startswith("ANAM")} | {"POC_AVATAR": "off"}
    assert load_settings(env).avatar_enabled is False


def test_token_and_llm_roles_need_only_their_own_keys():
    assert load_settings({k: FULL[k] for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")}, role="token").livekit_url
    assert load_settings({"GROQ_API_KEY": "x", "AI_MODE": "llm"}, role="llm").groq_api_key == "x"
    with pytest.raises(ConfigError, match="AI_MODE=llm"):
        load_settings({"GROQ_API_KEY": "x"}, role="llm")


@pytest.mark.parametrize("var, value", [("POC_AVATAR", "maybe"), ("POC_LLM_REASONING_EFFORT", "max")])
def test_invalid_options_are_rejected(var, value):
    with pytest.raises(ConfigError, match=var):
        load_settings({**FULL, var: value})


def test_mask_names_are_split():
    assert load_settings({**FULL, "POC_MASK_NAMES": " 김철수, Alex ,,"}).mask_names == ("김철수", "Alex")


def test_secrets_are_hidden_from_repr():
    text = repr(load_settings(FULL))
    assert not any(v in text for v in ("key-value-1", "secret-value-1", "anam-value-1", "llm-value-1"))  # llm-value-1 is the Groq key


def test_only_this_folders_env_file_is_ever_loaded():
    assert config.ENV_FILE == Path(config.__file__).resolve().parent / ".env"
    source = Path(config.__file__).read_text(encoding="utf-8")
    assert not re.search(r"load_dotenv\(\s*\)", source), "load_dotenv() without a path searches parent folders (the repo-root .env)"
    assert "find_dotenv" not in source
