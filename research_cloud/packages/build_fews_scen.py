"""Build the FEWS NET scen-b43ef6a-v1 actual-case packages (4 cases x pooled/system).

  python -m research_cloud.packages.build_fews_scen --out PACKAGES_DIR [--fews-src DIR]
"""
import argparse
import os

from research_cloud.packages import fews_scen

SRC = "/home/swl007007/projects/food-crisis-research/sources/Food_Crisis_Cluster/FEWSNETGeoXGBExperiment"
RUNTIME = {"python": "3.12", "numpy": "2.2.6", "pandas": "2.2.3", "xgboost": "3.0.0", "polars": "1.27.1",
           "geopandas": "1.0.1", "scikit-learn": "1.6.1", "scipy": "1.15.2", "env": "rt-fews-x300",
           "deviation": "original runtime Windows Python 3.12.10; Linux replay is a declared platform deviation"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--fews-src", default=SRC)
    args = ap.parse_args()
    for h, target in fews_scen.CASES:
        done = all(os.path.exists(os.path.join(args.out, f"fews-scen-b43ef6a-v1-actual-{h}-{target}-{arm}", "package.json"))
                   for arm in ("pooled", "system"))
        if done:
            print(h, target, "exists")
            continue
        metas = fews_scen.build_case(args.out, h, target, args.fews_src, RUNTIME)
        for arm, m in metas.items():
            print(h, target, arm, m["status"], m["full_cohort_check"], m["reference"]["rows"], flush=True)


if __name__ == "__main__":
    main()
