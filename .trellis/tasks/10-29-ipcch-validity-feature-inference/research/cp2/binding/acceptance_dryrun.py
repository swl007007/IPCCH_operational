"""DRY RUN (not an acceptance): the CP2 acceptance packet path on the actual package 18b91d45 and bundle r5 with a
labelled dry-run acceptor, then real-mode store installation/initialisation into a LOCAL store and bound reads.
Originals are only read; all outputs go to a DRYRUN-NOT-ACCEPTANCE directory."""
import json, os, sys, time
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from tools.ipcch_finalize_acceptance import finalize
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import binding as bd, initial
from cloud.ipcch.stores import StoreError, StoreRoot

PKG, BUNDLE, OUT, RESULT = sys.argv[1:5]
t0, res = time.time(), {"label": "DRY RUN - NOT AN ACCEPTANCE"}
res["finalize"] = finalize(PKG, BUNDLE, "e6e3ebc60ad816bda4580cf3cef65258ba1cb708a4766d9f4d76fbd13f5c97b4",
                           os.path.join(OUT, "bundle"), os.path.join(OUT, "envelope-dryrun.json"), 2,
                           "DRY-RUN (not an acceptance)", "2026-10-30")
b = bd.verify_combination(os.path.join(OUT, "envelope-dryrun.json"), PKG, mode="real",
                          expected_envelope_sha256=res["finalize"]["envelope_sha256"])
store, root = LocalObjectStore(os.path.join(OUT, "store")), StoreRoot("real", "gs://dryrun/ipcch-v2/real")
res["install_acceptance"] = initial.install_acceptance(store, root, os.path.join(OUT, "bundle"), binding=b)
rep = initial.initialise(store, root, os.path.join(OUT, "bundle"), binding=b)
res["initialise"] = {"initialised": len(rep["initialised"]), "unchanged": len(rep["unchanged"]),
                     "verified_files": rep["verified_files"], "pairing": rep["pairing"]}
rep2 = initial.initialise(store, root, os.path.join(OUT, "bundle"), binding=b)
res["reinitialise"] = {"initialised": len(rep2["initialised"]), "unchanged": len(rep2["unchanged"])}
inp = initial.read_assembly_inputs(store, root, b)
res["assembly_inputs"] = {"roster": len(inp.roster), "order": len(inp.order), "order_is_package": inp.order == b.feature_order}
pop, prep = initial.read_population(store, root, b, "2026-08")
res["population_2026_08"] = {**prep, "rows": len(pop)}
try:                                  # the ORIGINAL r5 (draft entries) is not the bound bundle
    initial.initialise(LocalObjectStore(os.path.join(OUT, "store-r5")), root, BUNDLE, binding=b)
    res["original_r5_with_draft_entries"] = "ACCEPTED (unexpected)"
except StoreError as exc:
    res["original_r5_with_draft_entries"] = f"refused: {exc}"
res["original_draft_untouched"] = bd.sha256_file(os.path.join(BUNDLE, "acceptance_entries.json")) == \
    "3621c350d3a8c22f45562368ce30b2041019b74acaa8f17deeb80f9fc887c372"
res["seconds"] = round(time.time() - t0, 1)
json.dump(res, open(RESULT, "w"), indent=1, default=str)
print(json.dumps(res, default=str)[:3000])
