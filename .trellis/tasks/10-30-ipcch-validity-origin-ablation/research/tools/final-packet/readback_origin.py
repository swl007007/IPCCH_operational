"""Read-only MLflow readback for task 10-30 (run only under a released final packet; tooling venv). Adapted from the
accepted task 10-28 ``readback_ch.py`` (base copy in ``base-10-28/``): same reader identity handling, pinned tracking/
registry URIs and per-run checks, with the origin-ablation pins; no recovery or card-correction rules.

  formal   --item formal:hHH:TRIAL_DIR      the origin-ablation run in 'IPCCH dashboard' (harvested trial): run/LoggedModel/version links,
           READY, names, tags (arm/role/CH-final baseline link/freeze/data versions/fit_labels/overlay image and composite
           source identifier), live model-card.md bytes == the card regenerated from the harvested record, the recipe-derived
           card sections and every recipe tag == the reviewed offline render (``render-final``), features, metrics/params
           exact, downloaded package == local, report.* and origin.* metrics, retained package routes only the 2026 holdout context, exactly ONE DatasetInput == the harvested
           payload (3 GCS generation reads) and == the render on every non-generation field, model Dataset metric
  baseline --item baseline:hHH:RECEIPT      a CH-final run (read only) unchanged since its task 10-28 accepted (supplemental)
           readback receipt: run status/name/tags/metric count/model outputs/DatasetInputs, LoggedModel id/name/status/source run and
           version, live card bytes (sha256); run metric VALUES (the LoggedModel Dataset metric excluded) == the retained
           CH-final trial metrics and run + LoggedModel params == its resolved params (no extra call: get_run /
           get_logged_model already return them); LoggedModel tags are not compared; registered-model aliases recorded
  -> OUT_DIR/<mode>-<group>.json + summary.json; ONE reader-secret access

  W=/home/swl007007/projects/food-crisis-research; cd $W/control-plane-origin-ablation
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B readback_origin.py --out-dir DIR --item formal:h00:DIR ... --item baseline:h00:RECEIPT
"""
import argparse
import base64
import hashlib
import json
import math
import os
import re
import sys
import tempfile

W = "/home/swl007007/projects/food-crisis-research"
sys.path.insert(0, f"{W}/control-plane-origin-ablation")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "readback")
URI = "https://mlflow.weilunshi.com"
SECRET = "projects/food-crisis-modeling-enso/secrets/mlflow-reader/versions/latest"
ARM = "validity_augmented_idp_202610_acledagg_lag1_uncal_hpt"
TITLE = "Original-label fit ablation (GOSIF v3 + CH validity 20261028)"
WIDTH = {0: 527, 6: 539, 12: 539}
DASHBOARD = "IPCCH dashboard"
RENDER = f"{W}/staging/ipcch-origin-ablation-20261030/job-packet/render-final"
# card sections built from the recipe/config (must equal the offline render); the others come from the job's own record
RECIPE_SECTIONS = ("card", "summary", "baseline", "status", "feature_engineering", "architecture", "settings", "evaluation", "features")
# DatasetInput tags that depend on the job's output prefix/generations (the render used placeholders) or on the job's own
# gzip output bytes (idp_ledger.sha256: gzip header mtime; task 10-28 verifier lesson). The payload equality itself is
# checked against the harvested trial (dataset_input_equals_payload).
GENERATION_TAGS = ("gcs.generation", "memberships.uri", "memberships.gcs.generation", "idp_ledger.uri", "idp_ledger.gcs.generation",
                   "idp_ledger.sha256")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def reader():
    """Read-only MLflow identity, held only in this process's environment; returns the secret version name."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id="food-crisis-modeling-enso")
    r = AuthorizedSession(creds).get(f"https://secretmanager.googleapis.com/v1/{SECRET}:access", timeout=60)
    r.raise_for_status()
    cred = json.loads(base64.b64decode(r.json()["payload"]["data"]))
    os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"] = cred["username"], cred["password"]
    del cred
    return r.json()["name"]


def finite(metrics):
    return {k: float(v) for k, v in (metrics or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)}


def group_of(t):
    cfg = t["config"]
    if cfg["arm"] != ARM:
        raise SystemExit(f"unexpected arm {cfg['arm']}")
    return int(cfg["horizon"]), f"h{int(cfg['horizon']):02d}"


def inputs(run):
    return [{"name": di.dataset.name, "digest": di.dataset.digest, "source_type": di.dataset.source_type, "source": di.dataset.source,
             "schema": di.dataset.schema, "profile": di.dataset.profile, "tags": {t.key: t.value for t in di.tags}}
            for di in (run.inputs.dataset_inputs if run.inputs else [])]


def sections(card):
    """``## key`` sections of a full model card."""
    parts = re.split(r"(?m)^## (\w+)\n", card)
    return dict(zip(parts[1::2], (p.rstrip("\n") for p in parts[2::2])))


