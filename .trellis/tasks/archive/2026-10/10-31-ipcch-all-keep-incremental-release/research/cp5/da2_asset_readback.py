"""Task 10-31 CP2 (DRAFT, NOT RUN; Supervisor gate needed for the credential identity): READ-ONLY DA2 field-shape
readback of this run's produced EE table assets.

The runtime reader maps each feature through ``Feature.toDictionary()`` and builds a DataFrame (ee_transport.py
read_asset_table), so an omitted property and an explicit null both become NaN. This readback pages the RAW feature
properties (no toDictionary mapping, bounded pages) and records per asset: row count, per-row property-key sets
(omitted keys per row vs explicit nulls), admin_code set (PATCH32: the exact normalized 32-ID set vs PATCH32_CODES),
constant identity properties, days_present_* / composite_dates, and numeric ranges of value columns.

Identity: it runs with the LOCAL operator's existing Earth Engine credentials (read-only computeFeatures on the
feisty assets). It is NOT the runtime service account; label results accordingly. No write, no export.

usage: da2_asset_readback.py LINEAGE_JSON OUT_JSON      (asset IDs from the lineage readback's completed task records)
"""

import json
import math
import re
import sys

PATCH32_CODES = (101183, 101191, 101194, 101275, 2107, 2108, 3422, 3423, 3427, 3428, 3429, 3430, 3431, 3432, 3433, 4073,
                 4267, 4269, 4270, 4353, 4783, 4784, 4785, 4786, 4787, 76, 77, 983, 984, 985, 986, 987)
VALUE = re.compile(r"(?:evi|ndvi|used1km)_\d{8}_mean|(?:prcp|et0)_\d{6}_mean")
MAX_PAGES, PAGE = 20, 1000


def _norm_code(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def field_status(props_rows, field):
    """Per declared field: rows where the key is OMITTED, explicitly null, finite numeric, other."""
    omitted = sum(1 for p in props_rows if field not in p)
    null = sum(1 for p in props_rows if field in p and p[field] is None)
    finite = sum(1 for p in props_rows if isinstance(p.get(field), (int, float)) and not isinstance(p.get(field), bool)
                 and math.isfinite(p[field]))
    n = len(props_rows)
    status = ("wholly_omitted" if omitted == n else "all_null" if null == n else "all_finite" if finite == n
              else "partial")
    return {"rows": n, "omitted": omitted, "explicit_null": null, "finite": finite, "other": n - omitted - null - finite,
            "status": status}


def summarize(props_rows, kind, expected_fields=()):
    """Pure: summary of raw property dicts (one per feature). ``expected_fields``: fields DECLARED by the produced
    metadata/calendar; each gets a status even when no row carries it (an absent field is never silently dropped)."""
    keys = [set(p) for p in props_rows]
    union = set().union(*keys) if keys else set()
    omitted = {k: sum(1 for s in keys if k not in s) for k in sorted(union)}
    explicit_null = {k: sum(1 for p in props_rows if k in p and p[k] is None) for k in sorted(union)}
    codes = [_norm_code(p.get("admin_code")) for p in props_rows]
    values = {}
    for k in sorted(union):
        if VALUE.fullmatch(k):
            nums = [p[k] for p in props_rows if isinstance(p.get(k), (int, float)) and not isinstance(p.get(k), bool)
                    and math.isfinite(p[k])]
            values[k] = {"finite": len(nums), "min": min(nums) if nums else None, "max": max(nums) if nums else None}
    constants = {}
    for k in sorted(union):
        if not VALUE.fullmatch(k) and k != "admin_code":
            seen = {json.dumps(p.get(k, "<omitted>"), default=str) for p in props_rows}
            constants[k] = json.loads(seen.pop()) if len(seen) == 1 else f"<{len(seen)} distinct>"
    out = {"rows": len(props_rows), "keys_union": sorted(union),
           "rows_with_omitted_keys": {k: v for k, v in omitted.items() if v},
           "explicit_null_counts": {k: v for k, v in explicit_null.items() if v},
           "admin_codes": {"count": len(codes), "distinct": len(set(codes)), "duplicates": len(codes) - len(set(codes))},
           "value_columns": values, "constants": constants}
    out["expected_fields"] = {f: field_status(props_rows, f) for f in expected_fields}
    out["expected_fields_note"] = ("statuses for declared fields only; a field not declared by metadata is not inferred"
                                   if expected_fields else "no declared field list supplied: observational limitation")
    if kind == "patch32":
        expected = {str(c) for c in PATCH32_CODES}
        out["patch32"] = {"code_set": sorted(set(codes), key=lambda c: int(c)), "rows": len(codes),
                          "distinct": len(set(codes)), "duplicates": len(codes) - len(set(codes)),
                          "equals_targets": set(codes) == expected and len(codes) == 32 and len(set(codes)) == 32,
                          "missing": sorted(expected - set(codes)), "extra": sorted(set(codes) - expected)}
    return out


def fetch(asset_id):
    import ee
    rows, token = [], None
    for page in range(1, MAX_PAGES + 1):
        params = {"expression": ee.FeatureCollection(asset_id), "pageSize": PAGE, **({"pageToken": token} if token else {})}
        resp = ee.data.computeFeatures(params)
        rows += [f.get("properties") or {} for f in resp.get("features", [])]
        token = resp.get("nextPageToken")
        if not token:
            return rows, page
    raise RuntimeError(f"{asset_id}: more than {MAX_PAGES} pages")


def main(lineage_json, out):
    import ee
    ee.Initialize(project="feisty-flames-511718-d4")
    lin = json.load(open(lineage_json))
    kinds = {r["asset_id"]: ("patch32" if "PATCH32" in r["asset_id"] else "vi" if "_VI_" in r["asset_id"] else "drought")
             for r in lin["task_records"] if r.get("state") == "completed"}
    body = {"identity": "local operator Earth Engine credentials (read-only), not the runtime SA", "assets": {}}
    for asset_id, kind in sorted(kinds.items()):
        rows, pages = fetch(asset_id)
        body["assets"][asset_id] = {"kind": kind, "pages": pages, **summarize(rows, kind)}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({a: {k: v[k] for k in ("kind", "rows", "rows_with_omitted_keys", "explicit_null_counts")}
                      for a, v in body["assets"].items()}, indent=1, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:3])
