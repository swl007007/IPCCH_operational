"""Task 10-31 CP2: DA2 forensic witnesses with the LOCAL OPERATOR's existing Earth Engine credentials (read-only;
approved within the spec). This identity is NOT the runtime service account, and nothing here counts as runtime-SA
evidence.

1. Raw property shapes of every completed table_to_asset export of the run (da2_asset_readback.summarize: per-row
   omitted keys vs explicit nulls, admin_code set, PATCH32 exact 32-ID set, constants, value ranges).
2. PATCH32 natural filling witness: for the 32 target codes, primary ET0 (FAO56 produced chunk) vs PATCH32 values for
   the input months of O. A code with primary null/omitted and patch finite at O is a natural filling witness; its
   saved spei03 at O (post-run immutable content) is reported. Codes with finite primary show the primary is kept.
3. VI units/anomaly witness: for N admins with a finite saved evi_anom at O, the raw current (produced) and same-slot
   baseline (han S2E3 base parts) values, recomputed with the product's monthly_vi and ensemble, compared to the saved
   value.

usage: da2_witness.py LINEAGE_JSON INV_POST O OUT_JSON [N_ADMINS]
"""

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import da2_asset_readback as da  # noqa: E402

IDENTITY = "local operator Earth Engine credentials (read-only forensic), NOT the runtime service account"
VI_TOLERANCE = 1e-9            # absolute; recompute and saved use the same float64 product functions


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) else float("nan")


def expected_fields(kind, asset_id, rows, origin):
    """Fields DECLARED by the produced table's own metadata: drought chunks Y{a}_{b} -> {prcp|et0}_YYYYMM_mean and
    days_present_YYYYMM for Jan a .. O; VI -> evi_{tag}_mean for each composite_dates tag."""
    import re
    if kind == "vi":
        tags = {str(r.get("composite_dates")) for r in rows if r.get("composite_dates")}
        tag = tags.pop() if len(tags) == 1 else ""
        return [f"evi_{t}_mean" for t in tag.split(",") if t]
    m = re.search(r"_Y(\d{4})_(\d{4})_V\d", asset_id)
    a, b = int(m.group(1)), int(m.group(2))
    prefix = "prcp" if "_PRCP_" in asset_id else "et0"
    last = int(origin.replace("-", ""))
    months = [f"{y}{mm:02d}" for y in range(a, b + 1) for mm in range(1, 13) if int(f"{y}{mm:02d}") <= last]
    return [f"{prefix}_{t}_mean" for t in months] + [f"days_present_{t}" for t in months]


def patch_fill(primary, patch, codes, months):
    """spi_spei.apply_et0_patch rule per code/input month: fill = isnan(primary) & isfinite(patch);
    selected = patch where fill else primary; finite primary is preserved."""
    out = []
    for c in codes:
        p, q = primary.get(c, {}), patch.get(c, {})
        for m in months:
            pv, qv = _num(p.get(f"et0_{m}_mean")), _num(q.get(f"et0_{m}_mean"))
            fill = bool(np.isnan(pv) and np.isfinite(qv))
            sel = qv if fill else pv
            out.append({"admin_code": c, "month": m, "primary": None if np.isnan(pv) else pv,
                        "primary_key_present": f"et0_{m}_mean" in p, "patch": None if np.isnan(qv) else qv,
                        "selected": None if np.isnan(sel) else sel, "filled": fill,
                        "finite_primary_preserved": (not np.isfinite(pv)) or sel == pv})
    return out


def vi_compare(recomputed, saved, tol=VI_TOLERANCE):
    """Per admin: both finite and |recomputed - saved| <= tol. Empty sample -> pending (D2), never a pass."""
    if not saved:
        return {"status": "unobserved_pending_D2", "passed": None, "per_admin": {}}
    per = {}
    for a, sv in saved.items():
        rv = recomputed.get(a)
        ok = rv is not None and np.isfinite(rv) and np.isfinite(sv) and abs(rv - sv) <= tol
        per[a] = {"recomputed": rv, "saved": sv, "abs_diff": None if rv is None or not np.isfinite(rv) else abs(rv - sv),
                  "within_tolerance": bool(ok)}
    return {"status": "observed", "tolerance": tol, "passed": all(v["within_tolerance"] for v in per.values()),
            "per_admin": per}


def _rows(ee, asset_id, codes=None):
    fc = ee.FeatureCollection(asset_id)
    if codes is not None:
        fc = fc.filter(ee.Filter.Or(ee.Filter.inList("admin_code", [int(c) for c in codes]),
                                    ee.Filter.inList("admin_code", [str(c) for c in codes])))
    rows, token = [], None
    for _ in range(da.MAX_PAGES):
        resp = ee.data.computeFeatures({"expression": fc, "pageSize": da.PAGE, **({"pageToken": token} if token else {})})
        rows += [f.get("properties") or {} for f in resp.get("features", [])]
        token = resp.get("nextPageToken")
        if not token:
            return rows
    raise RuntimeError(f"{asset_id}: too many pages")


def _post_content(inv_post, table):
    from google.cloud import storage
    import hashlib
    t = json.load(open(inv_post))["tables"][table]
    b, _, n = t["content"].removeprefix("gs://").partition("/")
    data = storage.Client().bucket(b).blob(n).download_as_bytes()
    if hashlib.sha256(data).hexdigest() != t["content_sha256"]:
        raise SystemExit(f"{table} content differs from its inventory sha256")
    return pd.read_csv(io.BytesIO(data), dtype={"admin_code": str, "month": str})


