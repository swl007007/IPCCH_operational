"""Build the FEWS NET ordinary 162-column diagnostic run packages (D35, D37, D46, D47, D48; one per run).

  python -m research_cloud.packages.build_fews_ordinary --out PACKAGES_DIR [--run RUN ...]
"""
import argparse
import os

from research_cloud.packages import fews_ordinary
from research_cloud.packages.build_fews_scen import RUNTIME


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", action="append", choices=sorted(fews_ordinary.RUNS))
    args = ap.parse_args()
    names, schema_sha, features_sha = fews_ordinary.feature_order()
    snapshots = fews_ordinary.Snapshots(names)
    for run in args.run or list(fews_ordinary.RUNS):
        if os.path.exists(os.path.join(args.out, f"fews-{run}", "package.json")):
            print(run, "exists")
            continue
        m = fews_ordinary.build_run(args.out, run, snapshots, (names, schema_sha, features_sha), RUNTIME)
        print(run, m["status"], m["full_cohort_check"]["total"], m["reference"]["rows"], flush=True)


if __name__ == "__main__":
    main()
