"""CP5 readback (task 10-30) with the PRODUCT verifiers; reads only (ADC credentials).

  pre  MODE OUT_JSON                      the current pointer/record of MODE's namespace, pinned (before submission)
  post MODE RUN_ID PRE_JSON CTX_IPCCH OUT STATE_JSON M O FEATURES ROSTER  after the run (success/link/expectation checks):
    * current moved from exactly PRE's generation to this run's v2 record (previous.pointer_generation == PRE);
    * real: activation present; the FEWS NET member is the FULL dict equal to pub.members(PRE record)["fewsnet"]
      (no stripped comparison) and record.inherited names PRE's pointer generation;
    * delivery_v2.verify_delivery(store, delivery_ref, snapshot=PRE, record) - every stored file vs the manifest, the new
      IPCCH member via delivery_member.verify_member, inherited members against their pinned source inventories;
    * batch_inference.load_batch of the run's feature batch (manifest ref from runs/<run>/v2_run_status.json) with the
      binding re-verified from the staged installed tree (CTX_IPCCH = the image's /opt/ipcch bytes, INSTALL.json), and
      each horizon file's RAW header line equal to the loaded frame's columns;
    * the run status' generation report (climate/production/GPP/nightlight sections) copied verbatim for source actions.
"""

import hashlib
import json
import sys

from google.cloud import storage

from cloud.common.object_store import GCSObjectStore
from cloud.ipcch import batch as bt
from cloud.ipcch import batch_inference as bi
from cloud.ipcch import binding as bd
from cloud.ipcch import delivery_v2 as dv
from cloud.ipcch import entrypoint_v2 as ep
from cloud.ipcch import initial
from cloud.ipcch import publication as pub
from cloud.ipcch.stores import StoreRoot

CONFIG = "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline/deploy/ipcch_v2_deployment.food-crisis-test.json"


def ns(cfg, mode):
    return cfg["namespaces"]["production" if mode == "real" else "smoke"]


def pre(mode, out):
    cfg, store = ep.load_config(CONFIG), GCSObjectStore(storage.Client())
    snap = pub.read_current(store, cfg["roots"][mode], ns(cfg, mode), allow_missing_legacy_record=False)
    json.dump(snap, open(out, "x"), indent=1, sort_keys=True)
    print(json.dumps({"mode": mode, "generation": snap["generation"], "run_id": (snap["record"] or {}).get("run_id")}))


