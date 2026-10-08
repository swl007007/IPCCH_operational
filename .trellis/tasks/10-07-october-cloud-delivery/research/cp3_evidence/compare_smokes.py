"""Compare two prepared snapshots keyed by (system, family, admin_code, month) (task evidence)."""
import io, json, sys
import numpy as np, pandas as pd
from google.cloud import storage

BUCKET = "manuel-remote-sensing-oct-delivery-debug"
left_id, right_id = sys.argv[1:3]
bucket = storage.Client(project="manuel-remote-sensing").bucket(BUCKET)
def read(prepare_id, rel):
    return bucket.blob(f"prepared/{prepare_id}/{rel}").download_as_bytes()
manifests = {pid: json.loads(read(pid, "prepared_manifest.json")) for pid in (left_id, right_id)}
report = {"left": left_id, "right": right_id, "families": {}}
for family, left in manifests[left_id]["families"].items():
    right = manifests[right_id]["families"][family]
    entry = {"provider_ids_equal": [(s["month"], s["provider_id"]) for s in left["sources"]] == [(s["month"], s["provider_id"]) for s in right["sources"]],
             "source_sha256_equal": [s["sha256"] for s in left["sources"]] == [s["sha256"] for s in right["sources"]],
             "band_names": [(s.get("band_names"), r.get("band_names")) for s, r in zip(left["sources"], right["sources"])], "systems": {}}
    for system in left["outputs"]:
        a = pd.read_csv(io.BytesIO(read(left_id, f"features/{system}/{family}.csv")), dtype={"admin_code": str, "month": str}).set_index(["admin_code", "month"]).sort_index()
        b = pd.read_csv(io.BytesIO(read(right_id, f"features/{system}/{family}.csv")), dtype={"admin_code": str, "month": str}).set_index(["admin_code", "month"]).sort_index()
        same_keys = a.index.equals(b.index) and list(a.columns) == list(b.columns)
        nulls_equal = bool(same_keys and (a.isna() == b.isna()).all().all())
        diff = float(np.nanmax(np.abs(a.to_numpy(float) - b.to_numpy(float)))) if same_keys and a.notna().any().any() else None
        entry["systems"][system] = {"rows": len(a), "keys_and_columns_equal": same_keys, "nulls_equal": nulls_equal, "max_abs_diff": diff}
    report["families"][family] = entry
print(json.dumps(report, indent=2))
