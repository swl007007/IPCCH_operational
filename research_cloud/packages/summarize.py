"""Summarize replay receipts against the packages they claim to cover.

A receipt counts as a pass only when its recorded package.json sha256 equals the current
package's package.json; otherwise it is reported stale (e.g. a rebuild under the same ID).

  python -m research_cloud.packages.summarize --replays DIR --out SUMMARY.json
"""
import argparse
import glob
import json
import os

from research_cloud.packages.common import sha256_file


def routes_covered(package, m):
    """covered/total routes; cell-routed packages (FEWS ordinary) count reference cells against their units."""
    if "routes_covered" in m["reference"]:
        return f"{len(m['reference']['routes_covered'])}/{len(m['routing']['routes_in_version'])}"
    import pandas as pd
    routes = pd.read_csv(os.path.join(package, "reference", "expected.csv"), usecols=["route"])["route"].astype(str)
    return f"{routes.nunique()}/{len(m['units'])}"


def summarize(report_paths):
    rows = []
    for f in sorted(report_paths):
        r = json.load(open(f))
        pj = os.path.join(r["package"], "package.json")
        m = json.load(open(pj))
        current = sha256_file(pj)
        fresh = r.get("package_json_sha256") == current
        cols = r.get("columns") or {}
        rows.append(dict(
            package=os.path.basename(r["package"]), receipt=f, family=m["family"],
            registered_model=m["identity"].get("registered_model"), logged_model_id=m["identity"].get("logged_model_id"),
            status=m["status"], gaps=len(m["gaps"]), package_json_sha256=current,
            receipt_package_json_sha256=r.get("package_json_sha256"), receipt_matches_package=fresh,
            replay_passed=bool(r.get("passed")) and fresh, reference_rows=r.get("rows"), fitted_units=m.get("fitted_units"),
            max_abs_err=max((v["max_abs_err"] for v in cols.values()), default=None),
            routing_mismatches=r.get("routing_mismatches"), phase_changes=len(r.get("phase_changes", [])),
            routes_covered=routes_covered(r["package"], m),
            content_sha256=m["content_sha256"], package_bytes=sum(x["bytes"] for x in m["files"].values()),
            runtime=r.get("runtime")))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replays", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = summarize([p for p in glob.glob(os.path.join(args.replays, "*.json")) if not p.endswith("summary.json")])
    json.dump(rows, open(args.out, "w"), indent=1)
    print(len(rows), "passed", sum(r["replay_passed"] for r in rows), "stale", sum(not r["receipt_matches_package"] for r in rows),
          "rows", sum(r["reference_rows"] or 0 for r in rows))


if __name__ == "__main__":
    main()
