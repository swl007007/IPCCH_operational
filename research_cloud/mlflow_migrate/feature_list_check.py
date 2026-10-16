"""Acceptance for the feature-list mapping: every tagged logged model's ordered feature lists, read from the ORIGINAL
tag against the local stores, must equal the lists read through the MLflow server in cloud mode (mapped tag
preferred, local roots disabled) by the given (read-only) identity.

  python -m research_cloud.mlflow_migrate.feature_list_check --original-db SNAPSHOT.db --tracking-uri URL --report R.json
"""
import argparse
import importlib
import json
import os
import sqlite3


def original_specs(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    return dict(con.execute("SELECT model_id, tag_value FROM logged_model_tags WHERE tag_key = 'card.feature_list'"))


def main(argv=None):
    from mlflow.tracking import MlflowClient
    ap = argparse.ArgumentParser()
    ap.add_argument("--original-db", required=True)
    ap.add_argument("--tracking-uri", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    reader = importlib.import_module("research_cloud.service.ipcch_model")
    originals = original_specs(args.original_db)
    os.environ["MLFLOW_TRACKING_URI"] = args.tracking_uri
    client = MlflowClient(tracking_uri=args.tracking_uri)
    rows = []
    for model_id, spec in sorted(originals.items()):
        os.environ.pop("IPCCH_MODEL_CLOUD", None)
        want = [(l, n) for l, _, _, n in reader.feature_blocks(spec)]
        tags = client.get_logged_model(model_id).tags
        if tags.get("card.feature_list") != spec:
            rows.append({"model_id": model_id, "ok": False, "error": "original tag changed in the target store"})
            continue
        cloud_spec = tags.get("card.feature_list.cloud") or tags["card.feature_list"]
        os.environ["IPCCH_MODEL_CLOUD"] = "1"
        try:
            got = [(l, n) for l, _, _, n in reader.feature_blocks(cloud_spec)]
            err = None
        except SystemExit as e:
            got, err = None, str(e)
        rows.append({"model_id": model_id, "mapped": "card.feature_list.cloud" in tags, "blocks": len(want),
                     "features": sum(len(n) for _, n in want), "ok": got == want, "error": err})
    report = {"models": len(rows), "ok": sum(r["ok"] for r in rows), "mapped": sum(bool(r.get("mapped")) for r in rows),
              "features_compared": sum(r.get("features", 0) for r in rows), "rows": rows}
    json.dump(report, open(args.report, "w"), indent=1)
    print(json.dumps({k: report[k] for k in ("models", "ok", "mapped", "features_compared")}))
    return 0 if report["ok"] == report["models"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
