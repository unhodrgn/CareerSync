"""The Compose side of the voice interview (M5 S5; docs/DECISIONS.md D52, D56, D80): the optional `agent` service is wired to the backend
over the Compose network and gets only what it needs, the backend image keeps its OCR packages, and the agent image installs its pinned
lock and checks its local models at build time. Static checks of docker-compose.yml, the two Dockerfiles and .dockerignore: they cannot
build an image, so a first `docker compose --profile voice build` is still the real test."""
import pytest
import yaml

from .markdown import ROOT

SHARED = ("INTERVIEW_AGENT_SECRET", "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
NO_DEFAULT_VALUES = (*SHARED, "GROQ_API_KEY", "ANAM_API_KEY", "ANAM_AVATAR_ID")  # keys and secrets: Compose may pass them on, the file never carries a value


def compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def agent() -> dict:
    return compose()["services"]["agent"]


def backend_env() -> dict:
    return compose()["services"]["backend"]["environment"]


def test_agent_is_optional_and_built_from_the_repo_root():
    service = agent()
    assert service["profiles"] == ["voice"]  # a plain `docker compose up` needs no LiveKit keys
    assert service["build"] == {"context": ".", "dockerfile": "interview_agent/Dockerfile"}  # it imports ai/ and reads data/
    assert "ports" not in service  # it dials out to LiveKit; nothing connects in
    assert "volumes" not in service  # no model-cache mount: it would hide what the image downloaded at build time


def test_agent_reaches_the_backend_over_the_compose_network():
    data = compose()
    assert agent()["environment"]["INTERVIEW_AGENT_BACKEND_URL"] == "http://backend:8000"
    assert agent()["depends_on"]["backend"]["condition"] == "service_healthy"
    assert "backend" in data["services"]


def test_backend_still_reaches_postgres_by_its_service_name_whatever_env_says():
    env = backend_env()
    assert env["DB_HOST"] == "db" and env["DB_PORT"] == "5432"  # literals: .env cannot point the container at 127.0.0.1
    assert env["CAREERSYNC_DOTENV"] == "0"
    assert "db" in compose()["services"]


@pytest.mark.parametrize("name", SHARED)
def test_backend_and_agent_get_the_same_value_of_the_shared_settings(name):
    assert agent()["environment"][name] == backend_env()[name] == f"${{{name}:-}}"


@pytest.mark.parametrize("name", NO_DEFAULT_VALUES)
def test_no_key_or_secret_has_a_default_value_in_the_compose_file(name):
    values = [agent()["environment"].get(name), backend_env().get(name)]
    assert all(v is None or v == f"${{{name}:-}}" for v in values)


def test_agent_follows_its_own_mode_variable_and_the_backend_is_untouched_by_it():
    assert agent()["environment"]["AI_MODE"] == "${INTERVIEW_AGENT_AI_MODE:-${AI_MODE:-llm}}"
    assert backend_env()["AI_MODE"] == "${AI_MODE:-llm}"
    assert backend_env()["LLM_PROVIDER"] == "${LLM_PROVIDER:-groq}"
    assert backend_env()["LLM_MODEL"] == "${LLM_MODEL:-openai/gpt-oss-120b}"


def test_each_service_gets_only_its_own_model_key():
    # D91/D90: backend uses LLM_API_KEY (falling back to GROQ_API_KEY for Compose demo); agent uses GROQ_API_KEY and optional Anam only
    assert "LLM_API_KEY" not in agent()["environment"]
    for key in ("GROQ_API_KEY", "INTERVIEW_AGENT_AVATAR", "ANAM_API_KEY", "ANAM_AVATAR_ID"):
        assert key not in backend_env()
    assert backend_env()["LLM_API_KEY"] == "${LLM_API_KEY:-${GROQ_API_KEY:-}}"
    assert agent()["environment"]["GROQ_API_KEY"] == "${GROQ_API_KEY:-}"
    assert agent()["environment"]["INTERVIEW_AGENT_AVATAR"] == "${INTERVIEW_AGENT_AVATAR:-auto}"
    assert agent()["environment"]["ANAM_API_KEY"] == "${ANAM_API_KEY:-}"
    assert agent()["environment"]["ANAM_AVATAR_ID"] == "${ANAM_AVATAR_ID:-}"


def test_backend_image_keeps_the_local_ocr_packages():
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    for package in ("tesseract-ocr", "tesseract-ocr-kor", "tesseract-ocr-eng"):
        assert f" {package}" in dockerfile, f"backend/Dockerfile no longer installs {package}"


def test_agent_image_installs_its_lock_and_checks_the_local_models():
    dockerfile = (ROOT / "interview_agent/Dockerfile").read_text(encoding="utf-8")
    assert "pip install --no-deps -r /app/interview_agent/requirements.linux.lock.txt" in dockerfile
    assert "pip check" in dockerfile
    assert "python -m livekit.agents download-files" in dockerfile
    assert "silero.VAD.load()" in dockerfile and "EOT()" in dockerfile  # a missing model file fails the build, not the container
    assert dockerfile.index("requirements.linux.lock.txt") < dockerfile.index("COPY ai ")  # code changes keep the install layers cached
    for source in ("COPY ai /app/ai", "COPY data /app/data", "COPY interview_agent /app/interview_agent"):
        assert source in dockerfile
    assert '"-m", "interview_agent.voice", "start"' in dockerfile
    assert ".env" not in dockerfile.replace("requirements", "")  # the agent reads no .env file


def test_build_context_leaves_out_the_agents_venv_and_reports_and_every_env_file():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for pattern in ("**/.venv", "interview_agent/.runs", ".env", ".env.*"):
        assert pattern in ignored, f".dockerignore must list {pattern}: interview_agent/ is copied into the agent image whole"
