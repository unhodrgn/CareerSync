"""CareerSync backend.

The shared `ai` package lives at the repository root, next to `backend/`. Adding the root to
sys.path lets `uvicorn app.main:app` and `alembic` run from backend/ without setting PYTHONPATH.
"""
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)
