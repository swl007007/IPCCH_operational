"""Build (and optionally replay) every registered version of an IPCCH GeoXGB family.

  python -m research_cloud.packages.build_geoxgb --family geoxgb_reference --snapshot DB --out PACKAGES_DIR

Version identities come from the MLflow snapshot (read-only); run roots, member manifests,
archived source_code and runtime locks are the family's recorded sources below.
"""
import argparse
import json
import os
import sqlite3

from research_cloud.packages import geoxgb

ART = "/home/swl007007/.local/share/ipcch-mlflow/artifacts/1"
SOURCES = {
    "geoxgb_reference": {
        "family_run_id": "bdbafe393d694439a1c35ccec4d5816a", "source_run_id": "p6-formal-20261004b",
        "run_root": "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/"
                    "Food_Crisis_Cluster/IPCCHGeoXGBExperiment/runs/p6-formal-20261004b",
        "source_code": "source_code/IPCCHGeoXGBExperiment", "commit": "6798df2"},
    "geoxgb_yearly_refit": {
        "family_run_id": "a6dc32cda52f45a7a5f12e87a72c6749", "source_run_id": "yearly-formal-20261007",
        "run_root": "/home/swl007007/ipcch-legacy-source-preservation/yearly-formal-20261007",
        "source_code": "source_code/IPCCHYearlyGeoXGBExperiment", "commit": "29c5fee"},
}
LINUX = {"python": "3.12", "xgboost": "3.0.0", "numpy": "2.2.6", "pandas": "2.2.3", "env": "rt-geoxgb-x300",
         "deviation": "original runtime is Windows-only; Linux replay is a declared platform deviation judged by D11 tolerance"}


def versions(snapshot, family):
    db = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    q = """SELECT v.name, v.version, l.model_id,
             (SELECT tag_value FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='arm'),
             (SELECT tag_value FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='lead_months')
           FROM model_versions v JOIN logged_models l ON v.source='models:/'||l.model_id
           WHERE EXISTS (SELECT 1 FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='family' AND t.tag_value=?)
           ORDER BY 4, 5"""
    return [dict(name=n, version=v, model_id=m, arm=a, lead=int(ld)) for n, v, m, a, ld in db.execute(q, (family,))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True, choices=sorted(SOURCES))
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = SOURCES[args.family]
    art = f"{ART}/{src['family_run_id']}/artifacts"
    sc = f"{art}/{src['source_code']}"
    lock = json.load(open(f"{sc}/config/runtime-lock.json"))
    for v in versions(args.snapshot, args.family):
        slug = f"{args.family}-{v['arm']}-h{v['lead']:02d}"
        out = os.path.join(args.out, slug)
        if os.path.exists(os.path.join(out, "package.json")):
            print(slug, "exists")
            continue
        meta = geoxgb.build(
            out, family=args.family, run_root=src["run_root"], source_code_dir=sc,
            members_manifest=f"{art}/manifests/models.tar.members.json",
            version={"registered_model": v["name"], "version": v["version"], "logged_model_id": v["model_id"],
                     "family_run_id": src["family_run_id"], "source_run_id": src["source_run_id"]},
            lead=v["lead"], arm=v["arm"],
            code_identity={"commit": src["commit"], "source_code_artifact": f"runs:/{src['family_run_id']}/source_code"},
            original_runtime={k: lock[k] for k in ("python", "platform_system", "packages", "model_runtime") if k in lock},
            linux_runtime=LINUX)
        print(slug, meta["status"], meta["fitted_units"], meta["reference"]["rows"], meta["gaps"][:2])


if __name__ == "__main__":
    main()