def post(mode, run_id, pre_path, ctx, out, state_path=None, expect=None, *, store=None, cfg=None):
    """``expect``: {"M", "O", "features", "roster"} required values (real CP5: 2026-10, 2026-08, 527, 6226).
    ``state_path``: the operator's submit_v2 state.json (frozen request identity); ``ctx``: staged /opt/ipcch or None."""
    cfg = cfg or ep.load_config(CONFIG)
    store = store or GCSObjectStore(storage.Client())
    before = json.load(open(pre_path))
    after = pub.read_current(store, cfg["roots"][mode], ns(cfg, mode))
    rec = after["record"]
    member = rec["systems"]["ipcch"]
    status = json.loads(store.read_text(f"{cfg['roots'][mode]}/runs/{run_id}/v2_run_status.json"))
    reservation = json.loads(store.read_text(f"{cfg['roots'][mode]}/runs/{run_id}/v2_reservation.json"))
    result = status["systems"]["ipcch"]["result"]
    inference = result["inference"]
    checks = {"status_succeeded": status.get("status") == "succeeded"
              and status["systems"]["ipcch"].get("status") == "succeeded",
              "status_run_mode": status.get("run_id") == run_id and status.get("mode") == mode,
              "reservation_run_mode": reservation.get("run_id") == run_id and reservation.get("mode") == mode,
              "release_request_is_reserved_request": {k: rec["request"].get(k) for k in ("uri", "generation")}
              == {k: reservation["request"].get(k) for k in ("uri", "generation")},
              "pointer_moved": after["generation"] != before["generation"],
              "record_is_this_run": rec.get("run_id") == f"{run_id}-ipcch" and rec["delivery"].get("request_run_id") == run_id,
              "previous_is_pre": rec["previous"]["pointer_generation"] == before["generation"],
              "schema_v2": rec.get("schema") == pub.RELEASE_SCHEMA, "mode": rec.get("mode") == mode}
    if state_path:
        state = json.load(open(state_path))
        checks["reserved_request_is_frozen_submission"] = (
            {k: state["request"].get(k) for k in ("uri", "generation", "sha256")} == dict(reservation["request"])
            and state["run_id"] == run_id)
    if mode == "real":
        want = pub.members(before["record"])["fewsnet"]
        checks["activation_present"] = bool(pub.activation(rec))
        checks["fewsnet_member_full_equal"] = rec["systems"].get("fewsnet") == want
        checks["inherited_fewsnet_from_pre"] = str((rec.get("inherited") or {}).get("fewsnet")) == before["generation"]
    manifest = dv.verify_delivery(store, delivery_ref=rec["delivery"]["manifest"], snapshot=before, record=rec)
    checks["verify_delivery"] = True
    inst = {k: (v.replace("/opt/ipcch", ctx) if ctx else v) for k, v in cfg["installed"][mode].items()}
    binding = bd.verify_combination(inst["envelope"], inst["package_root"], mode=mode,
                                    fixture_root=inst.get("fixture_root") if mode == "smoke" else None)
    root = StoreRoot(mode, cfg["store_roots"][mode])
    roster = [str(a) for a in initial._read(store, root, "fixed/roster.csv")["admin_code"]]
    roster = bt.bound_roster(store, root, binding, roster)
    bman, frames = bi.load_batch(store, inference["manifest_ref"], batch_root=root.uri, batch_id=inference["batch_id"],
                                 mode=mode, execution_month=member["execution_month"], binding=binding, roster=roster)
    paths = bt.batch_paths(root.uri, inference["batch_id"])
    headers = {}
    for h, frame in frames.items():
        uri = paths[str(h)]
        raw = store.read_bytes(uri).split(b"\n", 1)[0].decode("utf-8-sig").rstrip("\r")
        headers[str(h)] = {"uri": uri, "raw_header_equals_frame": raw == ",".join(map(str, frame.columns)),
                           "rows": int(len(frame)), "target_month": bman["horizons"][str(h)]["target_month"]}
    checks["batch_loaded"] = True
    checks["raw_headers_equal"] = all(v["raw_header_equals_frame"] for v in headers.values())
    want_roster = {"size": len(roster), "sha256": bt.roster_sha256(roster)}
    prov_entry = [e for e in manifest["files"] if e["path"].endswith("system_provenance.json") and "ipcch" in e["path"]]
    base = rec["delivery"]["manifest"]["uri"].rsplit("/", 1)[0]
    prov_bytes = store.read_bytes(f"{base}/{prov_entry[0]['path']}") if len(prov_entry) == 1 else b"{}"
    provenance = json.loads(prov_bytes)
    checks.update({
        "batch_run_mode": bman.get("run_id") == run_id and bman.get("mode") == mode,
        "batch_ids_linked": member["batch"]["batch_id"] == inference["batch_id"] == bman.get("batch_id"),
        "batch_feature_order_is_binding": bman.get("feature_order_sha256") == binding.feature_order_sha256
        and bman.get("feature_count") == len(binding.feature_order),
        "batch_roster_is_bound_roster": {k: bman["roster"][k] for k in ("size", "sha256")} == want_roster,
        "member_provenance_is_recorded": len(prov_entry) == 1
        and hashlib.sha256(prov_bytes).hexdigest() == member["provenance_sha256"],
        "member_roster_is_bound_roster": provenance.get("roster") == want_roster,
        "month_origin_linked": status["derived"]["execution_month"] == member["execution_month"] == bman.get(
            "execution_month") and status["derived"]["feature_origin"] == member["feature_origin"] == bman.get(
            "feature_origin"),
    })
    if expect:
        checks.update({"expected_M": member["execution_month"] == expect["M"],
                       "expected_O": member["feature_origin"] == expect["O"],
                       "expected_feature_count": bman.get("feature_count") == expect["features"],
                       "expected_roster": len(roster) == expect["roster"]
                       and all(v["rows"] == expect["roster"] for v in headers.values())})
    body = {"mode": mode, "run_id": run_id, "checks": checks, "passed": all(checks.values()),
            "actual": {"M": member["execution_month"], "O": member["feature_origin"],
                       "targets": {h: v["target_month"] for h, v in headers.items()},
                       "derived_horizons": status["derived"].get("horizons"),
                       "feature_count": bman.get("feature_count"), "feature_order_sha256": bman.get("feature_order_sha256"),
                       "roster": want_roster},
            "pre_generation": before["generation"], "post": {"generation": after["generation"], "pointer": after["pointer"]},
            "reservation": reservation, "record": rec, "delivery_manifest_files": len(manifest["files"]),
            "batch": {"batch_id": inference["batch_id"], "manifest_ref": inference["manifest_ref"], "headers": headers,
                      "generation": bman.get("generation"), "retained_inputs": bman.get("retained_inputs"),
                      "acceptance_consumed": bman.get("acceptance_consumed")},
            "run_status_generation_report": result.get("generation")}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({"passed": body["passed"], "failed": sorted(k for k, v in checks.items() if not v),
                      "actual": body["actual"]}, indent=1, default=str))
    return 0 if body["passed"] else 1


if __name__ == "__main__":
    if sys.argv[1] == "pre":
        pre(sys.argv[2], sys.argv[3])
    else:   # post MODE RUN PRE CTX OUT STATE M O FEATURES ROSTER
        m, run, pre_path, ctx, out, state, M, O, feats, ros = sys.argv[2:12]
        raise SystemExit(post(m, run, pre_path, ctx, out, state,
                              {"M": M, "O": O, "features": int(feats), "roster": int(ros)}))
