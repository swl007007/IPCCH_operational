"""Read-only: list han-sandbox-505315 asset folder metadata (no compute, no export, no writes)."""
import json, sys, ee
out = {"init": None}
for proj in ("food-crisis-modeling-enso",):
    try:
        ee.Initialize(project=proj); out["init"] = proj; break
    except Exception as e:
        out.setdefault("init_errors", []).append(f"{proj}: {type(e).__name__}: {str(e)[:300]}")
if not out["init"]:
    print(json.dumps(out, indent=1)); sys.exit(1)
root = "projects/han-sandbox-505315/assets"
assets, token = [], None
try:
    while True:
        r = ee.data.listAssets({"parent": root, "pageSize": 1000, **({"pageToken": token} if token else {})})
        assets += r.get("assets", [])
        token = r.get("nextPageToken")
        if not token: break
    out["listed"] = len(assets)
    out["assets"] = [{k: a.get(k) for k in ("id", "type", "updateTime", "sizeBytes")} for a in assets]
except Exception as e:
    out["list_error"] = f"{type(e).__name__}: {str(e)[:500]}"
print(json.dumps(out, indent=1))
