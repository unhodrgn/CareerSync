"""What the agent may import (D52, D56): never the backend (`app`), never a model SDK directly; LiveKit only in turn_model.py and only
inside functions, so the runner and the text driver work without the LiveKit packages."""
import ast
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1]


def imports(path: Path) -> list[tuple[str, bool]]:
    """(module, imported at module level)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top = {id(node) for node in tree.body}
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(a.name, id(node) in top) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, id(node) in top))
    return out


def test_the_agent_never_imports_the_backend_or_a_model_sdk_and_imports_livekit_lazily_in_one_module():
    for path in sorted(AGENT.glob("*.py")):
        for module, top_level in imports(path):
            root = module.split(".")[0]
            assert root not in ("app", "anthropic", "openai", "groq"), (path.name, module)
            if root == "livekit":
                assert path.name == "turn_model.py" and not top_level, (path.name, module)
