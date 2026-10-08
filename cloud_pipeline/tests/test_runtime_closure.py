"""Import all shipped runtime modules without any original repository on sys.path."""
import importlib
from pathlib import Path
import subprocess
import sys


def test_all_shipped_modules_import(tmp_path):
    root = Path(__file__).resolve().parents[1]
    modules = []
    for package in ("cloud", "fewsnet_partitioned_rf_pipeline", "model_pipeline", "tools"):
        for path in (root / package).rglob("*.py"):
            parts = list(path.relative_to(root).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            modules.append(".".join(parts))
    script = "import sys, importlib; sys.path.insert(0, " + repr(str(root)) + "); "
    script += "[importlib.import_module(name) for name in " + repr(sorted(set(modules))) + "]"
    subprocess.run([sys.executable, "-I", "-c", script], cwd=tmp_path, check=True)
