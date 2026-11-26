"""Run both test suites: the backend and AI suite in the repository's environment, and the Interview Agent's suite in the agent's own
environment (docs/DECISIONS.md D80 (7)). From the repository root, with any Python:

    python scripts/run_all_tests.py [pytest arguments for both suites, e.g. -q]

Each suite runs with `CAREERSYNC_DOTENV=0` and `AI_MODE=rules` and without the database, agent-secret and model-key variables, so neither
makes a database, model or network call (PostgreSQL-gated tests skip). The exit code is 0 only when both pass; a missing virtual
environment is reported and counts as a failure.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = (
    ("backend and ai", ROOT / ".venv", []),  # testpaths of pyproject.toml
    ("interview_agent", ROOT / "interview_agent" / ".venv", ["interview_agent/tests"]),
)
REMOVED = (
    "DATABASE_URL", "TEST_DATABASE_URL", "TEST_DATABASE_EXPECTED_NAME", "TEST_DATABASE_CONFIRM_DESTRUCTIVE",
    "INTERVIEW_AGENT_SECRET", "GROQ_API_KEY", "LLM_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "LLM_EFFORT",
)


def python_in(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main(argv: list[str]) -> int:
    env = {key: value for key, value in os.environ.items() if key not in REMOVED}
    env.update(CAREERSYNC_DOTENV="0", AI_MODE="rules")
    results = []
    for name, venv, paths in SUITES:
        python = python_in(venv)
        if not python.exists():
            print(f"[{name}] no virtual environment at {python.relative_to(ROOT)}")
            results.append((name, None))
            continue
        print(f"[{name}] {python.relative_to(ROOT)} -m pytest {' '.join(paths + argv)}", flush=True)
        results.append((name, subprocess.call([str(python), "-m", "pytest", *paths, *argv], cwd=ROOT, env=env)))
    for name, code in results:
        print(f"{name}: {'passed' if code == 0 else 'no environment' if code is None else f'failed (exit code {code})'}")
    return 0 if all(code == 0 for _name, code in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
