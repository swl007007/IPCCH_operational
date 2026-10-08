"""Pinned inputs manifest for the CP3 debug cloud scoring of the smoke assembly (task evidence).

Every logical input names the exact uploaded object generation; the GCS CRC32C must equal the local
file's CRC32C (identical bytes; composite uploads carry no MD5) and the recorded SHA-256 is the local
file's (re-verified on every cloud download). The prepared snapshot is
smoke-local-20261008a (bounded 12-area remote smoke; not a full-roster preparation).

Usage: python make_debug_inputs_manifest.py <manifest-name>
"""
import base64, hashlib, json, sys
from pathlib import Path

from google.cloud import storage

REPO = Path(__file__).resolve().parents[5]
BUCKET = "manuel-remote-sensing-oct-delivery-debug"
PREFIX = "delivery-inputs/v3-20261008a"
V3 = REPO / "Outcome/model_delivery/202609_h5/20260923_country_confidence_v3"
FEWS = REPO / "Outcome/fewsnet_partitioned_rf/model_artifacts/local-202604-57cb3b981198-510375f58cd8"
IPCCH = REPO / "model_artifacts/launch_2026_04"
CACHE = Path("/tmp/oct-prepared-cache/smoke-local-20261008a/cache_index.json")

local = {"ipcch_panel.csv": V3 / "inputs/ipcch_panel.csv", "ipcch_april_panel.csv": V3 / "inputs/ipcch_april_panel.csv",
         "fewsnet_refreshed_raw.csv": V3 / "inputs/fewsnet_refreshed_raw.csv",
         **{f"{s}_country_population_reference.csv": V3 / f"{s}/country_population_reference.csv" for s in ("fewsnet", "ipcch")},
         **{f"{s}_polygons.geojson": V3 / f"{s}/polygons.geojson" for s in ("fewsnet", "ipcch")}}
for horizon in (0, 6, 12):
    for path in sorted((FEWS / f"{horizon}m").iterdir()):
        local[f"fewsnet_package/{horizon}m/{path.name}"] = path
for path in sorted(p for p in IPCCH.rglob("*") if p.is_file()):
    local[f"ipcch_package/{path.relative_to(IPCCH).as_posix()}"] = path


def digests(path):
    import google_crc32c

    sha, crc = hashlib.sha256(), google_crc32c.Checksum()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
            crc.update(block)
    return sha.hexdigest(), base64.b64encode(crc.digest()).decode()


client = storage.Client(project="manuel-remote-sensing")
bucket = client.bucket(BUCKET)
files = {}
for logical, path in sorted(local.items()):
    blob = bucket.get_blob(f"{PREFIX}/{logical}")
    if blob is None:
        raise SystemExit(f"not uploaded: {logical}")
    sha, crc = digests(path)
    if blob.crc32c != crc:
        raise SystemExit(f"uploaded bytes differ from local: {logical}")
    files[logical] = {"uri": f"gs://{BUCKET}/{blob.name}", "generation": str(blob.generation), "sha256": sha}
cache = json.loads(CACHE.read_text())["manifest"]
body = {"schema_version": "delivery-debug-inputs-v1", "prepared_manifest": cache, "files": files,
        "note": "smoke-local-20261008a bounded 12-area remote smoke; debug parity only, never a release"}
raw = json.dumps(body, indent=2, sort_keys=True).encode()
blob = bucket.blob(f"{PREFIX}/manifests/{sys.argv[1]}.json")
blob.upload_from_string(raw, if_generation_match=0, content_type="application/json")
print(json.dumps({"uri": f"gs://{BUCKET}/{blob.name}", "generation": str(blob.generation),
                  "sha256": hashlib.sha256(raw).hexdigest(), "files": len(files)}))
