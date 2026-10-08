"""Structurally valid STAGING delivery request for the Eventarc -> Workflows -> Cloud Run path (task evidence).

It pins real objects: full-roster assets (assets/full-20261008a), the v3 panels/references and the six
uploaded packages (debug inputs manifest), retained WFP/ACLED projections of exactly those panels,
the environment manifest of the staging image and acceptance reports bound to package manifest bytes,
feature schema and runtime. The prepared snapshot is the bounded smoke-local-20261008a (12 areas), so
the final path MUST reject it (prepared roster != delivery roster): this exercises readiness
rejection, duplicate and conflict handling, never a release.

Usage: python make_staging_request.py <run_id> <image_uri@sha256> <request_bucket> [--write-supporting]
"""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import storage

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from cloud.orchestrator import delivery_job as dj  # noqa: E402
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from cloud.orchestrator.causal_fill import FILL_POLICY_VERSION  # noqa: E402

run_id, image, request_bucket = sys.argv[1:4]
BUCKET = "manuel-remote-sensing-oct-delivery-debug"
STAGE = f"staging/{run_id}"
V3 = REPO / "Outcome/model_delivery/202609_h5/20260923_country_confidence_v3"
client = storage.Client(project="manuel-remote-sensing")
bucket = client.bucket(BUCKET)
inputs = json.loads(bucket.blob("delivery-inputs/v3-20261008a/manifests/debug-smoke-20261008a.json",
                                generation=1791476078241656).download_as_bytes())
files = inputs["files"]


def existing(name):
    blob = bucket.get_blob(name)
    digest = hashlib.sha256(blob.download_as_bytes()).hexdigest()
    return {"uri": f"gs://{BUCKET}/{name}", "generation": str(blob.generation), "sha256": digest}


def put(name, data: bytes):
    blob = bucket.blob(f"{STAGE}/{name}")
    blob.upload_from_string(data, if_generation_match=0)
    return {"uri": f"gs://{BUCKET}/{blob.name}", "generation": str(blob.generation),
            "sha256": hashlib.sha256(data).hexdigest()}


def put_file(name, path: Path):
    blob = bucket.blob(f"{STAGE}/{name}")
    blob.upload_from_filename(path, if_generation_match=0)
    return {"uri": f"gs://{BUCKET}/{blob.name}", "generation": str(blob.generation), "sha256": dj._stream_sha256(path)}


def contract(version, text):
    return {"version": version, "sha256": hashlib.sha256(text.encode()).hexdigest()}


environment = put("environment.json", json.dumps({"image_uri": image, "requirements_lock_sha256": dj.lock_sha256()},
                                                 sort_keys=True).encode())
runtime = {"image_uri": image, "environment_manifest": environment}
fews_suite = "local-202604-57cb3b981198-510375f58cd8"
models = []
for system in ("fewsnet", "ipcch"):
    for horizon in (0, 6, 12):
        if system == "fewsnet":
            prefix, package_id = f"fewsnet_package/{horizon}m/", f"{fews_suite}/{horizon}m"
            members = {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)}
            schema = json.loads((REPO / f"Outcome/fewsnet_partitioned_rf/model_artifacts/{fews_suite}/{horizon}m/"
                                 "training_report.json").read_text())["feature_schema_sha256"]
        else:
            prefix, package_id = "ipcch_package/", f"launch_2026_04_production_safe/scope_{horizon}m"
            members = {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)
                       and (k.startswith(f"{prefix}scope_{horizon}m/") or "/" not in k[len(prefix):])}
            schema = dj._stream_sha256(REPO / f"model_artifacts/launch_2026_04/scope_{horizon}m/feature_contract.csv")
        manifest = put(f"models/{system}_{horizon}m_package_manifest.json", json.dumps({
            "schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": system, "horizon_months": horizon,
            "package_id": package_id, "files": [{"path": path, **ref} for path, ref in sorted(members.items())]},
            sort_keys=True).encode())
        report = put(f"models/{system}_{horizon}m_acceptance.json", json.dumps({
            "schema_version": dj.ACCEPTANCE_REPORT_SCHEMA, "system": system, "horizon_months": horizon,
            "package_id": package_id, "status": "accepted", "package_manifest_sha256": manifest["sha256"],
            "feature_schema_sha256": schema,
            "runtime": {"image_uri": image, "environment_manifest_sha256": environment["sha256"]},
            "evidence": "staging only: supervisor frozen replays research/cp3_evidence/{fews_frozen_replay,"
                        "fews_product_window_replay,ipcch_wrapper_replay}"}, sort_keys=True).encode())
        models.append({"system": system, "horizon_months": horizon, "package_id": package_id,
                       "package_manifest": manifest, "acceptance_report": report, "feature_schema_sha256": schema})
