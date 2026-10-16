"""Map logged-model ``card.feature_list`` references that point into the local MLflow artifact root to ``runs:/``.

The original tag is never changed. For every logged model whose ``card.feature_list`` has a part under the local
artifact root (``<root>/<experiment>/<run>/artifacts/<path>``), a ``card.feature_list.cloud`` tag is written with that
part rewritten to ``runs:/<run>/<path>``; labels, block order, ``!member`` names and ``#column?filter`` selectors are
kept byte-for-byte, and parts that already use ``runs:/`` stay as they are. A part under any other local root is
refused (reported, not guessed). Re-running is idempotent: an existing mapped tag must equal the recomputed one.

  python -m research_cloud.mlflow_migrate.feature_list_map --tracking-uri URI --report REPORT.json [--apply]
"""
import argparse
import json
import re

LOCAL_ROOT = "/home/swl007007/.local/share/ipcch-mlflow/artifacts/"
TAG, CLOUD_TAG = "card.feature_list", "card.feature_list.cloud"
# logged models are returned with all their metrics (up to ~6.9k rows per model here); Cloud Run refuses responses
# over 32 MiB ("Response size was too large"), so pages stay small (worst case ~12 MB at 5 models)
PAGE = 5
LOCAL_PART = re.compile(re.escape(LOCAL_ROOT) + r"(?P<exp>[^/]+)/(?P<run>[0-9a-f]{32})/artifacts/(?P<path>[^!#]+)(?P<rest>.*)$")


def map_spec(spec):
    """(mapped spec or None when nothing is local, refusals)."""
    parts, changed, refusals = [], False, []
    for part in spec.split(" ; "):
        label, eq, loc = part.partition("=")
        if loc.startswith("runs:/") or not eq:
            parts.append(part)
            continue
        m = LOCAL_PART.match(loc)
        if not m:
            refusals.append(f"{label}: local reference outside the MLflow artifact root: {loc[:120]}")
            parts.append(part)
            continue
        parts.append(f"{label}=runs:/{m['run']}/{m['path']}{m['rest']}")
        changed = True
    return (" ; ".join(parts) if changed else None), refusals


def plan(client):
    rows = []
    for exp in client.search_experiments():
        token = None
        while True:
            page = client.search_logged_models(experiment_ids=[exp.experiment_id], max_results=PAGE, page_token=token)
            for m in page:
                spec = (m.tags or {}).get(TAG)
                if not spec:
                    continue
                mapped, refusals = map_spec(spec)
                rows.append({"model_id": m.model_id, "name": m.name, "original": spec, "mapped": mapped,
                             "existing_mapped": (m.tags or {}).get(CLOUD_TAG), "refusals": refusals})
            token = page.token
            if not token:
                break
    return rows


def main(argv=None):
    from mlflow.tracking import MlflowClient
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracking-uri", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    client = MlflowClient(tracking_uri=args.tracking_uri)
    rows = plan(client)
    drift = [r["model_id"] for r in rows if r["existing_mapped"] and r["existing_mapped"] != r["mapped"]]
    refused = [r for r in rows if r["refusals"]]
    if drift or refused:
        json.dump({"rows": rows, "drift": drift}, open(args.report, "w"), indent=1)
        raise SystemExit(f"refused: {len(refused)} models with unmappable local parts, {len(drift)} with a differing mapped tag")
    written = 0
    if args.apply:
        for r in rows:
            if r["mapped"] and r["existing_mapped"] != r["mapped"]:
                client.set_logged_model_tags(r["model_id"], {CLOUD_TAG: r["mapped"]})
                written += 1
    summary = {"tagged_models": len(rows), "mapped": sum(1 for r in rows if r["mapped"]),
               "unchanged_runs_refs": sum(1 for r in rows if not r["mapped"]), "written_now": written,
               "distinct_mapped_specs": len({r["mapped"] for r in rows if r["mapped"]})}
    json.dump({"summary": summary, "rows": rows}, open(args.report, "w"), indent=1)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
