"""D18: build the October confidence rerun request from the accepted October final request.

Usage (from anywhere, lock-built venv with google-cloud-storage):
  python oct_confidence_make_request.py --image URI@sha256:D [--execute] [--submit]

* Starts from the archived October final request ``oct-final-20261008a`` (sha256-checked) and keeps
  every reference byte-for-byte: prepared snapshot ``full-window-20261008c``, ACLED/WFP keep retained
  snapshots, assets, package manifests, contracts, origin 2026-10, release namespace.
* Strictly required changes for a new runtime + the new baseline evidence: ``run_id``, ``runtime``
  (new image, new environment manifest), each model's ``acceptance_report`` (its body binds the
  runtime), all 15 ``diagnostics`` (now available, pointing at the new baseline evidence objects),
  ``operator`` and ``prepared_at``.
* ``--execute`` uploads the adjunct objects create-only under ``staging/<run_id>/`` of the existing
  October debug bucket (environment, six acceptance reports, nine evidence CSVs). Without it nothing
  is written to the cloud and placeholders are not produced: the script stops after the dry checks.
* ``--submit`` uploads the request create-only to the trigger bucket. That starts the Eventarc ->
  Workflow -> Cloud Run delivery; it is a separate, explicit operator action. ``--submit-built``
  submits the previously built local request (hash-checked against ``request-build.json``) without
  re-uploading adjuncts. Submit only after the job image AND the workflow ``DELIVERY_IMAGE_URI`` both
  equal ``--image`` (the job rejects a different ``--image-uri``).

Writes ``research/oct-confidence-request/{run_manifest.json, request-build.json}``.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
RESEARCH = HERE.parent
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
sys.path.insert(0, str(CP))
from cloud.orchestrator import delivery_job as dj  # noqa: E402
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from google.cloud import storage  # noqa: E402

PROJECT = "manuel-remote-sensing"
BUCKET = "manuel-remote-sensing-oct-delivery-debug"
REQUEST_BUCKET = "manuel-remote-sensing-oct-delivery-requests"
RUN_ID = "oct-confidence-20261009a"
OCT = (REPO / ".trellis/tasks/archive/2026-10/10-07-october-cloud-delivery/research/cp3_evidence/"
       "cloud_final_replay/run_manifest.json")
OCT_SHA = "0a519a265605bcefc9c6e70621d31d2f6e50542c88fc02194cab221fc9594c6a"
OUT = RESEARCH / "oct-confidence-request"
HASH_LIMIT = 200 * 1024 * 1024  # larger unchanged refs are checked for existence at generation only here
EXPECTED_CHANGES = {"run_id", "runtime", "operator", "prepared_at", "diagnostics"} | {
    f"models[{i}].acceptance_report" for i in range(6)}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split(uri: str) -> tuple[str, str]:
    bucket, name = uri[len("gs://"):].split("/", 1)
    return bucket, name


def diff_paths(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            sub = f"{path}.{key}" if path else key
            out += [sub] if key not in a or key not in b else diff_paths(a[key], b[key], sub)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in diff_paths(x, y, f"{path}[{i}]")]
    return [] if a == b else [path]


def submit_built(image: str) -> int:
    record = json.loads((OUT / "request-build.json").read_text())
    raw = (OUT / "run_manifest.json").read_bytes()
    if sha(raw) != record["request_sha256"] or record.get("submitted") or record["image_uri"] != image:
        raise SystemExit("built request does not match request-build.json, was already submitted, or names another image")
    request = json.loads(raw)
    dm.validate_delivery_request(request, request_uri=record["request_uri"], request_generation="1",
                                 expected_release_namespace="oct-staging")
    blob = storage.Client(project=PROJECT).bucket(REQUEST_BUCKET).blob(f"requests/{RUN_ID}/run_manifest.json")
    blob.upload_from_string(raw, if_generation_match=0, content_type="application/json")
    blob.reload()
    record["submitted"] = {"uri": record["request_uri"], "generation": str(blob.generation), "sha256": sha(raw),
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (OUT / "request-build.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record["submitted"], indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--submit-built", action="store_true")
    args = parser.parse_args()
    if args.submit_built:
        return submit_built(args.image)
    if "@sha256:" not in args.image:
        raise SystemExit("--image must be digest-pinned")
    if args.submit and not args.execute:
        raise SystemExit("--submit requires --execute")

    october_bytes = OCT.read_bytes()
    if sha(october_bytes) != OCT_SHA:
        raise SystemExit("archived October final request bytes changed")
    october = json.loads(october_bytes)
    baseline = json.loads((CP / "bootstrap/baseline.json").read_bytes())
    baseline_sha = sha((CP / "bootstrap/baseline.json").read_bytes())
    client = storage.Client(project=PROJECT)
    report = {"run_id": RUN_ID, "image_uri": args.image, "october_request": {"path": str(OCT.relative_to(REPO)),
              "sha256": OCT_SHA}, "baseline_sha256": baseline_sha, "execute": args.execute, "submit": args.submit}

    # 1. every reference kept from the October request must still exist at its pinned generation
    kept = []
    validated_october = dm.validate_delivery_request(
        october, request_uri=f"gs://{REQUEST_BUCKET}/requests/{october['run_id']}/run_manifest.json",
        request_generation="1791484415757028")
    for field, ref in dm.iter_object_refs(validated_october):
        if field.endswith(".acceptance_report") or field.startswith("diagnostics") or field.startswith("runtime"):
            continue  # replaced below
        bucket, name = split(ref["uri"])
        blob = client.bucket(bucket).get_blob(name, generation=int(ref["generation"]))
        if blob is None:
            raise SystemExit(f"{field}: {ref['uri']}#{ref['generation']} no longer exists")
        entry = {"field": field, "uri": ref["uri"], "generation": ref["generation"], "size": blob.size}
        if blob.size <= HASH_LIMIT:
            actual = sha(blob.download_as_bytes())
            if actual != ref["sha256"]:
                raise SystemExit(f"{field}: sha256 mismatch at pinned generation")
            entry["check"] = "sha256_downloaded_equal"
        else:
            entry["check"] = "exists_at_generation_only (the job verifies sha256)"
        kept.append(entry)
    report["kept_reference_checks"] = kept
    print(f"kept refs verified: {len(kept)}", flush=True)

    # 2. local evidence bytes = baseline inventory
    evidence = {}
    for entry in baseline["delivery"]["diagnostics"]:
        if entry["status"] != "available":
            raise SystemExit(f"baseline declaration not available: {entry}")
        local = entry["evidence"]["local_path"]
        data = (CP / "bootstrap" / local).read_bytes()
        if sha(data) != baseline["files"][local]["sha256"]:
            raise SystemExit(f"{local}: bytes differ from baseline inventory")
        evidence[local] = data
    if len(baseline["delivery"]["diagnostics"]) != 15:
        raise SystemExit("baseline must declare 15 diagnostics")

    lock = dj.lock_sha256()
    environment_body = json.dumps({"image_uri": args.image, "requirements_lock_sha256": lock}, sort_keys=True).encode()
    if lock != baseline["runtime"]["requirements_lock_sha256"]:
        raise SystemExit("requirements lock differs from the baseline runtime lock")
    if not args.execute:
        report["status"] = "dry_checks_passed_no_cloud_writes"
        OUT.mkdir(exist_ok=True)
        (OUT / "request-build.dry.json").write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps({k: report[k] for k in ("status", "image_uri", "baseline_sha256")}, indent=1))
        return 0

    bucket = client.bucket(BUCKET)
    stage = f"staging/{RUN_ID}"
    uploads = []

    def put(name: str, data: bytes) -> dict:
        blob = bucket.blob(f"{stage}/{name}")
        blob.upload_from_string(data, if_generation_match=0)  # create-only
        md5 = base64.b64encode(hashlib.md5(data).digest()).decode()
        blob.reload()
        if blob.md5_hash != md5 or blob.size != len(data):
            raise SystemExit(f"upload verification failed for {blob.name}")
        ref = {"uri": f"gs://{BUCKET}/{blob.name}", "generation": str(blob.generation), "sha256": sha(data)}
        uploads.append({**ref, "size": len(data)})
        return ref

    environment = put("environment.json", environment_body)
    runtime = {"image_uri": args.image, "environment_manifest": environment}
    request = copy.deepcopy(october)
    request["run_id"] = RUN_ID
    request["runtime"] = runtime
    for model in request["models"]:
        old = model["acceptance_report"]
        b, n = split(old["uri"])
        old_bytes = client.bucket(b).blob(n, generation=int(old["generation"])).download_as_bytes()
        if sha(old_bytes) != old["sha256"]:
            raise SystemExit(f"October acceptance report changed: {old['uri']}")
        body = json.loads(old_bytes)
        body["runtime"] = {"image_uri": args.image, "environment_manifest_sha256": environment["sha256"]}
        body["evidence"] = ("rebuilt runtime (current maintained source, unchanged requirements lock) for unchanged "
                            "package bytes; compatibility evidence = prediction equality with the accepted cloud run "
                            "oct-final-20261008a (image sha256:41944ea0...), checked after this run in "
                            ".trellis/tasks/10-09-sept-6m12m-confidence/research/october_confidence_check.json")
        model["acceptance_report"] = put(f"models/{model['system']}_{model['horizon_months']}m_acceptance.json",
                                         json.dumps(body, sort_keys=True).encode())
    refs = {local: put(local, data) for local, data in sorted(evidence.items())}
    request["diagnostics"] = [
        {"system": e["system"], "horizon_months": e["horizon_months"], "family": e["family"], "status": "available",
         "evidence": refs[e["evidence"]["local_path"]], "evidence_model_package_id": e["evidence_model_package_id"],
         "evidence_horizon_months": e["evidence_horizon_months"]}
        for e in baseline["delivery"]["diagnostics"]]
    request["operator"] = "executor (task 10-09-sept-6m12m-confidence, D18 confidence rerun)"
    request["prepared_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    uri = f"gs://{REQUEST_BUCKET}/requests/{RUN_ID}/run_manifest.json"
    dm.validate_delivery_request(request, request_uri=uri, request_generation="1",
                                 expected_release_namespace="oct-staging")
    changed = diff_paths(october, request)
    top = sorted({".".join(p.split(".")[:2]) if p.startswith("models[") else p.split(".")[0].split("[")[0]
                  for p in changed})
    if not set(top) <= EXPECTED_CHANGES:
        raise SystemExit(f"unexpected request changes {sorted(set(top) - EXPECTED_CHANGES)}")
    raw = json.dumps(request, indent=2, sort_keys=True).encode()
    OUT.mkdir(exist_ok=True)
    (OUT / "run_manifest.json").write_bytes(raw)
    report.update({"request_local": str((OUT / "run_manifest.json").relative_to(REPO)), "request_sha256": sha(raw),
                   "request_uri": uri, "uploads": uploads, "changed_paths": changed, "changed_top_level": top,
                   "unchanged_top_level": sorted(set(october) - {p.split(".")[0].split("[")[0] for p in changed})})
    if args.submit:
        blob = client.bucket(REQUEST_BUCKET).blob(f"requests/{RUN_ID}/run_manifest.json")
        blob.upload_from_string(raw, if_generation_match=0, content_type="application/json")
        blob.reload()
        report["submitted"] = {"uri": uri, "generation": str(blob.generation), "sha256": sha(raw),
                               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (OUT / "request-build.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report.get(k) for k in ("request_sha256", "request_uri", "changed_top_level", "submitted")},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
