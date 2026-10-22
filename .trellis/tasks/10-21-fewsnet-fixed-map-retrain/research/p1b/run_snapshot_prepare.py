"""Run the existing preparation in-process for the retrain release snapshot.

Reads the create-only prepare request at its exact generation, validates it with
validate_prepare_request, and executes cloud.orchestrator.prepare.run_prepare (plan +
extract) with the production CloudSourceAcquirer, GCSObjectStore and GcsPinnedReader.
Outputs (plan, sources, features, coverage, prepared_manifest, status) are written by the
existing code under gs://<bucket>/prepared/<prepare_id>/.

Usage: python run_snapshot_prepare.py --runtime-root <cloud_pipeline> --assets <assets_manifest.json>
"""
import argparse, hashlib, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_ROOT = "gs://food-crisis-test-ipcch-data"
DEADLINE = datetime(2026, 10, 22, 12, 45, tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime_root))
    import ee, requests
    from google.cloud import storage
    from cloud.common.object_store import GCSObjectStore
    from cloud.orchestrator.prepare import (CloudSourceAcquirer, GcsPinnedReader, run_prepare,
                                            validate_prepare_request)

    ref = json.loads(args.assets.read_text())["prepare_request"]
    client = storage.Client(project="feisty-flames-511718-d4")
    reader = GcsPinnedReader(client)
    raw = reader.read_bytes(ref["uri"], ref["generation"])
    if raw is None or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise SystemExit("prepare request missing or hash mismatch")
    request = validate_prepare_request(json.loads(raw), request_uri=ref["uri"],
                                       request_generation=ref["generation"],
                                       request_sha256=ref["sha256"])
    ee.Initialize(project="feisty-flames-511718-d4")
    acquirer = CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=GCSObjectStore(client),
                                   output_root=OUTPUT_ROOT, deadline_utc=DEADLINE)
    print("started", datetime.now(timezone.utc).isoformat(), flush=True)
    with tempfile.TemporaryDirectory() as workdir:
        manifest = run_prepare(request, store=GCSObjectStore(client), reader=reader, acquirer=acquirer,
                               output_root=OUTPUT_ROOT, workdir=Path(workdir))
    print("completed", datetime.now(timezone.utc).isoformat(), manifest["status"],
          {f: v["provider_latest_completed_month"] for f, v in manifest["families"].items()}, flush=True)


if __name__ == "__main__":
    main()