CH_TRIALS = f"{W}/scratch/ch-validity-20261028/harvest/formal-{{g}}/trial-0/publication.json"


def baseline(c, receipt, group):
    """Read-only check that a CH-final run is unchanged since the task 10-28 accepted (supplemental) readback receipt, with
    its metric values and params equal to the retained CH-final trial record."""
    from pathlib import Path
    from research_cloud.training import dataset_input
    old = json.load(open(receipt))
    if old.get("mode") != "formal" or old.get("group") != group or not old.get("all_checks_pass"):
        raise SystemExit(f"baseline {group}: {receipt} is not a passed task 10-28 formal readback of {group}")
    o = old["run"]
    run, model = c.get_run(o["id"]), c.get_logged_model(old["logged_model"]["id"])
    ver = c.get_model_version(old["version"]["name"], old["version"]["version"])
    rm = c.get_registered_model(old["version"]["name"])
    with tempfile.TemporaryDirectory() as tmp:
        card = Path(c.download_artifacts(run.info.run_id, "model-card.md", tmp)).read_bytes()
    tags = {k: v for k, v in dict(run.data.tags).items() if not k.startswith("mlflow.log-model")}
    now = {"run": {"status": run.info.status, "name": run.info.run_name, "experiment_id": run.info.experiment_id, "n_metrics": len(run.data.metrics),
                   "tags": tags, "model_outputs": [x.model_id for x in (run.outputs.model_outputs if run.outputs else [])], "dataset_inputs": inputs(run)},
           "logged_model": {"id": model.model_id, "name": model.name, "experiment_id": model.experiment_id, "status": str(model.status),
                            "source_run_id": model.source_run_id},
           "version": {"name": ver.name, "version": ver.version, "status": str(ver.status), "run_id": ver.run_id, "source": ver.source},
           "card_sha256": hashlib.sha256(card).hexdigest(), "registered_model_aliases": dict(getattr(rm, "aliases", {}) or {})}
    gt = json.load(open(CH_TRIALS.format(g=group)))["trial"]
    rows = float(json.loads(o["authoritative_dataset"]["profile"])["num_rows"])
    got_m = {k: v for k, v in run.data.metrics.items() if not (k == dataset_input.MODEL_DATASET_METRIC and v == rows)}
    want_p = {k: str(v) for k, v in (gt.get("resolved_params") or {}).items() if len(str(v)) <= 6000}
    checks = {"metrics_equal_retained_trial": got_m == finite(gt.get("metrics")),
              "params_equal_retained_trial": dict(run.data.params) == want_p and dict(model.params or {}) == want_p,
              "run_unchanged": {k: now["run"][k] for k in ("status", "name", "experiment_id", "n_metrics", "tags", "model_outputs", "dataset_inputs")}
                               == {k: o[k] for k in ("status", "name", "experiment_id", "n_metrics", "tags", "model_outputs", "dataset_inputs")},
              "logged_model_unchanged": now["logged_model"] == old["logged_model"],
              "version_unchanged": now["version"] == old["version"],
              "card_unchanged": now["card_sha256"] == old["card_sha256"]["live"]}
    return {"mode": "baseline", "group": group, "receipt": receipt, "receipt_sha256": sha(receipt), "now": now,
            "run": {"id": o["id"], "name": run.info.run_name, "experiment_id": run.info.experiment_id,
                    "authoritative_dataset": o["authoritative_dataset"]},
            "anchors": {"run_id": o["id"], "model_id": old["logged_model"]["id"], "registered_model": old["version"]["name"],
                        "model_version": old["version"]["version"]},
            "checks": checks, "all_checks_pass": all(checks.values())}


