import pytest

from interview_agent.config import DEFAULT_LLM_TIMEOUT_SECONDS, ConfigError, load_settings

SECRET = "z" * 32


def test_the_defaults():
    s = load_settings({"INTERVIEW_AGENT_SECRET": SECRET})
    assert s.ai_mode == "rules" and not s.uses_model and s.llm_timeout == DEFAULT_LLM_TIMEOUT_SECONDS == 3.0
    assert s.backend_url == "http://localhost:8000" and s.llm_model == "openai/gpt-oss-120b" and s.reasoning_effort == "low"
    assert (s.data_dir / "blocklist.yaml").exists() and (s.data_dir / "interview_blocklist.yaml").exists()


@pytest.mark.parametrize(
    "env, word",
    [
        ({}, "INTERVIEW_AGENT_SECRET"),
        ({"INTERVIEW_AGENT_SECRET": "short"}, "INTERVIEW_AGENT_SECRET"),
        ({"INTERVIEW_AGENT_SECRET": SECRET, "AI_MODE": "maybe"}, "AI_MODE"),
        ({"INTERVIEW_AGENT_SECRET": SECRET, "AI_MODE": "llm"}, "GROQ_API_KEY"),
        ({"INTERVIEW_AGENT_SECRET": SECRET, "INTERVIEW_AGENT_LLM_MODEL": "claude-opus-5-5"}, "Claude"),
        ({"INTERVIEW_AGENT_SECRET": SECRET, "INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS": "abc"}, "TIMEOUT"),
        ({"INTERVIEW_AGENT_SECRET": SECRET, "INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS": "0"}, "TIMEOUT"),
        ({"INTERVIEW_AGENT_SECRET": SECRET, "INTERVIEW_AGENT_REASONING_EFFORT": "max"}, "REASONING"),
    ],
)
def test_a_missing_or_invalid_setting_is_named_without_its_value(env, word):
    with pytest.raises(ConfigError) as error:
        load_settings(env)
    assert word in str(error.value)
    for value in env.values():
        if len(value) > 6:
            assert value not in str(error.value)


def test_llm_mode_and_a_custom_timeout():
    s = load_settings(
        {
            "INTERVIEW_AGENT_SECRET": SECRET, "AI_MODE": "LLM", "GROQ_API_KEY": "gsk_x", "INTERVIEW_AGENT_LLM_TIMEOUT_SECONDS": "2.5",
            "INTERVIEW_AGENT_LLM_MODEL": "llama-3.3-70b-versatile", "INTERVIEW_AGENT_BACKEND_URL": "http://backend:8000/",
        }
    )
    assert s.uses_model and s.llm_timeout == 2.5 and s.reasoning_effort == "" and s.backend_url == "http://backend:8000"


def test_avatar_voice_settings_defaults_validation_and_secret_hiding():
    from interview_agent.config import load_voice_settings

    base = {
        "INTERVIEW_AGENT_SECRET": SECRET,
        "LIVEKIT_URL": "wss://example.livekit.cloud",
        "LIVEKIT_API_KEY": "lk_key",
        "LIVEKIT_API_SECRET": "lk_sec",
    }
    default = load_voice_settings(base)
    assert default.avatar_mode == "auto" and default.avatar_requested and not default.avatar_enabled
    assert default.avatar_join_timeout == 30.0

    secret_val = "anam_super_secret_token"
    with_keys = load_voice_settings({**base, "ANAM_API_KEY": secret_val, "ANAM_AVATAR_ID": "av_123", "INTERVIEW_AGENT_AVATAR": "ON"})
    assert with_keys.avatar_mode == "on" and with_keys.avatar_enabled
    assert secret_val not in repr(with_keys)

    disabled = load_voice_settings({**base, "ANAM_API_KEY": secret_val, "ANAM_AVATAR_ID": "av_123", "INTERVIEW_AGENT_AVATAR": "off"})
    assert not disabled.avatar_requested and not disabled.avatar_enabled

    for bad in ({"INTERVIEW_AGENT_AVATAR": "invalid"}, {"INTERVIEW_AGENT_AVATAR_JOIN_TIMEOUT_SECONDS": "2"}, {"INTERVIEW_AGENT_AVATAR_JOIN_TIMEOUT_SECONDS": "90"}):
        with pytest.raises(ConfigError):
            load_voice_settings({**base, **bad})
