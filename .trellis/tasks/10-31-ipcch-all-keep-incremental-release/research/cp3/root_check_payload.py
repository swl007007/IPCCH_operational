"""Task 10-31 D5/CP3 root check, run as `python3 -c <this file>` in image acc3e467 under monthly-runtime.

Exact root projects/feisty-flames-511718-d4/assets/. Bounds:
- ONE absolute deadline is fixed at main entry, 240 s ahead (the job timeout is 300 s).
- No request starts with less than 5 s left.
- SDK retries are 0 from BEFORE Initialize (state is preserved by data.initialize, so discovery and getAlgorithms are
  built with num_retries=0).
- Every HTTP socket operation, including Initialize's discovery and getAlgorithms, goes through the public
  Initialize(http_transport=httplib2.Http(timeout=40)).
0. Identity gate: the metadata-server email must equal monthly-runtime@…; a mismatch or metadata error stops before any
   Earth Engine call.
1. listAssets(parent=root, pageSize=1). Success means listable, and nothing is created.
2. Only if step 1 is HTTP 404: ONE createAsset({"type": "FOLDER"}, root). This is the documented
   `earthengine create folder projects/P/assets/` mapping. Success means created; HTTP 409 means already exists, so
   only readback follows; any other result stops.
3. After a create or a 409: re-list the root; it must succeed.
4. Pinned product transport: EETransport.missing_assets([absent child]) must return exactly [child].
Any other error, permission or timeout stops before further calls (exit 2). Nothing is overwritten, no IAM, billing
or registration call is made, and no scientific data or export is produced. Runtime identity comes from the metadata
server. The result is printed as one line: IPCCH_ROOT_CHECK {json}.
"""

import json
from datetime import datetime, timedelta, timezone

PROJECT = "feisty-flames-511718-d4"
ROOT = f"projects/{PROJECT}/assets/"
LIST_PARENT = f"projects/{PROJECT}/assets"
CHILD = ROOT + "IPCCH_ROOT_CHECK_ABSENT_20261101"
EXPORT_ROOT = "gs://food-crisis-test-ipcch-data/ipcch-v2/exports"
EXPECTED_IDENTITY = "monthly-runtime@feisty-flames-511718-d4.iam.gserviceaccount.com"


