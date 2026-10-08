"""Build an October delivery request from existing fixed assets and a succeeded full-roster preparation.

Usage: python oct-make-final-request.py <run_id> <image_uri@sha256> <request_bucket> <prepare_id>
"""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import storage

REPO = next(p for p in Path(__file__).resolve().parents if (p / ".trellis").is_dir())  # also works after task archival
sys.path.insert(0, str(REPO))
from cloud.orchestrator import delivery_job as dj  # noqa: E402
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from cloud.orchestrator.causal_fill import FILL_POLICY_VERSION  # noqa: E402

run_id, image, request_bucket, prepare_id = sys.argv[1:5]
BUCKET = "manuel-remote-sensing-oct-delivery-debug"
STAGE = f"staging/{run_id}"
WORK = Path(f"/tmp/oct-request-{run_id}")  # scratch: downloads + request written here
WORK.mkdir(exist_ok=False)
client = storage.Client(project="manuel-remote-sensing")
bucket = client.bucket(BUCKET)
downloader = dj.PinnedDownloader(client, WORK / "downloads")
inputs = json.loads(downloader.fetch({
    "uri": f"gs://{BUCKET}/delivery-inputs/v3-20261008a/manifests/debug-smoke-20261008a.json",
    "generation": "1791476078241656",
    "sha256": "1a48c2d6c0b7f5e1df2d15be14b3cfc41e80b4b0d547e0f08bc41a160328fee0"}).read_text())
files = inputs["files"]
prepared_blob = bucket.get_blob(f"prepared/{prepare_id}/prepared_manifest.json")
prepared_path = WORK / "prepared_manifest.json"
client.bucket(BUCKET).blob(prepared_blob.name, generation=prepared_blob.generation).download_to_filename(prepared_path)
prepared_doc = json.loads(prepared_path.read_text())
if prepared_doc.get("status") != "succeeded" or prepared_doc.get("prepare_id") != prepare_id:
    raise SystemExit(f"prepared snapshot {prepare_id} is not succeeded: {prepared_doc.get('status')}")
prepared_ref = {"uri": f"gs://{BUCKET}/{prepared_blob.name}", "generation": str(prepared_blob.generation),
                "sha256": dj._stream_sha256(prepared_path)}


def existing(name):
    blob = bucket.get_blob(name)
    ref = {"uri": f"gs://{BUCKET}/{name}", "generation": str(blob.generation)}
    path = WORK / "assets" / name.replace("/", "_")
    path.parent.mkdir(parents=True, exist_ok=True)
    client.bucket(BUCKET).blob(name, generation=blob.generation).download_to_filename(path)
    return {**ref, "sha256": dj._stream_sha256(path)}


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
            schema = json.loads(downloader.fetch(members["training_report.json"]).read_text())["feature_schema_sha256"]
        else:
            prefix, package_id = "ipcch_package/", f"launch_2026_04_production_safe/scope_{horizon}m"
            members = {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)
                       and (k.startswith(f"{prefix}scope_{horizon}m/") or "/" not in k[len(prefix):])}
            schema = dj._stream_sha256(downloader.fetch(members[f"scope_{horizon}m/feature_contract.csv"]))
        manifest = put(f"models/{system}_{horizon}m_package_manifest.json", json.dumps({
            "schema_version": dj.PACKAGE_MANIFEST_SCHEMA, "system": system, "horizon_months": horizon,
            "package_id": package_id, "files": [{"path": path, **ref} for path, ref in sorted(members.items())]},
            sort_keys=True).encode())
        report = put(f"models/{system}_{horizon}m_acceptance.json", json.dumps({
            "schema_version": dj.ACCEPTANCE_REPORT_SCHEMA, "system": system, "horizon_months": horizon,
            "package_id": package_id, "status": "accepted", "package_manifest_sha256": manifest["sha256"],
            "feature_schema_sha256": schema,
            "runtime": {"image_uri": image, "environment_manifest_sha256": environment["sha256"]},
            "evidence": "supervisor frozen replays research/cp3_evidence/{fews_frozen_replay,"
                        "fews_product_window_replay,ipcch_wrapper_replay}"}, sort_keys=True).encode())
        models.append({"system": system, "horizon_months": horizon, "package_id": package_id,
                       "package_manifest": manifest, "acceptance_report": report, "feature_schema_sha256": schema})
history = {"fewsnet": str(downloader.fetch(files["fewsnet_refreshed_raw.csv"])),
           "ipcch": str(downloader.fetch(files["ipcch_panel.csv"]))}
retained = {}
for family in ("wfp", "acled"):
    path = WORK / f"retained_{family}.csv"
    with path.open("x", encoding="utf-8", newline="") as handle:
        for text in dj.retained_family_rows(history, family):
            handle.write(text)
    retained[family] = put_file(f"retained_{family}.csv", path)
converter = contract(dm.RAW_CONVERTER_CONTRACT_VERSION, "tools/refresh_h5_inputs.py converters")
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
    "prepared_snapshot": {"prepare_id": prepare_id, "origin_month": "2026-10", "manifest": prepared_ref},
    "acled": {"action": "keep", "retained_snapshot": retained["acled"], "converter_contract": converter},
    "wfp": {"action": "keep", "retained_snapshot": retained["wfp"], "converter_contract": converter},
    "models": models, "assets": assets,
    "diagnostics": [{"system": s, "horizon_months": h, "family": f, "status": "unavailable", "evidence": None,
                     "reason": "missing_evidence"}
                    for s in dm.SYSTEMS for h in dm.HORIZONS_MONTHS for f in dm.DIAGNOSTIC_FAMILIES[s]],
    "contracts": {"feature": contract("feature-v1", "128-column contracts"), "fill": contract(FILL_POLICY_VERSION, "fill"),
                  "output": contract("september-v3-output-v1", "frozen headers"), "diagnostic": contract("diag-v1", "diag")},
    "runtime": runtime, "release": {"namespace": "oct-staging", "expected_pointer_generation": "0"},
    "operator": "executor wR:p3 (task-scoped final path)",
    "prepared_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
raw = json.dumps(request, indent=2, sort_keys=True).encode()
uri = f"gs://{request_bucket}/requests/{run_id}/run_manifest.json"
dm.validate_delivery_request(request, request_uri=uri, request_generation="1", expected_release_namespace="oct-staging")
local = WORK / "run_manifest.json"
local.write_bytes(raw)
print(json.dumps({"request_local": str(local), "request_uri": uri, "sha256": hashlib.sha256(raw).hexdigest()}))
