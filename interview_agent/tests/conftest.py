"""The agent's offline tests: no network, no key, no LiveKit room. Run from the repository root in the agent's own environment:
`interview_agent\\.venv\\Scripts\\python.exe -m pytest interview_agent/tests -q` (or `python scripts/run_all_tests.py` for both suites)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # `ai` and `interview_agent` are imported from the repository, as the agent runs