def formal(c, trial, group):
    import mlflow
    from pathlib import Path
    from research_cloud.packages.common import verify_package
    from research_cloud.training import dataset_input, model_metadata
    from research_cloud.training.publication import dashboard_experiment
    mlflow.set_tracking_uri(URI)        # models:/<id> resolution uses the process default store (see module note)
    mlflow.set_registry_uri(URI)
    pub = json.load(open(os.path.join(trial, "publication.json")))
    t = pub.get("trial") or json.load(open(os.path.join(trial, "trial.json")))
    h, g = group_of(t)
    if g != group or pub.get("status") != "complete":
        raise SystemExit(f"trial is {g} (publication {pub.get('status')}), not a complete {group}")
    cfg = t["config"]
    render = json.load(open(os.path.join(RENDER, f"publication-{g}.json")))
    render_card = open(os.path.join(RENDER, f"model-card-{g}.md")).read()
    exp = dashboard_experiment(c, DASHBOARD)
    run, model = c.get_run(pub["run_id"]), c.get_logged_model(pub["model_id"])
    ver = c.get_model_version(pub["registered_model"], pub["model_version"])
    rt, mt, vt = dict(run.data.tags), dict(model.tags), dict(ver.tags)
    from research_cloud.training.publication import names
    expected_names = names(cfg["model_card"], h, pub["identity"])
    if TITLE not in expected_names[0]:
        raise SystemExit(f"{g}: the recipe display title is not the origin-ablation title")
    out = {"mode": "formal", "group": g, "experiment": {"id": exp.experiment_id, "name": exp.name},
           "run": {"id": run.info.run_id, "experiment_id": run.info.experiment_id, "status": run.info.status, "name": run.info.run_name,
                   "n_metrics": len(run.data.metrics), "tags": {k: v for k, v in rt.items() if not k.startswith("mlflow.log-model")},
                   "model_outputs": [o.model_id for o in (run.outputs.model_outputs if run.outputs else [])],
                   "dataset_inputs": inputs(run)},
           "logged_model": {"id": model.model_id, "name": model.name, "experiment_id": model.experiment_id, "status": str(model.status),
                            "source_run_id": model.source_run_id},
           "version": {"name": ver.name, "version": ver.version, "status": str(ver.status), "run_id": ver.run_id, "source": ver.source}}
    with tempfile.TemporaryDirectory() as tmp:
        # byte-exact (no text-mode newline/encoding normalisation): expected bytes are the deterministic UTF-8 encoding
        card_bytes = Path(c.download_artifacts(run.info.run_id, "model-card.md", tmp)).read_bytes()
        _, regenerated = model_metadata.build(t, Path(trial) / "package", run.info.run_id, model.model_id)
        fo = c.download_artifacts(run.info.run_id, "metadata/feature_order.csv", tmp)
        pkg = mlflow.artifacts.download_artifacts(artifact_uri=f"models:/{model.model_id}", dst_path=os.path.join(tmp, "pkg"), tracking_uri=URI)
        out["card_matches_local"] = card_bytes == regenerated.encode("utf-8")
        out["card_sha256"] = {"live": hashlib.sha256(card_bytes).hexdigest()}
        ids = {"<run_id>": run.info.run_id, "<model_id>": model.model_id}      # the render's placeholders -> actual ids
        live = sections(card_bytes.decode("utf-8"))
        offline = sections(re.sub("<run_id>|<model_id>", lambda m: ids[m.group(0)], render_card))
        out["card_recipe_sections_differing"] = [k for k in RECIPE_SECTIONS if live.get(k) != offline.get(k)]
        out["feature_order_equals_package"] = open(fo).read() == open(os.path.join(trial, "package", "deps", "feature_order.csv")).read()
        out["downloaded_package"] = {"sha256": sha(os.path.join(pkg, "package.json")), "problems": verify_package(pkg),
                                     "contexts": json.load(open(os.path.join(pkg, "package.json")))["routing"]["contexts"]}
    out["artifacts_root"] = sorted(a.path for a in c.list_artifacts(run.info.run_id))
    panel = dataset_input.payload(trial, t)
    auth = [d for d in out["run"]["dataset_inputs"] if d["name"] == panel["dataset"]["name"]]
    out["run"]["authoritative_dataset"] = auth[0] if len(auth) == 1 else None
    rd = render["dataset_input"]
    out["dataset_vs_render_differing"] = ([k for k in ("name", "digest", "schema", "profile") if panel["dataset"][k] != rd["dataset"][k]]
                                          + [f"tag:{k}" for k in sorted(set(panel["input_tags"]) | set(rd["input_tags"]))
                                             if k not in GENERATION_TAGS and panel["input_tags"].get(k) != rd["input_tags"].get(k)])
    want_tags = {k: re.sub("<run_id>|<model_id>", lambda m: ids[m.group(0)], v) for k, v in render["tags"].items() if k != "mlflow.note.content"}
    out["tags_vs_render_differing"] = [k for k, v in want_tags.items() if any(x.get(k) != v for x in (rt, mt, vt))]
    rows = float(json.loads(panel["dataset"]["profile"])["num_rows"])
    got_m = {k: v for k, v in run.data.metrics.items() if not (k == dataset_input.MODEL_DATASET_METRIC and v == rows)}
    want_p = {k: str(v) for k, v in (t.get("resolved_params") or {}).items() if len(str(v)) <= 6000}
    ents = (rt, mt, vt)
    checks = {
        "run_finished_model_ready_version_ready": run.info.status == "FINISHED" and str(model.status).endswith("READY") and str(ver.status).endswith("READY"),
        "in_dashboard": run.info.experiment_id == exp.experiment_id == model.experiment_id,
        "links": model.source_run_id == run.info.run_id == ver.run_id and ver.source == f"models:/{model.model_id}",
        "run_model_output": out["run"]["model_outputs"] == [model.model_id],
        "names": (ver.name == expected_names[2] == pub["registered_model"] == render["names"]["registered_model"]
                  and run.info.run_name == expected_names[0] == render["names"]["run"] and model.name == expected_names[1] == render["names"]["logged_model"]),
        "version_1": str(ver.version) == "1",
        "code_overlay_tag": all(x.get("provenance.code_overlay") == cfg["provenance_tags"]["provenance.code_overlay"] for x in ents),
        "publication_tags": all(x.get("publication.status") == "complete" and x.get("package.json_sha256") == pub["package.json_sha256"] for x in ents),
        "arm_tags": all(x.get("arm") == ARM and x.get("lead_months") == f"{h:02d}" and x.get("arm_role") == "candidate"
                        and x.get("family") == "ipcch_validity_pooled" and x.get("family_title") == TITLE for x in ents),
        "baseline_link_tags": all(x.get("baseline.run_id") == cfg["baseline"]["run_id"] == cfg["origin_ablation"]["ch_baseline"]["run_id"]
                                  and x.get("baseline.arm") == cfg["baseline"]["arm"] for x in ents),
        "freeze_and_data_tags": all(x.get("provenance.hpt_freeze_sha256") == cfg["frozen"]["freeze_sha256"]
                                    and x.get("provenance.data_version") == cfg["ch_correction"]["data_version"]
                                    and x.get("provenance.ch_links") == cfg["provenance_tags"]["provenance.ch_links"]
                                    and x.get("provenance.fit_labels") == cfg["provenance_tags"]["provenance.fit_labels"]
                                    and x.get("provenance.origin_ablation") == cfg["provenance_tags"]["provenance.origin_ablation"] for x in ents),
        "tags_equal_render": not out["tags_vs_render_differing"],
        "image_commit": all(x.get("image_digest") == t["runtime"]["image_digest"] and x.get("source_commit") == t["runtime"]["source_commit"]
                            for x in ents),
        "report_and_origin_metrics_present": any(k.startswith("report.region.") for k in run.data.metrics)
                                             and any(k.startswith("origin.historical_pooled.") for k in run.data.metrics)
                                             and not any(k.startswith("common.") for k in run.data.metrics),
        "published_package_holdout_only": out["downloaded_package"]["contexts"] == [c for c in out["downloaded_package"]["contexts"] if "_supp_" in c] != [],
        "n_features": rt.get("n_features") == str(cfg["n_features"]) == str(WIDTH[h]) == str(sum(1 for _ in open(os.path.join(trial, "package", "deps", "feature_order.csv"))) - 1),
        "feature_order_equals_package": out["feature_order_equals_package"],
        "card_matches_local": out["card_matches_local"],
        "card_recipe_sections_equal_render": not out["card_recipe_sections_differing"],
        "no_card_correction_tags": all("card.correction" not in x and "publication.recovery_code" not in x for x in ents),
        "downloaded_package_matches": out["downloaded_package"]["sha256"] == pub["package.json_sha256"] == sha(os.path.join(trial, "package", "package.json"))
                                      and not out["downloaded_package"]["problems"],
        # equal manifests prove nothing about the local bytes: every local payload file is re-hashed against package.json
        "local_package_payload": not verify_package(os.path.join(trial, "package")),
        "one_dataset_input": len(out["run"]["dataset_inputs"]) == 1 and len(auth) == 1,
        "dataset_input_equals_payload": len(auth) == 1 and dataset_input.existing_match(run, panel) is True
                                        and auth[0]["source"] == panel["dataset"]["source"] and auth[0]["digest"] == panel["dataset"]["digest"],
        "dataset_input_equals_render": not out["dataset_vs_render_differing"],
        "model_dataset": dataset_input.model_dataset_check(model, panel)["ok"],
        "metrics_exact": got_m == finite(t.get("metrics")),
        "params_exact": dict(run.data.params) == want_p and dict(model.params or {}) == want_p,
        "gcs_only_not_in_mlflow": "gcs-only" not in out["artifacts_root"] and "annual-package" not in out["artifacts_root"],
    }
    out["checks"], out["all_checks_pass"] = checks, all(checks.values())
    if out["all_checks_pass"]:          # the UI expectation file exists only for a fully verified run
        os.makedirs(OUT_DIR, exist_ok=True)
        out["trial_metrics_path"] = os.path.join(OUT_DIR, f"metrics-{g}.json")      # the values proved equal above
        with open(out["trial_metrics_path"], "w") as f:
            json.dump(finite(t.get("metrics")), f, indent=1)
    return out