history = {"fewsnet": str(V3 / "inputs/fewsnet_refreshed_raw.csv"), "ipcch": str(V3 / "inputs/ipcch_panel.csv")}
retained = {}
for family in ("wfp", "acled"):
    path = Path(f"/tmp/oct-staging-{run_id}-{family}.csv")
    with path.open("x", encoding="utf-8", newline="") as handle:
        for text in dj.retained_family_rows(history, family):
            handle.write(text)
    retained[family] = put_file(f"retained_{family}.csv", path)
converter = contract(dm.RAW_CONVERTER_CONTRACT_VERSION, (REPO / "tools/refresh_h5_inputs.py").read_text())
assets = {}
for system in ("fewsnet", "ipcch"):
    assets[system] = {"geometry": existing(f"assets/full-20261008a/{system}/geometry.geojson"),
                      "roster": existing(f"assets/full-20261008a/{system}/roster.csv"),
                      "population": files[f"{system}_country_population_reference.csv"],
                      "country_reference": files[f"{system}_country_population_reference.csv"],
                      "history_panel": files["fewsnet_refreshed_raw.csv" if system == "fewsnet" else "ipcch_panel.csv"]}
assets["ipcch"]["fixed_features"] = files["ipcch_april_panel.csv"]
request = {
    "schema_version": dm.SCHEMA_VERSION, "run_id": run_id, "origin_month": "2026-10",
    "systems": ["fewsnet", "ipcch"], "horizons_months": [0, 6, 12],
    "prepared_snapshot": {"prepare_id": "smoke-local-20261008a", "origin_month": "2026-10",
                          "manifest": inputs["prepared_manifest"]},
    "acled": {"action": "keep", "retained_snapshot": retained["acled"], "converter_contract": converter},
    "wfp": {"action": "keep", "retained_snapshot": retained["wfp"], "converter_contract": converter},
    "models": models, "assets": assets,
    "diagnostics": [{"system": s, "horizon_months": h, "family": f, "status": "unavailable", "evidence": None,
                     "reason": "missing_evidence"}
                    for s in dm.SYSTEMS for h in dm.HORIZONS_MONTHS for f in dm.DIAGNOSTIC_FAMILIES[s]],
    "contracts": {"feature": contract("feature-v1", "128-column contracts"), "fill": contract(FILL_POLICY_VERSION, "fill"),
                  "output": contract("september-v3-output-v1", "frozen headers"), "diagnostic": contract("diag-v1", "diag")},
    "runtime": runtime, "release": {"namespace": "oct-staging", "expected_pointer_generation": "0"},
    "operator": "executor wR:p3 (staging negative path)",
    "prepared_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
raw = json.dumps(request, indent=2, sort_keys=True).encode()
uri = f"gs://{request_bucket}/requests/{run_id}/run_manifest.json"
dm.validate_delivery_request(request, request_uri=uri, request_generation="1", expected_release_namespace="oct-staging")
local = Path(f"/tmp/oct-staging-{run_id}-run_manifest.json")
local.write_bytes(raw)
print(json.dumps({"request_local": str(local), "request_uri": uri, "sha256": hashlib.sha256(raw).hexdigest()}))
