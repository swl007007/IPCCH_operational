import hashlib, json, sys
from pathlib import Path
from google.cloud import storage
sys.path.insert(0, str(next(p for p in Path(__file__).resolve().parents if (p / ".trellis").is_dir())))  # repository root
from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES
from cloud.orchestrator.prepare import PREPARE_SCHEMA_VERSION
prepare_id, assets, cutoff = sys.argv[1:4]
refresh = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
BUCKET = "manuel-remote-sensing-oct-delivery-debug"; ROOT = f"gs://{BUCKET}"
client = storage.Client(project="manuel-remote-sensing"); bucket = client.bucket(BUCKET)
def ref(uri):
    blob = bucket.get_blob(uri.removeprefix(ROOT + "/")); data = blob.download_as_bytes()
    return {"uri": uri, "generation": str(blob.generation), "sha256": hashlib.sha256(data).hexdigest()}
body = {"schema_version": PREPARE_SCHEMA_VERSION, "prepare_id": prepare_id, "origin_month": "2026-10", "cutoff_utc": cutoff,
        "extraction_contract_version": EXTRACTION_CONTRACT_VERSION, "operator": "executor wR:p3 (task debug)",
        "systems": {s: {"geometry": ref(f"{assets}/{s}/geometry.geojson"), "roster": ref(f"{assets}/{s}/roster.csv"),
                        "history": {f: ref(f"{assets}/{s}/history/{f}.csv") for f in SYSTEM_FAMILIES[s]}}
                    for s in ("fewsnet", "ipcch")}}
if refresh: body["refresh_from"] = refresh
raw = json.dumps(body, indent=2, sort_keys=True).encode()
blob = bucket.blob(f"prepare_requests/{prepare_id}/prepare_request.json")
blob.upload_from_string(raw, if_generation_match=0, content_type="application/json")
print(json.dumps({"uri": f"{ROOT}/prepare_requests/{prepare_id}/prepare_request.json", "generation": str(blob.generation),
                  "sha256": hashlib.sha256(raw).hexdigest()}))
