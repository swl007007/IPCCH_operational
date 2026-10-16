"""Build IPCCH forecasting packages for registered versions in batch/launch formats.

  python -m research_cloud.packages.build_forecast --snapshot DB --out PACKAGES_DIR [--source-key K] [--limit N]

Registered identity (name, version, logged model, family) comes from the read-only snapshot; the
version's members come from its plan (``zz_prov.version_key``). Somalia-oracle source keys use a
different format and are not built here.
"""
import argparse
import glob
import json
import os
import re
import sqlite3

from research_cloud.packages import forecast_batch

STORE = "/home/swl007007/.local/share/ipcch-mlflow"
IPCCH = "/mnt/c/users/swl00/ifpri dropbox/weilun shi/google fund/analysis/2.source_code/step5_geo_rf_trial/IPCCH"
BATCH_KEYS = ("compact_global_original", "compact_somalia_original", "compact_global_2026_extension",
              "compact_somalia_2026_extension", "origin_safe_climate_idp_v1", "origin_safe_weather_oracle_v1",
              "compact_global_launch", "compact_somalia_launch")
RUNTIME = {"python": "3.12", "xgboost": "3.2.0", "numpy": "2.3.5", "pandas": "3.0.3", "scikit-learn": "1.9.0", "scipy": "1.17.1", "env": "rt-forecast-x320",
           "note": "numpy/pandas/scikit-learn/scipy from IPCCH uv.lock (python>=3.11 markers); xgboost is not pinned by the lock: 3.2.0 is the loader tested here, matching run metadata where recorded"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-key", action="append")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    db = sqlite3.connect(f"file:{args.snapshot}?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    plans = {}
    for path in glob.glob(f"{STORE}/artifacts/3/*/artifacts/manifests/plan.json"):
        plan = json.load(open(path))
        plans[plan["source_key"]] = plan
    q = """SELECT v.name, v.version, l.model_id,
             (SELECT tag_value FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='zz_prov.version_key'),
             (SELECT tag_value FROM logged_model_tags t WHERE t.model_id=l.model_id AND t.tag_key='family')
           FROM model_versions v JOIN logged_models l ON v.source='models:/'||l.model_id WHERE l.experiment_id=4 ORDER BY 4"""
    built = 0
    for name, version, model_id, version_key, family in db.execute(q).fetchall():
        source_key = version_key.split("@", 1)[1]
        if source_key not in BATCH_KEYS or (args.source_key and source_key not in args.source_key):
            continue
        slug = "forecast-" + re.sub(r"[^A-Za-z0-9_.-]+", "_", version_key.replace("@", "--"))
        out = os.path.join(args.out, slug)
        if os.path.exists(os.path.join(out, "package.json")):
            continue
        meta = forecast_batch.build(out, ipcch_root=IPCCH, plan_version=plans[source_key]["versions"][version_key],
                                    version_key=version_key, source_key=source_key,
                                    version={"registered_model": name, "version": version, "logged_model_id": model_id,
                                             "family": family}, runtime=RUNTIME)
        print(slug, meta["status"], meta["fitted_units"], meta["reference"]["rows"], meta["gaps"][:2], flush=True)
        built += 1
        if args.limit and built >= args.limit:
            break


if __name__ == "__main__":
    main()
