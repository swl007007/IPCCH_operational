"""Build every registered AlphaEarth supervised-partition version (identities from the read-only snapshot).

  python -m research_cloud.packages.build_alphaearth --snapshot DB --out PACKAGES_DIR [--lead 3]
"""
import argparse
import json
import os

from research_cloud.packages import alphaearth
from research_cloud.packages.build_geoxgb import versions

FAMILY_RUN = "9939ac69809949e9923821fa692a7b2a"
ART = f"/home/swl007007/.local/share/ipcch-mlflow/artifacts/1/{FAMILY_RUN}/artifacts"
RUN_ROOT = "/home/swl007007/ipcch-alphaearth-runs/p1-formal-d30-20261014"
LINUX = {"python": "3.12", "xgboost": "3.2.0", "numpy": "2.4.4", "pandas": "3.0.3", "env": "rt-alphaearth-x320",
         "deviation": "none in platform: the original numerical runtime is Linux with the same pinned versions"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lead", type=int)
    args = ap.parse_args()
    sc = f"{ART}/source_code/IPCCHAlphaEarthExperiment"
    lock = json.load(open(f"{sc}/config/runtime-lock.json"))["numerical"]
    for v in versions(args.snapshot, "alphaearth_supervised_partition"):
        if args.lead and v["lead"] != args.lead:
            continue
        slug = f"alphaearth_supervised_partition-{v['arm']}-h{v['lead']:02d}"
        out = os.path.join(args.out, slug)
        if os.path.exists(os.path.join(out, "package.json")):
            print(slug, "exists")
            continue
        meta = alphaearth.build(
            out, run_root=RUN_ROOT, source_code_dir=sc, members_manifest=f"{ART}/manifests/models.tar.members.json",
            version={"registered_model": v["name"], "version": v["version"], "logged_model_id": v["model_id"],
                     "family_run_id": FAMILY_RUN, "source_run_id": "p1-formal-d30-20261014"},
            lead=v["lead"], arm=v["arm"],
            code_identity={"commit": "uncommitted; frozen code inventory 57ca2ef1, analysis amendment 385a8db8",
                           "source_code_artifact": f"runs:/{FAMILY_RUN}/source_code"},
            original_runtime=lock, linux_runtime=LINUX)
        print(slug, meta["status"], meta["fitted_units"], meta["reference"]["rows"], meta["gaps"][:2])


if __name__ == "__main__":
    main()
