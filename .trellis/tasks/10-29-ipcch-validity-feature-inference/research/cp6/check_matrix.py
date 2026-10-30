"""CP6: every `suite::test` reference in cp6-evidence-matrix.md must name an indexed test (test-index.json), and every
R1-R66 / AC1-AC40 / FCC1-FCC10 row must be present exactly once. Run: python3 check_matrix.py (exit 1 on failure)."""

import json
import re
import sys
from pathlib import Path

here = Path(__file__).parent
text = (here / "cp6-evidence-matrix.md").read_text()
index = json.loads((here / "test-index.json").read_text())
names = {}
for path, v in index.items():
    stem = Path(path).stem
    suite = stem.removeprefix("test_")
    names[suite] = {t["name"].removeprefix("test_") for t in v["tests"]}
bad, last = [], None
for m in re.finditer(r"`([a-z0-9_]+)::(\*|[a-z0-9_]+)`|`::([a-z0-9_]+)`", text):
    suite, test, cont = m.group(1), m.group(2), m.group(3)
    if suite:
        last = suite
        if suite not in names or (test != "*" and test not in names[suite]):
            bad.append(f"{suite}::{test}")
    elif cont and (last is None or cont not in names.get(last, set())):
        bad.append(f"{last}::{cont}")
rows = re.findall(r"^\| (R\d+|AC\d+|FCC\d+) \|", text, re.M)
expected = [f"AC{i}" for i in range(1, 41)] + [f"R{i}" for i in range(1, 67)] + [f"FCC{i}" for i in range(1, 11)]
missing = [r for r in expected if rows.count(r) != 1]
print(f"references checked; unresolved: {bad}")
print(f"rows: {len(rows)}; missing or duplicated: {missing}")
sys.exit(1 if bad or missing else 0)
