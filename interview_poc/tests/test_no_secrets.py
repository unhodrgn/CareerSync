"""No key or token is written into the PoC's files, and the PoC stays isolated from CareerSync's code."""
import importlib.util
import re
from pathlib import Path

from config import POC_DIR

SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".runs"}
SKIP_FILES = {"requirements.lock.txt"}


def poc_files():
    for path in POC_DIR.rglob("*"):
        rel = path.relative_to(POC_DIR)
        if path.is_file() and not (set(rel.parts) & SKIP_DIRS) and path.name not in SKIP_FILES and path.name != ".env":
            yield path


def test_no_key_like_strings_in_any_file():
    patterns = [
        re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
        re.compile(r"gsk_[A-Za-z0-9]{20,}"),  # a Groq API key
        re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\."),  # a JWT
        re.compile(r"(?i)(api[_-]?(key|secret)|token)\s*[=:]\s*['\"][A-Za-z0-9_-]{16,}['\"]"),
    ]
    for path in poc_files():
        if path.suffix in (".png", ".jpg", ".pyc"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            assert not pattern.search(text), f"{path.relative_to(POC_DIR)} looks like it contains a secret"


def test_no_anthropic_integration_remains_in_the_poc():
    """The PoC's LLM is Groq only: no Anthropic import, plugin, dependency, endpoint or key variable (the word may appear in prose)."""
    forbidden = [
        re.compile(r"(?mi)^\s*(?:from|import)\s+anthropic\b"),
        re.compile(r"livekit[.-]plugins[.-]anthropic"),
        re.compile(r"(?mi)^\s*anthropic\s*(?:[<>=!~]|$)"),  # a requirement line
        re.compile(r"(?i)livekit-agents\[[^\]]*anthropic"),  # the extra
        re.compile(r"(?i)api\.anthropic\.com"),
        re.compile(r"(?m)^\s*ANTHROPIC_API_KEY\s*="),  # an env-file line (conftest only scrubs the name)
    ]
    this_file = Path(__file__).name
    for path in POC_DIR.rglob("*"):
        rel = path.relative_to(POC_DIR)
        if not path.is_file() or (set(rel.parts) & SKIP_DIRS) or path.name in (".env", this_file) or path.suffix in (".png", ".jpg", ".pyc"):
            continue  # the real .env is never opened; this file holds the patterns themselves
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in forbidden:
            assert not pattern.search(text), f"{rel} still has an Anthropic integration ({pattern.pattern})"


def test_the_anthropic_packages_are_not_installed_in_this_environment():
    # The PoC's LLM is Groq only. If this fails: pip uninstall anthropic livekit-plugins-anthropic (in interview_poc/.venv)
    assert importlib.util.find_spec("anthropic") is None
    assert importlib.util.find_spec("livekit.plugins.anthropic") is None


def test_env_example_has_names_only():
    for line in (POC_DIR / ".env.example").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if match and match.group(1).endswith(("_KEY", "_SECRET")):
            assert match.group(2) == "", f"{match.group(1)} must be empty in .env.example"


def test_the_poc_does_not_import_careersync_code():
    pattern = re.compile(r"^\s*(?:from|import)\s+(?:app|ai)(?:\.|\s|$)", re.M)
    for path in POC_DIR.glob("*.py"):
        assert not pattern.search(path.read_text(encoding="utf-8")), f"{path.name} imports app.* or ai.*"
    for path in (POC_DIR / "tests").glob("*.py"):
        assert not pattern.search(path.read_text(encoding="utf-8")), f"tests/{path.name} imports app.* or ai.*"


def test_the_gitignore_covers_local_secrets_and_reports():
    ignored = (POC_DIR / ".gitignore").read_text(encoding="utf-8").split()
    for entry in (".env", ".env.*", ".venv/", ".runs/"):
        assert entry in ignored
    assert Path(POC_DIR / ".env.example").exists()
