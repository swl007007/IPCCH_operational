"""D21: repoint the handover baseline to the confidence-rerun runtime image after its acceptance evidence passed.

Usage: python rebind_baseline_runtime.py --cloud-run JSON [--execute]

Gates: ``october_confidence_check.json`` passed (predictions equal the accepted smoke run) and the
relocated replay/cloud run recorded in ``build_october_fallback.json`` / ``--cloud-run`` passed.
Changes in ``cloud_pipeline/bootstrap/baseline.json`` (proved before writing): ``runtime.image_uri`` and, for
each of the six models, ``acceptance`` and ``environment``, replaced by the exact acceptance/environment
bodies that the rerun consumed (pinned GCS objects of the request, sha256-verified). Writes
``research/new-image-acceptance.json`` (the new image's acceptance evidence) and keeps the old baseline bytes
at ``research/baseline.before-runtime-rebind.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
RESEARCH = HERE.parent
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
sys.path.insert(0, str(CP))
from google.cloud import storage  # noqa: E402

BACKUP = RESEARCH / "baseline.before-runtime-rebind.json"
OLD_IMAGE_DIGEST = "sha256:41944ea048c559190b6018f30ad52695cf9bedbb7d5695abef50b1348616d034"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def serialize(baseline: dict, crlf: bool) -> bytes:
    text = json.dumps(baseline, indent=2, sort_keys=True) + "\n"
    return (text.replace("\n", "\r\n") if crlf else text).encode()


def read_pinned(client, ref: dict) -> bytes:
    bucket, name = ref["uri"][len("gs://"):].split("/", 1)
    data = client.bucket(bucket).blob(name, generation=int(ref["generation"])).download_as_bytes()
    if sha(data) != ref["sha256"]:
        raise SystemExit(f"{ref['uri']}#{ref['generation']} sha256 mismatch")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud-run", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    cloud_run = json.loads(Path(args.cloud_run).read_text())
    check = json.loads((RESEARCH / "october_confidence_check.json").read_text())
    fallback = json.loads((RESEARCH / "build_october_fallback.json").read_text())
    gates = {"comparison_passed": check["passed"], "replay_and_run_gates_passed": fallback["gates"]["passed"],
             "fallback_rebuilt_and_verified": fallback.get("fallback", {}).get("verified", False),
             "cloud_run_succeeded": cloud_run["run_status"]["status"] == "succeeded"}
    if not all(gates.values()):
        raise SystemExit(f"gates failed: {gates}")
    request = json.loads(Path(cloud_run["request_local"]).read_bytes())
    if sha(Path(cloud_run["request_local"]).read_bytes()) != cloud_run["run_status"]["request"]["sha256"]:
        raise SystemExit("local request bytes differ from the run's request")
    image = request["runtime"]["image_uri"]
    client = storage.Client(project="manuel-remote-sensing")
    environment_bytes = read_pinned(client, request["runtime"]["environment_manifest"])
    environment = json.loads(environment_bytes)
    if sha(json.dumps(environment, sort_keys=True).encode()) != request["runtime"]["environment_manifest"]["sha256"]:
        raise SystemExit("environment body is not canonical sort_keys JSON")
    acceptance = {}
    for model in request["models"]:
        data = read_pinned(client, model["acceptance_report"])
        body = json.loads(data)
        if sha(json.dumps(body, sort_keys=True).encode()) != model["acceptance_report"]["sha256"]:
            raise SystemExit("acceptance body is not canonical sort_keys JSON")
        acceptance[(model["system"], model["horizon_months"])] = (body, model["acceptance_report"])

    path = CP / "bootstrap/baseline.json"
    old_bytes = path.read_bytes()
    crlf = b"\r\n" in old_bytes
    old = json.loads(old_bytes)
    if serialize(old, crlf) != old_bytes:
        raise SystemExit("baseline.json serialization is not reproducible")
    if old["runtime"]["image_uri"].split("@")[-1] != OLD_IMAGE_DIGEST:
        raise SystemExit("baseline runtime is not the expected old image")
    new = json.loads(old_bytes)
    new["runtime"]["image_uri"] = image
    if new["runtime"]["requirements_lock_sha256"] != environment["requirements_lock_sha256"]:
        raise SystemExit("environment lock differs from the baseline runtime lock")
    for model in new["models"]:
        body, ref = acceptance[(model["system"], model["horizon_months"])]
        unchanged = {k: v for k, v in model["acceptance"].items() if k not in ("runtime", "evidence")}
        if unchanged != {k: v for k, v in body.items() if k not in ("runtime", "evidence")}:
            raise SystemExit(f"{model['system']}/{model['horizon_months']}m acceptance identity differs")
        model["acceptance"] = body
        model["environment"] = environment
    # prove the scope of the change
    changed = []

    def walk(a, b, p=""):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                walk(a.get(k), b.get(k), f"{p}.{k}" if p else k)
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{p}[{i}]")
        elif a != b:
            changed.append(p)
    walk(old, new)
    allowed = {"runtime.image_uri"} | {f"models[{i}].{f}" for i in range(6) for f in
                                       ("acceptance.runtime.image_uri", "acceptance.runtime.environment_manifest_sha256",
                                        "acceptance.evidence", "environment.image_uri")}
    if not set(changed) <= allowed:
        raise SystemExit(f"unexpected baseline changes {sorted(set(changed) - allowed)}")

    evidence = {
        "schema_version": "runtime-image-acceptance-evidence-v1",
        "image_uri": image, "previous_image_digest": OLD_IMAGE_DIGEST,
        "build": cloud_run.get("build"), "requirements_lock_sha256": environment["requirements_lock_sha256"],
        "environment_manifest": request["runtime"]["environment_manifest"],
        "acceptance_reports": {f"{s}/{h}m": ref for (s, h), (_, ref) in sorted(acceptance.items())},
        "method": "rerun of the accepted October cloud delivery inputs (prepared full-window-20261008c, ACLED/WFP "
                  "keep, same assets and package manifests) on the new image; every prediction/mapping/country "
                  "prediction table compared with the accepted smoke run oct-final-20261008a (image "
                  "sha256:41944ea0...) under the bundle comparator (IDs/discrete exact, continuous atol 1e-12, "
                  "rtol 0) plus relocated offline replay of the new bundle",
        "cloud_run": {k: cloud_run[k] for k in ("run_id", "execution", "request", "release") if k in cloud_run},
        "comparison": {"passed": check["passed"],
                       "prediction_tables_equal": sum(v["equal"] for v in check["predictions"].values()),
                       "prediction_tables": len(check["predictions"]),
                       "max_abs_diff": max(v["max_abs_diff"] for v in check["predictions"].values()),
                       "confidence_tables_passed": sum(v["passed"] for v in check["confidence"].values()),
                       "report": "research/october_confidence_check.json"},
        "replay": {"gates": fallback["gates"], "evidence": "cloud_pipeline/fallback/october_2026/replay_evidence/"},
        "baseline": {"before_sha256": sha(old_bytes), "after_sha256": sha(serialize(new, crlf)),
                     "changed_paths": changed},
    }
    print(json.dumps({"gates": gates, "changed_paths": len(changed), "after_sha256": evidence["baseline"]["after_sha256"]},
                     indent=1))
    if not args.execute:
        return 0
    if not BACKUP.exists():
        BACKUP.write_bytes(old_bytes)
    elif BACKUP.read_bytes() != old_bytes:
        raise SystemExit("an earlier different backup exists")
    path.write_bytes(serialize(new, crlf))
    if path.read_bytes() != serialize(new, crlf):
        raise SystemExit("baseline write verification failed")
    (RESEARCH / "new-image-acceptance.json").write_text(json.dumps(evidence, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
