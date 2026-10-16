"""Build the FEWS NET map-transfer run packages (D42, D43; one per run).

  python -m research_cloud.packages.build_fews_map --out PACKAGES_DIR [--run RUN ...]
"""
import argparse
import os

from research_cloud.packages import fews_map, fews_ordinary
from research_cloud.packages.build_fews_scen import RUNTIME


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", action="append", choices=sorted(fews_map.RUNS))
    args = ap.parse_args()
    schema = fews_ordinary.feature_order()
    snapshots = fews_ordinary.Snapshots(schema[0])
    for run in args.run or list(fews_map.RUNS):
        if os.path.exists(os.path.join(args.out, f"fews-{run}", "package.json")):
            print(run, "exists")
            continue
        m = fews_map.build_run(args.out, run, snapshots, schema, RUNTIME)
        print(run, m["status"], m["full_cohort_check"]["total"], m["reference"]["rows"], flush=True)


if __name__ == "__main__":
    main()
