import importlib.util
from pathlib import Path


def test_cost_gates_fail_open_for_unknown_changes():
    path = Path(__file__).resolve().parents[1] / "scripts" / "ci_scope.py"
    spec = importlib.util.spec_from_file_location("ci_scope", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.classify(["README.md", "docs/demo.md"]) == (False, False)
    assert module.classify(["frontend/src/App.tsx"]) == (False, True)
    for name in ["storage/datastore.py", "uv.lock", "frontend/package-lock.json", "unexpected"]:
        assert module.classify(["README.md", name]) == (True, True)
