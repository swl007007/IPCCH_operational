"""One retry of the D18 confidence rerun under a new run ID (run ``oct-confidence-20261009a`` failed only at
the release-pointer precheck: its request copied ``expected_pointer_generation: "0"`` from the October final
request although ``oct-staging/current.json`` already exists).

Usage: python oct_confidence_retry_request.py --run-id oct-confidence-20261009b [--submit]

Starts from the submitted run-a request (sha256-checked) and changes only ``run_id``, ``prepared_at`` and
``release.expected_pointer_generation`` (read now from the live pointer). Every pinned reference - including
the run-a environment, acceptance reports and evidence objects - is reused unchanged. ``--submit`` uploads the
request create-only to the trigger bucket (starts the delivery).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "cloud_pipeline"))
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from google.cloud import storage  # noqa: E402

PROJECT = "manuel-remote-sensing"
BUCKET = "manuel-remote-sensing-oct-delivery-debug"
REQUEST_BUCKET = "manuel-remote-sensing-oct-delivery-requests"
RUN_A = HERE.parent / "oct-confidence-request/run_manifest.json"
RUN_A_SHA = "56171953ed3fa0490718ada659e3fb0d080aa56446ec7bb6d678cd36e95f5c38"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    raw_a = RUN_A.read_bytes()
    if hashlib.sha256(raw_a).hexdigest() != RUN_A_SHA:
        raise SystemExit("run-a request bytes changed")
    client = storage.Client(project=PROJECT)
    pointer = client.bucket(BUCKET).get_blob("oct-staging/current.json")
    pointer_body = json.loads(pointer.download_as_bytes(if_generation_match=pointer.generation))
    request = copy.deepcopy(json.loads(raw_a))
    request["run_id"] = args.run_id
    request["release"]["expected_pointer_generation"] = str(pointer.generation)
    request["prepared_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    uri = f"gs://{REQUEST_BUCKET}/requests/{args.run_id}/run_manifest.json"
    dm.validate_delivery_request(request, request_uri=uri, request_generation="1",
                                 expected_release_namespace="oct-staging")
    a = json.loads(raw_a)
    changed = sorted(k for k in set(a) | set(request) if a.get(k) != request.get(k))
    if changed != ["prepared_at", "release", "run_id"] or {k: v for k, v in a["release"].items()
                                                            if k != "expected_pointer_generation"} != \
            {k: v for k, v in request["release"].items() if k != "expected_pointer_generation"}:
        raise SystemExit(f"unexpected changes {changed}")
    raw = json.dumps(request, indent=2, sort_keys=True).encode()
    out = HERE.parent / f"oct-confidence-request/{args.run_id}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "run_manifest.json").write_bytes(raw)
    record = {"run_id": args.run_id, "from_request": {"path": str(RUN_A.relative_to(REPO)), "sha256": RUN_A_SHA},
              "pointer_at_build": {"uri": f"gs://{BUCKET}/oct-staging/current.json",
                                   "generation": str(pointer.generation), "body": pointer_body},
              "changed_top_level": changed, "request_uri": uri, "request_sha256": hashlib.sha256(raw).hexdigest()}
    if args.submit:
        blob = client.bucket(REQUEST_BUCKET).blob(f"requests/{args.run_id}/run_manifest.json")
        blob.upload_from_string(raw, if_generation_match=0, content_type="application/json")
        blob.reload()
        record["submitted"] = {"uri": uri, "generation": str(blob.generation),
                               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (out / "request-build.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
