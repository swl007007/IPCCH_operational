"""Task 10-31 CP2: READ-ONLY GCS witnesses (run under guarded.sh; split bases across invocations if needed).

climate MODE: for each given monthly climate base, the pre-run and post-run IMMUTABLE version contents named by the two
  inventories (HEAD content URI + sha): content sha re-verified; every pre (admin_code, month) row present after with
  byte-identical values (old keys preserved); new keys exactly {(roster admin, O)}; NaN count of the new month.
links MODE: batch manifest (pinned ref from readback_v2 post) -> every retained_inputs entry equals the post-run HEAD
  (version, sha256, HEAD generation); the delivery's ipcch fill-audit entry equals the batch feature_provenance sha.

usage: witness_readback.py climate INV_PRE INV_POST O OUT_JSON BASE [BASE...]
       witness_readback.py links POST_REAL_JSON INV_POST OUT_JSON
"""

import hashlib
import io
import json
import sys

import pandas as pd
from google.cloud import storage


def _bytes(client, uri, generation=None):
    b, _, n = uri.removeprefix("gs://").partition("/")
    blob = client.bucket(b).blob(n, generation=int(generation) if generation else None)
    return blob.download_as_bytes()


def _frame(data):
    return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)    # values compared as exact text


def climate(inv_pre, inv_post, origin, out, *bases):
    client = storage.Client()
    pre_t, post_t = json.load(open(inv_pre))["tables"], json.load(open(inv_post))["tables"]
    result = {}
    for base in bases:
        name = f"history__climate_month_{base}"
        a, b = pre_t[name], post_t[name]
        da, db = _bytes(client, a["content"]), _bytes(client, b["content"])
        r = {"pre_version": a["version"], "post_version": b["version"],
             "pre_sha_ok": hashlib.sha256(da).hexdigest() == a["content_sha256"],
             "post_sha_ok": hashlib.sha256(db).hexdigest() == b["content_sha256"]}
        fa, fb = _frame(da), _frame(db)
        del da, db
        key = ["admin_code", "month"]
        merged = fa.merge(fb, on=key, how="left", suffixes=("_pre", "_post"), indicator=True)
        cols = [c for c in fa.columns if c not in key]
        r["old_rows"] = int(len(fa))
        r["old_keys_missing_after"] = int((merged["_merge"] == "left_only").sum())
        r["old_values_changed"] = int(sum((merged[f"{c}_pre"] != merged[f"{c}_post"]).sum() for c in cols))
        new = fb.merge(fa[key], on=key, how="left", indicator=True)
        new = new[new["_merge"] == "left_only"]
        r["new_rows"] = int(len(new))
        r["new_months"] = sorted(new["month"].unique().tolist())
        r["new_admins"] = int(new["admin_code"].nunique())
        r["new_value_blank"] = int((new["value"] == "").sum()) if "value" in new else None
        r["new_method_ids"] = sorted(new["method_id"].unique().tolist()) if "method_id" in new else None
        r["passed"] = (r["pre_sha_ok"] and r["post_sha_ok"] and r["old_keys_missing_after"] == 0
                       and r["old_values_changed"] == 0 and r["new_months"] == [origin] and r["new_rows"] == r["new_admins"])
        result[base] = r
        del fa, fb, merged, new
    with open(out, "x") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print(json.dumps({b: {k: v[k] for k in ("passed", "old_rows", "new_rows", "new_months", "new_value_blank")}
                      for b, v in result.items()}, indent=1))
    return 0 if all(v["passed"] for v in result.values()) else 1


def links(post_real, inv_post, out):
    client = storage.Client()
    post = json.load(open(post_real))
    post_t = json.load(open(inv_post))["tables"]
    ref = post["batch"]["manifest_ref"]
    data = _bytes(client, ref["uri"], ref["generation"])
    assert hashlib.sha256(data).hexdigest() == ref["sha256"], "batch manifest bytes differ from the pinned ref"
    bman = json.loads(data)
    ret = bman.get("retained_inputs") or {}
    retained = {t: {"pinned": v, "post_head": {k: (post_t.get(t) or {}).get(k) for k in ("head_generation", "version", "content_sha256")},
                    "equal": bool(post_t.get(t)) and str(v.get("generation")) == str(post_t[t]["head_generation"])
                    and v.get("version") == post_t[t]["version"] and v.get("sha256") == post_t[t]["content_sha256"]}
                for t, v in sorted(ret.items())}
    dref = post["record"]["delivery"]["manifest"]
    dman = json.loads(_bytes(client, dref["uri"], dref["generation"]))
    audit = [e for e in dman["files"] if e["path"].endswith("ipcch_feature_fill_audit.csv")]
    fp = bman.get("feature_provenance") or {}
    body = {"batch_id": bman.get("batch_id"), "retained": retained,
            "retained_all_equal_post_heads": all(v["equal"] for v in retained.values()),
            "feature_provenance": fp, "delivery_fill_audit": audit,
            "fill_audit_equals_batch_provenance": len(audit) == 1 and audit[0]["sha256"] == fp.get("sha256")}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True)
    print(json.dumps({k: body[k] for k in ("batch_id", "retained_all_equal_post_heads", "fill_audit_equals_batch_provenance")}
                     | {"retained_tables": len(retained), "unequal": [t for t, v in retained.items() if not v["equal"]]}, indent=1))
    return 0 if body["retained_all_equal_post_heads"] and body["fill_audit_equals_batch_provenance"] else 1


if __name__ == "__main__":
    mode = sys.argv[1]
    raise SystemExit(climate(*sys.argv[2:6], *sys.argv[6:]) if mode == "climate" else links(*sys.argv[2:5]))
