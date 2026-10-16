"""Build pop-v1 packages (one per arm x horizon) from the original run root.

  python -m research_cloud.packages.build_popv1 --inventory popv1_models.json --out PACKAGES_DIR
"""
import argparse
import json
import os

from research_cloud.packages import popv1
from research_cloud.packages.common import ensure_local, sha256_file

RUN = ("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/"
       "Food_Crisis_Cluster/IPCCHPopulationHistoryExperiment/runs/pop-v1")
RUNTIME = {"python": "3.12", "numpy": "2.2.6", "pandas": "2.2.3", "scikit-learn": "1.6.1", "scipy": "1.15.2",
           "xgboost": "3.0.0", "env": "rt-popv1-x300",
           "deviation": "original runtime Windows Python 3.12.10; Linux replay is a declared platform deviation"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    inv = json.load(open(args.inventory))
    if not inv.get("complete") or inv.get("walk_errors"):
        raise SystemExit("model inventory incomplete")
    files = [dict(f, path=os.path.basename(f["path"])) for f in inv["files"]]
    ensure_local([os.path.join(RUN, "data/rich561_X.npy")])
    matrix_sha = sha256_file(os.path.join(RUN, "data/rich561_X.npy"))
    for arm in popv1.ARMS:
        for h in (1, 3, 6, 12):
            out = os.path.join(args.out, f"popv1-{arm}-h{h:02d}")
            if os.path.exists(os.path.join(out, "package.json")):
                print(os.path.basename(out), "exists")
                continue
            meta = popv1.build(out, run_root=RUN, arm=arm, horizon=h, inventory=files, matrix_sha256=matrix_sha, runtime=RUNTIME)
            print(os.path.basename(out), meta["status"], meta["fitted_units"], meta["reference"]["rows"], meta["gaps"][:2], flush=True)


if __name__ == "__main__":
    main()