def http_status(exc):
    """HTTP status of an SDK error: the EEException keeps the googleapiclient HttpError as __context__."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        resp = getattr(exc, "resp", None)
        if resp is not None and getattr(resp, "status", None) is not None:
            return int(resp.status)
        exc = exc.__context__ or exc.__cause__
    return None


def http_body(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        content = getattr(exc, "content", None)
        if content:
            return (content.decode("utf-8", "replace") if isinstance(content, bytes) else str(content))[:1000]
        exc = exc.__context__ or exc.__cause__
    return None


BUDGET_SECONDS = 240          # whole check from main entry; the job timeout is 300 s
CALL_SECONDS = 40             # httplib2 socket timeout for every Earth Engine HTTP operation
MIN_START_SECONDS = 5


def call(result, name, fn, budget=None):
    started = datetime.now(timezone.utc).isoformat()
    left = budget() if budget else None
    if left is not None and left < MIN_START_SECONDS:      # never start a call that could outlive the job
        step = {"step": name, "ok": False, "started": started, "error": "budget exhausted; not started",
                "http_status": None, "http_body": None, "not_started": True}
        result["steps"].append(step)
        return step
    try:
        value = fn()
        step = {"step": name, "ok": True, "started": started, "result": value}
    except Exception as exc:                                   # classified below; never retried
        step = {"step": name, "ok": False, "started": started, "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                "http_status": http_status(exc), "http_body": http_body(exc)}
    result["steps"].append(step)
    return step


def identity_ok(identity):
    return identity.get("metadata_server_email") == EXPECTED_IDENTITY and "metadata_server_error" not in identity


def run(api, transport_absent, identity, budget=None):
    """Decision logic (injectable). Returns (exit_code, result). ``budget()`` -> remaining seconds (None = unbounded)."""
    result = {"identity": identity, "root": ROOT, "steps": [], "created": False, "branch": None, "passed": False}
    if not identity_ok(identity):                              # never act on the root under an unproven identity
        result["branch"] = "stop_identity"
        return 2, result
    first = call(result, "list_root", api.list_root, budget)
    if first["ok"]:
        result["branch"] = "listable_no_create"
    elif first["http_status"] == 404:
        create = call(result, "create_root_folder", api.create_root, budget)  # the ONLY mutation, at most once
        if create["ok"]:
            result["branch"], result["created"] = "created", True
        elif create["http_status"] == 409:
            result["branch"] = "already_exists_readback_only"
        else:
            result["branch"] = "stop_create_failed"
            return 2, result
        if not call(result, "relist_root", api.list_root, budget)["ok"]:
            result["branch"] += "+stop_relist_failed"
            return 2, result
    else:
        result["branch"] = "stop_list_failed"
        return 2, result
    absent = call(result, "transport_missing_assets_absent_child", lambda: transport_absent([CHILD]), budget)
    if not absent["ok"] or absent["result"] != [CHILD]:
        result["branch"] += "+stop_transport_absent_child"
        return 2, result
    result["passed"] = True
    return 0, result


def runtime_identity():
    import requests
    out = {}
    try:
        r = requests.get("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                         headers={"Metadata-Flavor": "Google"}, timeout=5)
        out["metadata_server_email"] = r.text.strip() if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception as exc:
        out["metadata_server_error"] = f"{type(exc).__name__}: {exc}"
    return out


def main():
    end = datetime.now(timezone.utc) + timedelta(seconds=BUDGET_SECONDS)     # the ONE absolute deadline
    budget = lambda: (end - datetime.now(timezone.utc)).total_seconds()
    identity = runtime_identity()
    if not identity_ok(identity):                              # before importing/initializing Earth Engine
        print("IPCCH_ROOT_CHECK " + json.dumps({"identity": identity, "branch": "stop_identity", "passed": False,
                                                "steps": []}, sort_keys=True), flush=True)
        raise SystemExit(2)
    import ee
    import google.auth
    import httplib2
    from google.cloud import storage

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform",
                                                 "https://www.googleapis.com/auth/earthengine"])
    identity["adc_service_account_email"] = getattr(credentials, "service_account_email", None)
    ee.data.setMaxRetries(0)                  # state only (no resource install), kept by data.initialize
    ee.Initialize(credentials=credentials, project=PROJECT, http_transport=httplib2.Http(timeout=CALL_SECONDS))
    ee.data.setMaxRetries(0)

    def bounded(fn):                          # retries 0; the socket timeout comes from the http_transport
        def go():
            ee.data.setMaxRetries(0)
            return fn()
        return go

    class Api:
        list_root = staticmethod(bounded(lambda: ee.data.listAssets({"parent": LIST_PARENT, "pageSize": 1})))
        create_root = staticmethod(bounded(lambda: ee.data.createAsset({"type": "FOLDER"}, ROOT)))

    def transport_absent(ids):
        from cloud.common.object_store import GCSObjectStore
        from cloud.ipcch.ee_transport import EETransport
        client = storage.Client(project=PROJECT)
        t = EETransport(ee=ee, client=client, store=GCSObjectStore(client), output_root=EXPORT_ROOT,
                        run_id="ipcch-ee-root-check-20261101", cleanup_reserve_seconds=1,
                        deadline_utc=end)            # the SAME absolute deadline fixed at main entry
        return t.missing_assets(ids)

    code, result = run(Api, transport_absent, identity, budget)
    result["budget_left_seconds"] = round(budget(), 1)
    print("IPCCH_ROOT_CHECK " + json.dumps(result, sort_keys=True, default=str), flush=True)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
