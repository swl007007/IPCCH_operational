"""CP2 binding evidence on the ACTUAL candidate package (18b91d45) and handoff bundle r5 (read-only; nothing in either
is modified). Writes a CANDIDATE envelope v1 (create-only) next to the package build outputs, verifies it in smoke mode
(package + evidence only), shows the bundle digests equal the envelope's handoff section, that real mode refuses the
candidate envelope and the draft (unfinalized) acceptance entries, and runs the population snapshot and the exact-roster
geometry on the real r5 assets."""
import json, os, sys, time
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
import pandas as pd
from cloud.batch import remote_sources as rs
from cloud.ipcch import binding as bd, geography as geo

PKG, BUNDLE, OUT_ENV, OUT_JSON = sys.argv[1:5]
t0 = time.time()
res = {"package_root": PKG, "bundle_dir": BUNDLE}
env = bd.build_envelope(PKG, BUNDLE, envelope_version=1, created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
res["envelope_path"] = OUT_ENV
res["envelope_sha256"] = bd.write_envelope(env, OUT_ENV) if not os.path.exists(OUT_ENV) else bd.sha256_file(OUT_ENV)
env = json.load(open(OUT_ENV))
res["envelope"] = {k: env[k] for k in ("envelope_id", "status", "acceptor", "accepted_at")} | {"package": env["package"], "handoff": env["handoff"]}
b = bd.verify_combination(OUT_ENV, PKG, mode="smoke", expected_envelope_sha256=res["envelope_sha256"])
res["smoke_verify"] = {"ok": True, "handoff_resolved": b.handoff is not None, "feature_count": len(b.feature_order),
                       "feature_order_sha256": b.feature_order_sha256}
ident = bd.handoff_identity(BUNDLE, finalized=False)
res["bundle_digests_equal_envelope"] = {k: ident[k] == env["handoff"][k] for k in
                                        ("manifest_sha256", "roster_size", "roster_sha256", "draft_acceptance_entries_sha256")}
def refused(fn):
    try:
        fn(); return {"refused": False}
    except bd.BindingError as exc:
        return {"refused": True, "error": str(exc)}
res["real_with_candidate_envelope"] = refused(lambda: bd.verify_combination(OUT_ENV, PKG, mode="real"))
res["finalized_entries_check_on_draft"] = refused(lambda: bd.handoff_identity(BUNDLE, finalized=True))
res["accepted_envelope_on_draft_entries"] = refused(lambda: bd.build_envelope(PKG, BUNDLE, envelope_version=99, created_at="x",
                                                                              acceptor="dry-run", accepted_at="2026-10-30"))
man = ident["_manifest"]
roster = pd.read_csv(os.path.join(BUNDLE, "fixed/roster.csv"), dtype=str)["admin_code"].tolist()
ref = pd.read_csv(os.path.join(BUNDLE, "fixed/population_reference.csv"), dtype={"admin_code": str, "reference_period": str})
res["population_reference"] = {"rows": len(ref), "areas": ref["admin_code"].nunique(),
                               "periods": [ref["reference_period"].min(), ref["reference_period"].max()]}
res["population"] = {}
from model_pipeline.ipcch_launch_runtime.population import PopulationSelectionError
first = ref.groupby("admin_code")["reference_period"].min()
res["population_reference"]["latest_first_period"] = first.max()
res["population_reference"]["areas_by_first_period"] = first.value_counts().sort_index().to_dict()
for origin in ("2026-10", "2026-08", "2026-04", "2025-06", "2020-01"):
    try:
        out, rep = geo.population_snapshot(ref, origin=origin, roster=roster)
    except PopulationSelectionError as exc:      # an area with no reference period <= O is refused, never back-filled
        res["population"][origin] = {"refused": str(exc)[:200]}
        continue
    res["population"][origin] = {**rep, "rows": len(out), "admin_codes_equal_roster": out["admin_code"].tolist() == roster,
                                 "max_reference_period_le_origin": max(out["population_reference_period"]) <= origin}
fc, grep = geo.roster_geometries(BUNDLE, man, roster)
keys = rs.native_geometries(fc, roster=roster)
res["geometry"] = {**grep, "declared_extra": sorted(geo.declared_extras(man)),
                   "native_geometries_equal_roster": list(keys) == roster}
res["seconds"] = round(time.time() - t0, 1)
json.dump(res, open(OUT_JSON, "w"), indent=1, default=str)
print(json.dumps({k: res[k] for k in ("envelope_sha256", "bundle_digests_equal_envelope", "geometry")}, default=str)[:1500])
