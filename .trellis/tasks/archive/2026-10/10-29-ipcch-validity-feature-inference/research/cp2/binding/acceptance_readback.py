"""CP2 acceptance readback: the ACCEPTED envelope v2 verified in real mode against the package and the accepted bundle,
then real-mode install/initialise/readback into a LOCAL temporary store (no production retained store, no current).
Also re-hashes every bundle payload and confirms the originals (package, r5) are unchanged."""
import json, os, sys, tempfile, time
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import binding as bd, initial
from cloud.ipcch.stores import StoreError, StoreRoot

PKG, BUNDLE, ENV, ORIG, RESULT = sys.argv[1:6]
EXPECT = {"envelope": "03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596",
          "package": "18b91d454163ac9ff9833d8127108e731b2f9d95069fb26fd5e7e8877a115f22",
          "handoff": "e6e3ebc60ad816bda4580cf3cef65258ba1cb708a4766d9f4d76fbd13f5c97b4",
          "draft": "3621c350d3a8c22f45562368ce30b2041019b74acaa8f17deeb80f9fc887c372"}
t0, res = time.time(), {}
b = bd.verify_combination(ENV, PKG, mode="real", expected_envelope_sha256=EXPECT["envelope"])
res["verify_combination"] = b.reference() | {"acceptor": b.acceptor, "accepted_at": b.accepted_at, "scopes": b.scopes}
ident = bd.verify_handoff(b, BUNDLE)
res["verify_handoff"] = {k: ident[k] for k in ("manifest_sha256", "roster_size", "roster_sha256", "acceptance_entries_sha256")}
man = ident["_manifest"]
bad = [rel for rel, v in man["files"].items() if bd.sha256_file(os.path.join(BUNDLE, rel)) != v["sha256"]]
res["payload_rehash"] = {"files": len(man["files"]), "mismatches": bad,
                         "bytes": sum(os.path.getsize(os.path.join(BUNDLE, r)) for r in man["files"])}
entries = ident["_entries"]
res["entries"] = {"count": len(entries), "acceptors": sorted({e["acceptor"] for e in entries.values()}),
                  "dates": sorted({e["accepted_at"] for e in entries.values()})}
with tempfile.TemporaryDirectory(prefix="ipcch-cp2-readback-") as tmp:
    store, root = LocalObjectStore(tmp), StoreRoot("real", "gs://local-temp-readback/ipcch-v2/real")
    res["install_acceptance"] = initial.install_acceptance(store, root, BUNDLE, binding=b)
    rep = initial.initialise(store, root, BUNDLE, binding=b)
    res["initialise"] = {"initialised": len(rep["initialised"]), "unchanged": len(rep["unchanged"]),
                         "verified_files": len(rep["verified_files"]), "pairing": rep["pairing"]}
    res["reinitialise_unchanged"] = len(initial.initialise(store, root, BUNDLE, binding=b)["unchanged"])
    inp = initial.read_assembly_inputs(store, root, b)
    res["readback"] = {"roster": len(inp.roster), "feature_order": len(inp.order), "order_is_package": inp.order == b.feature_order,
                       "climate_monthly_bases": len(inp.climate_monthly), "climate_seasonal_bases": len(inp.climate_seasonal),
                       "interim_families": sorted(inp.interim), "snapshot_rows": len(inp.snapshot),
                       "idp_national_rows": len(inp.idp_national), "season_windows": len(inp.season_windows)}
    pop, prep = initial.read_population(store, root, b, "2026-08")
    res["population_2026_08"] = {**prep, "rows": len(pop)}
    try:
        initial.initialise(LocalObjectStore(os.path.join(tmp, "orig")), root, ORIG, binding=b)
        res["original_r5_refused"] = False
    except StoreError as exc:
        res["original_r5_refused"] = str(exc)[:160]
res["originals_unchanged"] = {"package_manifest": bd.sha256_file(os.path.join(PKG, "package_manifest.json")) == EXPECT["package"],
                              "r5_handoff_manifest": bd.sha256_file(os.path.join(ORIG, "handoff_manifest.json")) == EXPECT["handoff"],
                              "r5_draft_entries": bd.sha256_file(os.path.join(ORIG, "acceptance_entries.json")) == EXPECT["draft"],
                              "package_status_field": json.load(open(os.path.join(PKG, "package_manifest.json")))["status"]}
res["ok"] = (not bad and res["readback"]["order_is_package"] and res["readback"]["roster"] == 6226
             and res["initialise"]["initialised"] == 52 and res["reinitialise_unchanged"] == 52
             and isinstance(res["original_r5_refused"], str) and all(v is True for k, v in res["originals_unchanged"].items() if k != "package_status_field"))
res["seconds"] = round(time.time() - t0, 1)
json.dump(res, open(RESULT, "w"), indent=1, default=str)
print(json.dumps(res, default=str, indent=1))
sys.exit(0 if res["ok"] else 2)
