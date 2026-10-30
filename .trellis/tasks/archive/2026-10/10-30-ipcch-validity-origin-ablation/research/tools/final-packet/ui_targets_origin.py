"""Rendered-UI targets for task 10-30, built only from passed readback receipts (readback/formal-hHH.json and
baseline-hHH.json), for the existing read-only harness archive/2026-10/10-20-ipcch-acled-retrain/research/cp4/ui/
harness-cap5000/browser_check.py and verify_run_rows.py. Adapted from task 10-28 ui_targets_ch.py (base copy in
base-10-28/): origin artifacts, the fit-label/origin provenance tags and origin.* metric rows; the six identities are the
three origin-ablation runs and the three CH-final baseline runs (unchanged, from their baseline readback); one DatasetInput.

Metric checks (two existing checkers, both required for a UI pass):
* run pages: ``run_metric_rows`` -> ``verify_run_rows.py`` (header-aware ``Metric | Value | Models``; its ``ui_pass`` =
  harness ``acceptance.json`` all_pass AND every run metric row). ``rows_checks.metric_rows`` is NOT used on run pages:
  ``verify_render.metric_row`` reads a row's LAST cell, which on a run page is the Models column (task 10-20 finding).
* LoggedModel pages: ``rows_checks.metric_rows`` (``verify_render``; last cell = value) for the model's dataset metric with
  its ``name (#digest)`` cell and source-run link, plus readiness waits (``Metrics (1)`` and the key).
A run target without ``run_metric_rows`` is refused. Offline rejection test: ``test_ui_targets.py``.

Per origin-ablation run: run page (names, dataset, tags incl. family_title / data version / code overlay, metric rows incl.
report.*), artifacts (report tables and both region maps), dataset details, LoggedModel page. Shared: the Dashboard
Experiments tab ("Model training") listing all six run names (CH-final + origin-ablation H0/H6/H12), and the Models table with
``models_rows`` binding all SIX identities (run, LoggedModel, registered model/version, dataset name/digest).

  python ui_targets.py --readback DIR --out NEW_DIR
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = ("h00", "h06", "h12")
KEYS = ("historical_pooled.binary_f1", "holdout_2026_01_10.binary_f1", "report.region.east_africa.holdout.binary_f1",
        "report.temporal.somalia.holdout.binary_f1", "report.temporal.all_regions.2024.macro_f1", "scored_rows",
        "origin.historical_pooled.delta_matched_augmented_minus_original.binary_f1", "origin.holdout_2026_01_10.original.binary_f1",
        "origin.holdout_2026_01_10.augmented_total.n_rows")
ARTIFACTS = ("predictions.csv.gz", "metrics.json", "model-card.md", "equivalence.json", "trial.json", "report_tables.csv",
             "report_region_mapping.csv", "region_mapping.csv", "origin_comparison.csv", "origin_comparison.json", "origin_tui.csv")
TAG_KEYS = ("family", "family_title", "arm", "arm_role", "record_kind", "lead_months", "baseline.run_id", "provenance.data_version",
            "provenance.code_overlay", "provenance.hpt_freeze_sha256", "vertex.CLOUD_ML_JOB_ID", "provenance.ch_links",
            "provenance.fit_labels", "provenance.origin_ablation")
HARNESS_EXPERIMENT = "2"
MODEL_METRIC = "dataset.modeling_panel_index.rows"     # research_cloud.training.dataset_input.MODEL_DATASET_METRIC


def targets(g, rb, metrics):
    run, model, ver, exp = rb["run"], rb["logged_model"], rb["version"], rb["experiment"]["id"]
    if not rb.get("all_checks_pass") or rb["mode"] != "formal" or rb["group"] != g:
        raise SystemExit(f"{g}: readback missing or not passed")
    ds, legacy = run["authoritative_dataset"], []      # an origin run publishes in-job: exactly one DatasetInput (readback-checked)
    tags = run["tags"]
    missing = [k for k in TAG_KEYS if not tags.get(k)] + [a for a in ARTIFACTS if a not in rb["artifacts_root"]] + [k for k in KEYS if k not in metrics]
    if missing:
        raise SystemExit(f"{g}: readback lacks {missing}")
    prof, schema = json.loads(ds["profile"]), json.loads(ds["schema"])["mlflow_colspec"]
    rows = [{"key": k, "value": metrics[k], "href_contains": f"/runs/{run['id']}/model-metrics"} for k in KEYS]
    return [
        {"label": f"{g}-run", "fragment": f"#/experiments/{exp}/runs/{run['id']}",
         "expect": [run["name"], ds["name"], f"Metrics ({run['n_metrics']})"],
         "segments": [{"after": "Logged models (1)", "before": "About this run", "expect": [model["name"], "Ready", ver["name"], f"v{ver['version']}"]},
                      {"after": "Datasets", "before": "Tags", "expect": [f"{d['name']} ({d['digest']})" for d in (ds, *legacy)]},
                      {"after": "\nTags\n", "before": "\nRegistered models", "expect": [f"{k}\n: {tags[k]}" for k in TAG_KEYS]
                       + (["publication.recovery_code"] if legacy else [])}],
         "run_metric_rows": rows},
        {"label": f"{g}-artifacts", "fragment": f"#/experiments/{exp}/runs/{run['id']}/artifacts", "expect": list(ARTIFACTS)},
        {"label": f"{g}-dataset", "fragment": f"#/experiments/{exp}/runs/{run['id']}", "clicks": [ds["name"]],
         "expect": ["Data details for", ds["digest"], f"num rows: {prof['num_rows']}", "\n".join(f"{c['name']}\n{c['type']}" for c in schema)]},
        {"label": f"{g}-logged-model", "fragment": f"#/experiments/{exp}/models/{model['id']}",
         "expect": [model["name"], ds["name"], "Ready", "Metrics (1)", MODEL_METRIC],
         "rows_checks": {"metric_rows": [{"key": MODEL_METRIC, "value": float(prof["num_rows"]), "dataset": f"{ds['name']} (#{ds['digest']})",
                                          "href_contains": f"/runs/{run['id']}"}]}},     # LoggedModel cell shows "name (#digest)"
    ]


def ident_new(g, rb):
    ds = rb["run"]["authoritative_dataset"]
    return {"group": f"origin-{g}", "run_id": rb["run"]["id"], "run_name": rb["run"]["name"], "model_id": rb["logged_model"]["id"],
            "registered_model": rb["version"]["name"], "model_version": str(rb["version"]["version"]),
            "dataset_name": ds["name"], "expected_digest": ds["digest"]}


def ident_old(g, rb):
    """CH-final baseline identities come only from its passed baseline readback (anchored to the task 10-28 supplemental
    receipt; its LoggedModel's Dataset is its authoritative CH DatasetInput)."""
    if not rb.get("all_checks_pass") or rb["mode"] != "baseline":
        raise SystemExit(f"baseline {g}: readback missing or not passed")
    ds = rb["run"]["authoritative_dataset"]
    return {"group": f"ch-final-{g}", "run_id": rb["anchors"]["run_id"], "run_name": rb["run"]["name"], "model_id": rb["anchors"]["model_id"],
            "registered_model": rb["anchors"]["registered_model"], "model_version": str(rb["anchors"]["model_version"]),
            "dataset_name": ds["name"], "expected_digest": ds["digest"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--readback", default=os.path.join(HERE, "readback"))
    a = ap.parse_args()
    os.makedirs(a.out)
    new = {g: json.load(open(os.path.join(a.readback, f"formal-{g}.json"))) for g in GROUPS}
    old = {g: json.load(open(os.path.join(a.readback, f"baseline-{g}.json"))) for g in GROUPS}
    exps = {rb["experiment"]["id"] for rb in new.values()} | {rb["run"]["experiment_id"] for rb in old.values()}
    if exps != {HARNESS_EXPERIMENT}:
        raise SystemExit(f"runs span experiments {exps}; the harness models_rows check pins experiment {HARNESS_EXPERIMENT}")
    out = []
    for g, rb in new.items():
        out += targets(g, rb, json.load(open(rb["trial_metrics_path"])))
    run_targets = [t for t in out if t["label"].endswith("-run")]
    if sorted(t["label"] for t in run_targets) != [f"{g}-run" for g in GROUPS] or any(not t.get("run_metric_rows") for t in run_targets):
        raise SystemExit("exactly the three origin run targets must exist, each with run_metric_rows (verify_run_rows ui_pass)")
    idents = [ident_new(g, new[g]) for g in GROUPS] + [ident_old(g, old[g]) for g in GROUPS]
    names = [i["run_name"] for i in idents]
    for field in ("run_id", "model_id", "run_name", "registered_model"):
        if len({i[field] for i in idents}) != 6:
            raise SystemExit(f"the six identities are not distinct in {field}: {[i[field] for i in idents]}")
    out += [{"label": "dashboard-experiment", "fragment": f"#/experiments/{HARNESS_EXPERIMENT}", "clicks": ["Model training"],
             "expect": ["IPCCH dashboard", *names]},
            {"label": "models-table", "fragment": f"#/experiments/{HARNESS_EXPERIMENT}/models", "clicks": ["Model training", "Models"],
             "expect": ["Model attributes", "Dataset"], "rows_checks": {"models_rows": idents}}]
    json.dump(out, open(os.path.join(a.out, "targets.json"), "w"), indent=1)
    print(json.dumps({"targets": [t["label"] for t in out], "identities": len(idents)}))


if __name__ == "__main__":
    main()
