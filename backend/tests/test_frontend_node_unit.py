"""Runs the frontend unit tests in frontend/tests/ with Node's built-in test runner (no npm dependency), so a plain
`pytest` covers them. Skipped when Node is missing or too old to run TypeScript directly (22.18+ / 23.6+)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "frontend" / "tests"


def _node_can_strip_types() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    m = re.match(r"v(\d+)\.(\d+)", subprocess.run([node, "--version"], capture_output=True, text=True).stdout)
    return bool(m) and (int(m[1]), int(m[2])) >= (22, 18) and (int(m[1]), int(m[2])) != (23, 0) and not (int(m[1]) == 23 and int(m[2]) < 6)


@pytest.mark.skipif(not _node_can_strip_types(), reason="Node 22.18+ or 23.6+ is needed to run TypeScript tests directly")
def test_frontend_unit_tests_pass():
    files = sorted(str(p) for p in TESTS.glob("*.test.ts"))
    assert files, "no frontend unit test"
    r = subprocess.run(["node", "--test", *files], capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert re.search(r"(?m)^ℹ fail 0$", r.stdout), r.stdout[-2000:]