def main(lineage_json, inv_post, origin, out, n_admins="3"):
    import ee
    from cloud.ipcch import climate as cl
    from cloud.ipcch import climate_tables as ct
    ee.Initialize(project="feisty-flames-511718-d4")
    lin = json.load(open(lineage_json))
    assets = {r["asset_id"]: r for r in lin["task_records"] if r.get("kind") == "table_to_asset" and r.get("state") == "completed"}
    body = {"identity": IDENTITY, "raw": {}, "patch32": {}, "vi": {}}
    raw_rows = {}
    for asset_id in sorted(assets):
        kind = "patch32" if "PATCH32" in asset_id else "vi" if "_VI_" in asset_id else "drought"
        rows = _rows(ee, asset_id)
        raw_rows[asset_id] = rows
        body["raw"][asset_id] = {"kind": kind, **da.summarize(rows, kind, expected_fields(kind, asset_id, rows, origin))}
    # 2. PATCH32 filling witness
    token = origin.replace("-", "")
    months = [m.replace("-", "") for m in ct.input_months(origin, origin)]
    et0_id = next(a for a in assets if "ET0_FAO56" in a)
    patch_id = next(a for a in assets if "PATCH32" in a)
    codes = {da._norm_code(c) for c in da.PATCH32_CODES}
    prim = {da._norm_code(r.get("admin_code")): r for r in raw_rows[et0_id] if da._norm_code(r.get("admin_code")) in codes}
    patch = {da._norm_code(r.get("admin_code")): r for r in raw_rows[patch_id]}
    spei = _post_content(inv_post, "history__climate_month_spei03")
    spei = spei[spei["month"] == origin].set_index("admin_code")["value"]
    fills = patch_fill(prim, patch, sorted(codes, key=int), months)
    for f in fills:
        f["saved_spei03_at_O"] = (spei.loc[f["admin_code"]] if f["admin_code"] in spei.index else None) if f["month"] == token else None
    body["patch32"] = {"asset": patch_id, "primary_asset": et0_id, "input_months": months, "per_code_month": fills,
                       "label": "SOURCE-LEVEL candidate witness from the raw produced assets (operator read); the retained "
                                "selection evidence is only the saved spei03 value, not a re-run of the product",
                       "natural_fill_witnesses": sorted({(f["admin_code"], f["month"]) for f in fills if f["filled"]}),
                       "finite_primary_all_preserved": all(f["finite_primary_preserved"] for f in fills),
                       "status": "observed" if any(f["filled"] for f in fills) else "no_natural_fill_pending_D2"}
    # 3. VI units / anomaly witness
    evi = _post_content(inv_post, "history__climate_month_evi_anom")
    evi = evi[(evi["month"] == origin)].copy()
    evi["v"] = pd.to_numeric(evi["value"], errors="coerce")
    sample = evi[np.isfinite(evi["v"])].head(int(n_admins))["admin_code"].tolist()
    refs = ct.TableRefs()
    y, m = (int(x) for x in origin.split("-"))
    per_sensor = {}
    for sensor, label in (ct.SENSOR_LABELS.items() if sample else []):      # empty sample -> pending (D2)
        base_ids = [refs.asset(refs.vi_baseline.format(label=label, part=k)) for k in range(1, 5)]
        cur_id = next((a for a in assets if f"_VI_CURRENT_ADMIN_{label.upper()}_" in a.upper()), None)
        if cur_id is None:
            continue
        base = pd.DataFrame([r for b in base_ids for r in _rows(ee, b, sample)])
        base["admin_code"] = base["admin_code"].map(da._norm_code)
        joined = base.drop_duplicates("admin_code", keep="first").set_index("admin_code")
        cur = pd.DataFrame(_rows(ee, cur_id, sample))
        cur["admin_code"] = cur["admin_code"].map(da._norm_code)
        cur = cur.set_index("admin_code")
        joined = joined.join(cur[[c for c in cur.columns if c not in joined.columns]], how="left")
        res = ct.monthly_vi(joined.reset_index(), sensor, "evi", y, m).set_index("admin_code")
        parts = ct.month_plan(sensor, y, m)
        per_sensor[sensor] = {"current_asset": cur_id, "baseline_assets": base_ids,
                              "parts": parts, "value": res["value"].to_dict(), "coverage": res["coverage"].to_dict(),
                              "raw": {a: {f"cur {p['tag']}": joined.loc[a].get(f"evi_{p['tag']}_mean") if a in joined.index else None
                                          for p in parts} | {f"base s{p['slot']:02d}": joined.loc[a].get(f"evi_base_s{p['slot']:02d}_mean")
                                                             if a in joined.index else None for p in parts} for a in sample}}
    ens = cl.ensemble({s: pd.Series(v["value"]) for s, v in per_sensor.items()}).set_index("admin_code") if per_sensor else None
    saved = {a: float(evi.set_index("admin_code").loc[a, "v"]) for a in sample}
    recomputed = {a: float(ens.loc[a, "value"]) for a in sample if ens is not None and a in ens.index}
    body["vi"] = {"sample": sample, "per_sensor": per_sensor, "compare": vi_compare(recomputed, saved),
                  "scaling_note": "no extra 0.0001 scaling applied (producer and consumer apply none)"}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({"identity": IDENTITY,
                      "raw": {a: {k: v[k] for k in ("kind", "rows", "rows_with_omitted_keys", "explicit_null_counts")}
                              | ({"patch32": v["patch32"]} if "patch32" in v else {}) for a, v in body["raw"].items()},
                      "patch32": {k: body["patch32"][k] for k in ("status", "natural_fill_witnesses", "finite_primary_all_preserved")},
                      "vi_compare": {k: body["vi"]["compare"][k] for k in ("status", "passed")}}, indent=1, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:6])
