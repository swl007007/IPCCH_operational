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


BASES = ("prcp_anom", "prcp_z", "rainy_days", "cdd", "tmean_anom", "tmax_anom", "hot_days_p95", "gdd", "edd",
         "sm_z", "spi03", "spei03", "evi_anom")
KEPT = ["history__WFP_Price", "history__history_snapshot", "history__nino34_anom",
        "history__bbg_staple_food__composite_mean", "history__bbg_oilgas__composite_mean",
        "history__bbg_soybean_oil__composite_mean", "history__bbg_global_food__composite_mean",
        "history__food_price_index_WB", "history__idp_national", "history__idp_local", "acled_agg_weekly"]
REQUIRED_RETAINED = [f"history__climate_month_{b}" for b in BASES] + KEPT


def _verified(client, entry):
    data = _bytes(client, entry["content"])
    if hashlib.sha256(data).hexdigest() != entry["content_sha256"]:
        raise SystemExit(f"{entry['content']} differs from its inventory sha256")
    return data


def compare_keys(fa, fb, roster, origin):
    """Pure: old (admin_code, month) rows preserved byte-for-byte, keys unique, new keys == roster x {O}."""
    key = ["admin_code", "month"]
    r = {"pre_keys_unique": not fa.duplicated(key).any(), "post_keys_unique": not fb.duplicated(key).any()}
    if not (r["pre_keys_unique"] and r["post_keys_unique"]):
        r["passed"] = False
        return r
    merged = fa.merge(fb, on=key, how="left", suffixes=("_pre", "_post"), indicator=True, validate="one_to_one")
    cols = [c for c in fa.columns if c not in key]
    r["old_rows"] = int(len(fa))
    r["old_keys_missing_after"] = int((merged["_merge"] == "left_only").sum())
    r["old_values_changed"] = int(sum((merged[f"{c}_pre"] != merged[f"{c}_post"]).sum() for c in cols))
    old = set(map(tuple, fa[key].itertuples(index=False)))
    new = {k for k in map(tuple, fb[key].itertuples(index=False)) if k not in old}
    want = {(str(a), origin) for a in roster}
    r.update(new_rows=len(new), expected_new=len(want), new_keys_equal_roster_x_O=new == want,
             new_not_in_roster=len(new - want), roster_missing=len(want - new),
             new_value_blank=int(fb[fb.set_index(key).index.isin(list(new))]["value"].eq("").sum()) if "value" in fb else None)
    r["passed"] = (r["old_keys_missing_after"] == 0 and r["old_values_changed"] == 0 and r["new_keys_equal_roster_x_O"])
    return r


def climate(inv_pre, inv_post, origin, out, *bases):
    """Bound roster = the post inventory's fixed__roster HEAD content (sha-verified; the paired/bound roster)."""
    client = storage.Client()
    pre_t, post_t = json.load(open(inv_pre))["tables"], json.load(open(inv_post))["tables"]
    roster = _frame(_verified(client, post_t["fixed__roster"]))["admin_code"].tolist()
    bases = bases or BASES
    result = {"roster_size": len(roster), "bases": list(bases), "per_base": {}}
    for base in bases:
        name = f"history__climate_month_{base}"
        fa, fb = _frame(_verified(client, pre_t[name])), _frame(_verified(client, post_t[name]))
        result["per_base"][base] = {"pre_version": pre_t[name]["version"], "post_version": post_t[name]["version"],
                                    **compare_keys(fa, fb, roster, origin)}
        del fa, fb
    result["all_13_bases"] = sorted(bases) == sorted(BASES)
    result["passed"] = result["all_13_bases"] and all(v["passed"] for v in result["per_base"].values())
    with open(out, "x") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print(json.dumps({b: {k: v.get(k) for k in ("passed", "new_rows", "expected_new", "old_values_changed")}
                      for b, v in result["per_base"].items()} | {"passed": result["passed"]}, indent=1))
    return 0 if result["passed"] else 1


def links(post_real, inv_post, out):
    """Requires generic readback passed (it ran delivery_v2.verify_delivery on this exact delivery ref). Here: the batch
    manifest bytes (pinned ref sha), a NONEMPTY retained_inputs covering the required set, each equal to the post HEAD,
    the batch identity equal to readback's, and the delivery manifest bytes sha-checked before parsing; the fill-audit
    comparison is of DECLARED shas (manifest entry vs batch feature_provenance), byte verification of that member being
    verify_delivery's."""
    client = storage.Client()
    post = json.load(open(post_real))
    post_t = json.load(open(inv_post))["tables"]
    ref = post["batch"]["manifest_ref"]
    data = _bytes(client, ref["uri"], ref["generation"])
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise SystemExit("batch manifest bytes differ from the pinned ref")
    bman = json.loads(data)
    ret = bman.get("retained_inputs") or {}
    retained = {t: {"pinned": v, "equal": bool(post_t.get(t)) and str(v.get("generation")) == str(post_t[t]["head_generation"])
                    and v.get("version") == post_t[t]["version"] and v.get("sha256") == post_t[t]["content_sha256"]}
                for t, v in sorted(ret.items())}
    dref = post["record"]["delivery"]["manifest"]
    dbytes = _bytes(client, dref["uri"], dref["generation"])
    dman_ok = hashlib.sha256(dbytes).hexdigest() == dref["sha256"]
    dman = json.loads(dbytes) if dman_ok else {"files": []}
    audit = [e for e in dman["files"] if e["path"].endswith("ipcch_feature_fill_audit.csv")]
    fp = bman.get("feature_provenance") or {}
    checks = {"generic_readback_passed": bool(post.get("passed")),
              "batch_identity_bound": bman.get("batch_id") == post["batch"]["batch_id"],
              "retained_nonempty": bool(retained),
              "required_tables_present": not sorted(set(REQUIRED_RETAINED) - set(retained)),
              "retained_all_equal_post_heads": bool(retained) and all(v["equal"] for v in retained.values()),
              "delivery_manifest_sha_ok": dman_ok,
              "fill_audit_declared_sha_equals_batch_provenance": len(audit) == 1 and audit[0]["sha256"] == fp.get("sha256")}
    body = {"batch_id": bman.get("batch_id"), "checks": checks, "passed": all(checks.values()),
            "missing_required": sorted(set(REQUIRED_RETAINED) - set(retained)), "retained": retained,
            "feature_provenance": fp, "delivery_fill_audit": audit}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True)
    print(json.dumps({"passed": body["passed"], "checks": checks, "missing_required": body["missing_required"]}, indent=1))
    return 0 if body["passed"] else 1


if __name__ == "__main__":
    mode = sys.argv[1]
    raise SystemExit(climate(*sys.argv[2:6], *sys.argv[6:]) if mode == "climate" else links(*sys.argv[2:5]))