def main():
    """All requested readbacks in ONE process with ONE reader-secret access."""
    global OUT_DIR
    from mlflow.tracking import MlflowClient
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", action="append", required=True, help="MODE:GROUP:TRIAL_DIR|RECEIPT (formal|baseline), repeatable")
    ap.add_argument("--out-dir", default=OUT_DIR)
    a = ap.parse_args()
    out_dir = OUT_DIR = a.out_dir
    os.makedirs(out_dir, exist_ok=True)
    items = [x.split(":", 2) for x in a.item]
    for mode, group, _ in items:
        if mode not in ("formal", "baseline") or os.path.exists(os.path.join(out_dir, f"{mode}-{group}.json")):
            raise SystemExit(f"{mode}-{group}: unknown mode or existing receipt")
    version = reader()
    c = MlflowClient(tracking_uri=URI, registry_uri=URI)
    summary = {"reader_secret_version": version, "reader_accesses": 1, "items": {}}
    for mode, group, arg in items:
        try:
            rec = formal(c, arg, group) if mode == "formal" else baseline(c, arg, group)
        except Exception as e:
            rec = {"mode": mode, "group": group, "error": f"{type(e).__name__}: {e}", "checks": {}, "all_checks_pass": False, "run": {}}
        rec["reader_secret_version"] = version
        with open(os.path.join(out_dir, f"{mode}-{group}.json"), "w") as f:
            json.dump(rec, f, indent=1, default=str)
        summary["items"][f"{mode}-{group}"] = {"run": rec["run"].get("id"), "all_checks_pass": rec["all_checks_pass"],
                                               "failed": [k for k, v in rec["checks"].items() if not v], "error": rec.get("error")}
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))
    return 0 if all(v["all_checks_pass"] for v in summary["items"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
