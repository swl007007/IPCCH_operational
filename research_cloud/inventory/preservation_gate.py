"""Final gate over the per-root preservation manifests: every expected root has a manifest that parses, is complete,
has no walk errors and whose recorded checks all pass. Missing, unreadable or incomplete manifests fail the gate.

  python -m research_cloud.inventory.preservation_gate --dir MANIFEST_DIR --catalog fews_run_catalog.json
      [--extra NAME ...] --out GATE.json
"""
import argparse
import json
import os
import sys


def gate(directory, expected):
    rows, ok = [], True
    for name in expected:
        path = os.path.join(directory, f"{name}.json")
        row = {"root": name, "manifest": path}
        try:
            m = json.load(open(path))
            row.update(files=m["totals"]["files"], bytes=m["totals"]["bytes"], complete=bool(m["complete"]),
                       walk_errors=len(m["walk_errors"]), symlinks=len(m["symlinks"]),
                       recorded=f"{m['totals']['recorded_ok']}/{m['totals']['recorded_checked']}")
            row["passed"] = row["complete"] and row["walk_errors"] == 0 and \
                m["totals"]["recorded_ok"] == m["totals"]["recorded_checked"]
        except (OSError, ValueError, KeyError) as e:
            row.update(passed=False, error=f"{type(e).__name__}: {e}")
        ok &= row["passed"]
        rows.append(row)
    total = {"roots": len(rows), "passed": sum(r["passed"] for r in rows),
             "files": sum(r.get("files", 0) for r in rows), "bytes": sum(r.get("bytes", 0) for r in rows)}
    return {"passed": ok, "total": total, "roots": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    expected = [r["run"] for r in json.load(open(args.catalog))["runs"]] + args.extra
    result = gate(args.dir, expected)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({"passed": result["passed"], **result["total"],
                      "failed": [r["root"] for r in result["roots"] if not r["passed"]]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
