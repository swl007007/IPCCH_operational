"""Build IPCCH Somalia-oracle packages for every registered version of a supported run.

  python -m research_cloud.packages.build_somalia --snapshot DB --out PACKAGES_DIR --source-key somalia_oracle_v2_q3
"""
import argparse
import glob
import json
import os
import sqlite3

from research_cloud.packages import somalia

STORE = "/home/swl007007/.local/share/ipcch-mlflow"
IPCCH = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/google fund/analysis/2.source_code/step5_geo_rf_trial/IPCCH"
RUNS = {"somalia_oracle_v2_q3": somalia, "somalia_oracle_v3_validity": somalia, "somalia_oracle_v4_calibrated_d": somalia}
RUNTIME = {"python": "3.12", "xgboost": "3.2.0", "numpy": "2.4.4", "pandas": "3.0.3", "scikit-learn": "1.8.0",
           "env": "rt-ipcchgeo-x320", "note": "matches the run manifest's recorded Linux runtime"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-key", required=True, choices=sorted(RUNS))
    args = ap.parse_args()
    module = RUNS[args.source_key]
    plan = next(json.load(open(p)) for p in glob.glob(f"{STORE}/artifacts/3/*/artifacts/manifests/plan.json")
                if json.load(open(p))["source_key"] == args.source_key)
    db = sqlite3.connect(f"file:{args.snapshot}?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    q = """SELECT v.name, v.version, l.model_id,
             (SELECT tag_value FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='zz_prov.version_key'),
             (SELECT tag_value FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='family')
           FROM model_versions v JOIN logged_models l ON v.source='models:/'||l.model_id WHERE l.experiment_id=4"""
    for name, version, model_id, vk, family in db.execute(q).fetchall():
        if not vk.endswith("@" + args.source_key):
            continue
        out = os.path.join(args.out, "somalia-" + vk.replace("/", "_").replace("@", "--"))
        if os.path.exists(os.path.join(out, "package.json")):
            continue
        meta = module.build(out, source_key=args.source_key, ipcch_root=IPCCH, plan_version=plan["versions"][vk],
                            version_key=vk, version={"registered_model": name, "version": version, "logged_model_id": model_id,
                                                     "family": family}, runtime=RUNTIME)
        print(os.path.basename(out), meta["status"], meta["fitted_units"], meta["reference"]["rows"], meta["gaps"][:2], flush=True)


if __name__ == "__main__":
    main()
