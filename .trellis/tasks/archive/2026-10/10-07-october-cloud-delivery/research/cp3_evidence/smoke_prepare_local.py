"""Bounded live smoke of the CP2 preparation path from a local process (task evidence).

Real Earth Engine / GOSIF HTTP / GCS through the production CloudSourceAcquirer,
GCSObjectStore and GcsPinnedReader; plan + extract run in-process (run_prepare).
Usage: python smoke_prepare_local.py <prepare_id> <assets_prefix> <cutoff_utc> <workdir>
"""
import hashlib, json, sys, time
from pathlib import Path

import ee, requests
from google.cloud import storage

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES
from cloud.common.object_store import GCSObjectStore
from cloud.orchestrator import prepare

BUCKET = "manuel-remote-sensing-oct-delivery-debug"
ROOT = f"gs://{BUCKET}"
prepare_id, assets, cutoff, workdir = sys.argv[1:5]
client = storage.Client(project="manuel-remote-sensing")
bucket = client.bucket(BUCKET)


def ref(uri):
    blob = bucket.get_blob(uri.removeprefix(ROOT + "/"))
    data = blob.download_as_bytes()
    return {"uri": uri, "generation": str(blob.generation), "sha256": hashlib.sha256(data).hexdigest()}


systems = {
    system: {
        "geometry": ref(f"{assets}/{system}/geometry.geojson"),
        "roster": ref(f"{assets}/{system}/roster.csv"),
        "history": {family: ref(f"{assets}/{system}/history/{family}.csv") for family in SYSTEM_FAMILIES[system]},
    }
    for system in ("fewsnet", "ipcch")
}
body = json.dumps({
    "schema_version": prepare.PREPARE_SCHEMA_VERSION, "prepare_id": prepare_id, "origin_month": "2026-10",
    "cutoff_utc": cutoff, "extraction_contract_version": EXTRACTION_CONTRACT_VERSION, "systems": systems,
    "operator": "executor-smoke wR:p3",
}, indent=2, sort_keys=True).encode()
request_uri = f"{ROOT}/prepare_requests/{prepare_id}/prepare_request.json"
blob = bucket.blob(request_uri.removeprefix(ROOT + "/"))
blob.upload_from_string(body, if_generation_match=0, content_type="application/json")
reader = prepare.GcsPinnedReader(client)
raw = reader.read_bytes(request_uri, str(blob.generation))
request = prepare.validate_prepare_request(json.loads(raw), request_uri=request_uri,
                                           request_generation=str(blob.generation),
                                           request_sha256=hashlib.sha256(raw).hexdigest())
ee.Initialize(project="manuel-remote-sensing")
store = GCSObjectStore(client)
acquirer = prepare.CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=store,
                                       output_root=ROOT, poll_seconds=20)
started = time.time()
Path(workdir).mkdir(parents=True, exist_ok=True)
manifest = prepare.run_prepare(request, store=store, reader=reader, acquirer=acquirer, output_root=ROOT,
                               workdir=Path(workdir))
print(json.dumps({"elapsed_seconds": round(time.time() - started, 1), "request": request["request"],
                  "families": {f: {k: v for k, v in d.items() if k not in ("history", "outputs")}
                               for f, d in manifest["families"].items()}}, indent=2, default=str))
