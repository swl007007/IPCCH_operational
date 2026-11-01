"""Task 10-31 failure diagnosis: READ-ONLY Earth Engine calls with the LOCAL OPERATOR's existing credentials
(NOT the runtime service account; no create/write/ACL change). Distinguishes whether the feisty asset root is
listable/readable for this identity, versus the han root, and how a nonexistent child id is reported."""
import json, sys
import ee
ee.Initialize(project="feisty-flames-511718-d4")
def attempt(label, fn):
    try:
        r = fn(); return {"label": label, "ok": True, "result": r if len(json.dumps(r, default=str)) < 4000 else str(r)[:4000]}
    except Exception as exc:
        return {"label": label, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
FE, HAN = "projects/feisty-flames-511718-d4/assets", "projects/han-sandbox-505315/assets"
child = FE + "/IPCCH_DIAG_NONEXISTENT_CHILD_20261101"
out = {"identity": "local operator Earth Engine credentials (read-only), NOT monthly-runtime",
       "calls": [attempt("getAsset feisty root", lambda: ee.data.getAsset(FE)),
                 attempt("listAssets feisty root", lambda: ee.data.listAssets({"parent": FE, "pageSize": 5})),
                 attempt("getAsset nonexistent feisty child", lambda: ee.data.getAsset(child)),
                 attempt("listAssets han root", lambda: {"n": len(ee.data.listAssets({"parent": HAN, "pageSize": 5}).get("assets", []))}),
                 attempt("getAssetRoots", lambda: ee.data.getAssetRoots())]}
json.dump(out, open(sys.argv[1], "x"), indent=1, default=str); print(json.dumps(out, indent=1, default=str)[:3500])
