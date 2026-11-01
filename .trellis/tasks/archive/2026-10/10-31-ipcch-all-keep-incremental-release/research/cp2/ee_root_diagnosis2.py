"""Task 10-31: bounded READ-ONLY re-check with the local EE credentials: HTTP status/body behind EEException
(__context__) for the feisty root listing/metadata, and the EE caller identity via Google tokeninfo (token never
printed or saved; only email/scope/audience fields kept). No create, write or ACL call."""
import json, sys
import ee, requests
ee.Initialize(project="feisty-flames-511718-d4")
FE = "projects/feisty-flames-511718-d4/assets"
def detail(fn):
    try:
        return {"ok": True, "result": fn()}
    except Exception as exc:
        ctx = exc.__context__ or exc.__cause__
        resp = getattr(ctx, "resp", None)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "http_status": getattr(resp, "status", None),
                "http_body": (getattr(ctx, "content", b"") or b"").decode("utf-8", "replace")[:1500] if ctx is not None else None,
                "context_type": type(ctx).__name__ if ctx is not None else None}
out = {"listAssets_feisty_root": detail(lambda: ee.data.listAssets({"parent": FE, "pageSize": 5})),
       "getAsset_feisty_root": detail(lambda: ee.data.getAsset(FE))}
ident = {"source": "oauth2 tokeninfo of the EE session credentials (token not recorded)"}
try:
    creds = ee.data.get_persistent_credentials() if hasattr(ee.data, "get_persistent_credentials") else ee.data._credentials
    import google.auth.transport.requests as gr
    if not getattr(creds, "token", None):
        creds.refresh(gr.Request())
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token}, timeout=30)
    info = r.json()
    ident.update({"http_status": r.status_code, **{k: info.get(k) for k in ("email", "email_verified", "scope", "aud", "azp")}})
except Exception as exc:
    ident["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
out["caller_identity"] = ident
json.dump(out, open(sys.argv[1], "x"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str)[:3000])
