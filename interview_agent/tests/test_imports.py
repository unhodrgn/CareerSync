"""What the agent may import (D52, D56): never the backend (`app`), never a model SDK directly; LiveKit only in `voice.py` (the worker) and, inside
functions, in `turn_model.py`, so that everything else works without the LiveKit packages."""
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


def test_the_agent_never_imports_the_backend_or_a_model_sdk_and_imports_livekit_only_in_the_worker_and_lazily_in_the_model_client():
    """`voice.py` is the LiveKit worker and may import it at the top; `turn_model.py` imports the Groq plugin when a client is made. Every other
    module (the runner, the controller, the timing report, the client of the backend, the settings, the text driver, the dev page's server)
    runs without a LiveKit package: that is what lets the backend suite run the runner and the controller against the real application."""
    seen = set()
    for path in sorted(AGENT.glob("*.py")) + sorted((AGENT / "devclient").glob("*.py")):
        for module, top_level in imports(path):
            root = module.split(".")[0]
            assert root not in ("app", "anthropic", "openai", "groq"), (path.name, module)
            if root == "livekit":
                seen.add(path.name)
                assert path.name in ("voice.py", "turn_model.py") and (path.name == "voice.py" or not top_level), (path.name, module)
    assert seen == {"voice.py", "turn_model.py"}, "the worker and the model client are the two modules that use LiveKit"
