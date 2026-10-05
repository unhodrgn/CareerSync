"""Create the schema and seed demo accounts before the backend starts."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        check=True,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed.py")],
        cwd=ROOT / "backend",
        check=True,
    )


if __name__ == "__main__":
    main()
