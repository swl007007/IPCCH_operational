"""Task 10-31 CP5 AC6 ACLED cutoff witness (READ-ONLY; run under guarded.sh). Provenance/cutoff evidence only.

What it checks:
- It reads the run's batch feature_provenance sidecar, whose definition is in product cloud/ipcch/provenance.py
  section_of / section_provenance.
- Acquisition: batch manifest bytes at the pinned ref from readback_v2 post (sha checked), then the sidecar at the
  manifest's pinned generation and sha.
- Already-verified local copies are reused when their sha matches; otherwise the bytes are fetched once and saved.
- For EVERY acled_agg_* section:
  - polygon_id set == the bound roster (post fixed__roster, sha-verified), one row per polygon;
  - observation_kind == month_lag1, feature_month == O, dependency_end == A = O - 1;
  - every nonblank latest_observation <= A (blanks are counted and reported, never filled);
  - source_table == acled_agg_weekly, with source_version and source_sha256 == the post inventory HEAD of
    acled_agg_weekly, which also equals the batch retained_inputs entry.
- It also checks that the delivery fill-audit declared sha equals the sidecar sha (the delivery manifest itself is
  sha-checked).

What it does NOT do: it makes no numerical replay of ACLED features. The saved coverage end is reported only as context.

usage: acled_cutoff.py POST_REAL_JSON INV_POST O OUT_JSON [LOCAL_DIR]
"""

import hashlib
import io
import json
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import witness_readback as wr  # noqa: E402  (unchanged helpers: _bytes/_frame/_verified)


def _ord(month):
    y, m = (int(x) for x in str(month).split("-")[:2])
    return y * 12 + m - 1


def _label(o):
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def summarize(prov, roster, origin, acled):
    """Pure. ``prov``: sidecar frame (str dtype, blanks ''); ``acled``: {version, sha256} of the retained table."""
    A = _label(_ord(origin) - 1)
    want = sorted({str(a) for a in roster})
    rows = prov[prov["section"].str.startswith("acled_agg_")]
    sections = {}
    for s, g in rows.groupby("section"):
        ids = g["polygon_id"].astype(str)
        latest = g["latest_observation"]
        nonblank = latest[latest != ""]
        c = {"rows": int(len(g)), "polygons_unique": not ids.duplicated().any(),
             "polygons_equal_roster": sorted(ids) == want,
             "observation_kind_month_lag1": bool((g["observation_kind"] == "month_lag1").all()),
             "feature_month_is_O": bool((g["feature_month"] == origin).all()),
             "dependency_end_is_A": bool((g["dependency_end"] == A).all()),
             "latest_nonblank": int(len(nonblank)), "latest_blank": int((latest == "").sum()),
             "latest_max": max(nonblank) if len(nonblank) else None,
             "latest_all_le_A": bool(nonblank.map(_ord).le(_ord(A)).all()),
             "source_table_acled": bool((g["source_table"] == "acled_agg_weekly").all()),
             "source_version_raw": sorted(g["source_version"].unique().tolist()),     # CSV may serialize 2 as "2.0"
             "source_version_equal": bool(pd.to_numeric(g["source_version"], errors="coerce")
                                          .eq(float(acled["version"])).all()),
             "source_sha_equal": bool((g["source_sha256"] == acled["sha256"]).all())}
        c["passed"] = all(c[k] for k in ("polygons_unique", "polygons_equal_roster", "observation_kind_month_lag1",
                                         "feature_month_is_O", "dependency_end_is_A", "latest_all_le_A",
                                         "source_table_acled", "source_version_equal", "source_sha_equal"))
        sections[s] = c
    return {"origin_O": origin, "cutoff_A": A, "roster_size": len(want), "acled_sections": sorted(sections),
            "per_section": sections, "passed": bool(sections) and all(v["passed"] for v in sections.values())}


def _pinned(client, uri, generation, sha, local):
    """Reuse the local verified copy when its sha matches; otherwise fetch the pinned generation once and save it."""
    if os.path.exists(local):
        data = open(local, "rb").read()
        if hashlib.sha256(data).hexdigest() == sha:
            return data, "reused_local_verified"
        raise SystemExit(f"{local} exists with a different sha256; refusing to overwrite")
    data = wr._bytes(client, uri, generation)
    if hashlib.sha256(data).hexdigest() != sha:
        raise SystemExit(f"{uri}#{generation} differs from its pinned sha256")
    with open(local, "xb") as f:
        f.write(data)
    return data, "fetched_pinned"


def main(post_real, inv_post, origin, out, local_dir=None):
    from google.cloud import storage
    client = storage.Client()
    local_dir = Path(local_dir or Path(out).parent)
    post = json.load(open(post_real))
    post_t = json.load(open(inv_post))["tables"]
    ref = post["batch"]["manifest_ref"]
    mbytes, msrc = _pinned(client, ref["uri"], ref["generation"], ref["sha256"], local_dir / "batch-manifest.json")
    bman = json.loads(mbytes)
    fp = bman["feature_provenance"]
    pbytes, psrc = _pinned(client, fp["file"], fp["generation"], fp["sha256"], local_dir / "batch-feature_provenance.csv")
    prov = pd.read_csv(io.BytesIO(pbytes), dtype=str, keep_default_na=False)
    roster = wr._frame(wr._verified(client, post_t["fixed__roster"]))["admin_code"].tolist()
    head = post_t["acled_agg_weekly"]
    acled = {"version": head["version"], "sha256": head["content_sha256"]}
    pinned = (bman.get("retained_inputs") or {}).get("acled_agg_weekly") or {}
    dref = post["record"]["delivery"]["manifest"]
    dbytes = wr._bytes(client, dref["uri"], dref["generation"])
    dman_ok = hashlib.sha256(dbytes).hexdigest() == dref["sha256"]
    audit = [e for e in json.loads(dbytes)["files"] if e["path"].endswith("ipcch_feature_fill_audit.csv")] if dman_ok else []
    body = summarize(prov, roster, origin, acled)
    body["bindings"] = {
        "batch_id_bound": bman.get("batch_id") == post["batch"]["batch_id"],
        "sidecar_rows_declared": int(fp.get("rows", -1)) == len(prov),
        "batch_retained_acled_equals_post_head": str(pinned.get("version")) == str(acled["version"])
        and pinned.get("sha256") == acled["sha256"] and str(pinned.get("generation")) == str(head["head_generation"]),
        "delivery_manifest_sha_ok": dman_ok,
        "fill_audit_declared_sha_equals_sidecar": len(audit) == 1 and audit[0]["sha256"] == fp["sha256"]}
    body["sources"] = {"batch_manifest": {**ref, "acquired": msrc},
                       "feature_provenance": {**fp, "acquired": psrc}, "acled_head": {k: v for k, v in head.items() if k != "record"},
                       "acled_saved_coverage_context": (head.get("record") or {}).get("coverage")}
    body["claim_scope"] = ("provenance/cutoff evidence: the features declare ACLED dependency through A only; "
                           "no numerical replay of ACLED features was performed")
    body["passed"] = body["passed"] and all(body["bindings"].values())
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({"passed": body["passed"], "cutoff_A": body["cutoff_A"], "bindings": body["bindings"],
                      "per_section": body["per_section"]}, indent=1))
    return 0 if body["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
