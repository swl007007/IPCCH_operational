"""Persist reviewable actual-weight predictions of the CP3 real-mode LOCAL integration: reload the run's own immutable
batch from its local store (pinned manifest ref from result.json), re-verify (load_batch) and score it once through the
unchanged runtime with the accepted package (no network, no refresh, nothing written to the store), then write one CSV
per horizon plus a receipt (sha256, rows, exact unique roster, finite q2..q5, M/O/targets/mode)."""
import hashlib, json, os, sys
import numpy as np
sys.path.insert(0, "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline")
from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import batch_inference as bi, binding as bd, initial
from cloud.ipcch.stores import StoreRoot

R = "/home/swl007007/projects/food-crisis-research"
PKG = f"{R}/scratch/h2h8h14-final/package-build/out-r1/package"
ENV = f"{R}/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json"
RUN = sys.argv[1]
OUT = os.path.join(RUN, "predictions")
os.makedirs(OUT)                                                   # create-only
res = json.load(open(os.path.join(RUN, "result.json")))
ref, batch_id = res["batch"]["manifest_ref"], res["batch"]["batch_id"]
binding = bd.verify_combination(ENV, PKG, mode="real")


class ReadOnlyReopen(LocalObjectStore):
    """The local fake store keeps generations in memory only; reopened READ-ONLY in a new process every existing object
    reports generation 1 (exact for the create-only batch objects the pinned manifest ref names; table reads are still
    verified against their HEAD sha256 and batch reads against the pinned sha256). Any write is refused."""

    def get_metadata(self, uri):
        from cloud.common.object_store import ObjectMetadata
        return ObjectMetadata(uri=uri, generation="1") if self._path_for_uri(uri).is_file() else None

    def write_text(self, *a, **k):
        raise RuntimeError("read-only reopen: no writes")


store, root = ReadOnlyReopen(os.path.join(RUN, "store")), StoreRoot("real", "gs://local-integration-store/ipcch-v2/real")
roster = [str(a) for a in initial._read(store, root, "fixed/roster.csv")["admin_code"]]
manifest, frames = bi.load_batch(store, ref, batch_root=root.uri, batch_id=batch_id, mode="real", execution_month="2026-10",
                                 binding=binding, roster=roster)
scored = bi.score_batch(manifest, frames, PKG, binding)
receipt = {"batch_id": batch_id, "manifest_ref": ref, "envelope_sha256": binding.envelope_sha256,
           "package_manifest_sha256": binding.package_manifest_sha256, "execution_month": manifest["execution_month"],
           "feature_origin": manifest["feature_origin"], "mode": manifest["mode"], "designation": manifest["designation"],
           "disclosure": "local locked Python (fewsnet-test-lock-20261022) only; the request's runtime image digest and "
                         "environment manifest are placeholders - not container/deployment validation",
           "store_reopen": "read-only reopen of the local fake store (generation 1 per existing object; content verified by sha256)",
           "horizons": {}}
ok = True
for h, v in sorted(scored.items()):
    p = v["predictions"]
    path = os.path.join(OUT, f"ipcch_predictions_h{h:02d}.csv")
    p.to_csv(path, index=False, lineterminator="\n")
    data = open(path, "rb").read()
    scores = p[[f"{t}_score" for t in bi.TARGETS]].to_numpy(float)
    areas = p["admin_code"].astype(str)
    chk = {"rows": int(len(p)), "unique_areas": bool(areas.is_unique), "exact_roster": sorted(areas) == sorted(roster),
           "finite_q2_q5": bool(np.isfinite(scores).all()), "feature_period": sorted(set(p["feature_period"])),
           "target_period": sorted(set(p["target_period"])), "mode": sorted(set(p["mode"])),
           "batch_id": sorted(set(p["batch_id"])) == [batch_id], "model_package_id": sorted(set(p["model_package_id"]))}
    expect_target = manifest["horizons"][str(h)]["target_month"]
    chk["ok"] = (chk["rows"] == len(roster) == 6226 and chk["unique_areas"] and chk["exact_roster"] and chk["finite_q2_q5"]
                 and chk["feature_period"] == [manifest["feature_origin"]] and chk["target_period"] == [expect_target]
                 and chk["mode"] == ["real"] and chk["batch_id"])
    ok &= chk["ok"]
    receipt["horizons"][str(h)] = {"file": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                                   "columns": list(p.columns), "checks": chk,
                                   "phase_counts": {str(k): int(n) for k, n in p["overall_phase_pred"].value_counts().sort_index().items()},
                                   "raw_scores_outside_0_1": v["summary"]["raw_scores_outside_0_1"],
                                   "thresholds": v["summary"]["thresholds"], "monotonicity": v["summary"]["monotonicity_policy"]}
receipt["ok"] = bool(ok)
json.dump(receipt, open(os.path.join(OUT, "predictions_receipt.json"), "w"), indent=1, default=str)
print(json.dumps({h: v["checks"] for h, v in receipt["horizons"].items()}, default=str)[:2500])
sys.exit(0 if ok else 2)
