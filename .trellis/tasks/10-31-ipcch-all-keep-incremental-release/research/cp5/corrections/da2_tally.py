"""Exact local tally of cp5/da2-witness.json PATCH32 rows (no cloud; corrects cp5-result.md wording)."""
import json, math, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open("../da2-witness.json"))
rows = d["patch32"]["per_code_month"]
fin = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
O = [r for r in rows if r["month"] == "202609"]
filled_codes = sorted({r["admin_code"] for r in rows if r["filled"]}, key=int)
spei = {r["admin_code"]: r["saved_spei03_at_O"] for r in O}
out = {"rows": len(rows), "codes": len(spei), "months": sorted({r["month"] for r in rows}),
       "saved_spei03_at_O_finite": sorted([c for c, v in spei.items() if fin(v)], key=int),
       "saved_spei03_at_O_nan_or_missing": sorted([c for c, v in spei.items() if not fin(v)], key=int),
       "filled_codes": filled_codes,
       "filled_codes_with_nan_spei03_at_O": sorted([c for c in filled_codes if not fin(spei.get(c))], key=int),
       "not_filled_codes": sorted({r["admin_code"] for r in rows if not r["filled"]}, key=int),
       "primary_finite_rows": sum(fin(r["primary"]) for r in rows),
       "primary_null_rows": sum(r["primary"] is None for r in rows),
       "finite_primary_all_preserved_flag": d["patch32"].get("finite_primary_all_preserved")}
out["finite_primary_preservation"] = ("vacuous: no sampled row has a finite primary; finite-primary preservation is NOT observed"
                                      if out["primary_finite_rows"] == 0 else "observed on finite-primary rows")
for k in ("saved_spei03_at_O_finite", "saved_spei03_at_O_nan_or_missing", "filled_codes", "filled_codes_with_nan_spei03_at_O"):
    out[k + "_count"] = len(out[k])
open(sys.argv[1], "x").write(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
