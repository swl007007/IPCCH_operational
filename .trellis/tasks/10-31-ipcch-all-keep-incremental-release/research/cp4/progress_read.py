"""CP4 READ-ONLY durable progress of run RUN: objects written since SINCE under the real store, exports, run dir, locks;
plus each export task record's description/kind/state/task_id/asset_id (bounded listing; no writes)."""
import datetime, json, sys
from google.cloud import storage
RUN, SINCE, OUT = sys.argv[1], datetime.datetime.fromisoformat(sys.argv[2]), sys.argv[3]
c = storage.Client(); B = "food-crisis-test-ipcch-data"; out = {"objects": [], "tasks": []}
for pre in ("ipcch-v2/real/", f"ipcch-v2/exports/ipcch_exports/{RUN}/", f"runs/{RUN}/", "locks/", f"dispatch/{RUN}/", f"deliveries/{RUN}"):
    for b in c.list_blobs(B, prefix=pre):
        if b.updated >= SINCE:
            out["objects"].append([b.updated.strftime("%H:%M:%S"), b.name, b.size, str(b.generation)])
            if "/tasks/" in b.name and b.name.endswith(".json"):
                r = json.loads(b.download_as_bytes(if_generation_match=b.generation))
                out["tasks"].append({k: r.get(k) for k in ("description", "kind", "state", "task_id", "asset_id", "prefix")})
out["objects"].sort()
json.dump(out, open(OUT, "w"), indent=1)
print(len(out["objects"]), "objects;", len(out["tasks"]), "task records")
for t in out["tasks"]: print(" ", t["state"], t.get("kind") or "gcs", t["description"], (t.get("asset_id") or t.get("prefix") or "")[-60:])
for o in out["objects"]:
    if "/tasks/" not in o[1]: print(" ", o[0], o[1].replace("ipcch-v2/real/", "STORE/")[-90:])
