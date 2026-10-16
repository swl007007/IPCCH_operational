"""FEWS NET ``confirm-onset-v1`` pooled packages (S0, S3; H4, origin 2025-10, target 2026-02).

Each scenario's pooled arm predicted every area with the retained global booster (``gate.json`` ``global``), so it is
complete. The system arm routed gated regions to local continuation boosters that were never saved (2,446 of 11,436
system rows); its disposition is pending with the user and it is NOT packaged here - no global or pooled substitute
is produced under the system identity.

Inputs are rebuilt as ``run_confirm.build_ctx`` did, with FEWS's own builders: the scenario's saved observations and
release ledger (sha256 equal to ``steps/inputs.json``), the certified pinned panel of ``scen-b43ef6a-v1`` (sources
sha re-checked), the hashed v3 covariate extension (manifest sha equal to ``steps/extension.json``; Windows path
relocated and the CSV re-hashed) and ``alignment_v3.json`` (sha equal to ``steps/alignment.json``). Binding: the
rebuilt Availability digest equals the fold's ``availability_inputs_sha256`` and the rebuilt panel identity equals
the global's ``snapshot_sha256``, both computed with the original Windows ``\\r\\n`` line terminators. Every pooled row
is re-predicted at build time (<= 1e-6, ``y_pred_code`` = argmax); saved prediction files equal ``fold.json`` outputs
and ``predictions_frozen.json``.
"""
import io
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, select_reference, sha256_file
from research_cloud.packages.fews_scen import (ENTRY as SCEN_ENTRY, PROB, crlf_digest_availability, crlf_panel_sha,
                                               fews_modules, wsl)

RUN = Path("/mnt/c/Users/swl00/geoxgb_runs/confirm-onset-v1")
RUN10 = Path("/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1")
SCENARIOS = ("S0", "S3")
ENTRY = SCEN_ENTRY.replace("one FEWS NET scen-b43ef6a-v1 actual-case package", "one FEWS NET confirm-onset-v1 pooled package")


def rebuild(src, scenario, fold):
    import json as _json
    rx, av, s3, ff, schema_path = fews_modules(src)
    steps = _json.load(open(RUN / "steps" / "inputs.json"))[scenario]
    d = RUN / scenario
    if sha256_file(d / "observations.csv") != steps["observations_sha256"] \
            or sha256_file(d / "release_ledger.csv") != steps["ledger_sha256"]:
        raise PackageError(f"{scenario}: observations/ledger differ from steps/inputs.json")
    extension = _json.load(open(RUN / "steps" / "extension.json"))
    ext_path = RUN / "extension_v3" / "extension_manifest_v3.json"
    if sha256_file(ext_path) != extension["manifest_sha256"]:
        raise PackageError("extension_manifest_v3 differs from steps/extension.json")
    manifest = _json.load(open(ext_path))
    manifest["path"] = wsl(manifest["path"])
    if sha256_file(manifest["path"]) != manifest["sha256"] or manifest["sha256"] != extension["csv_sha256"]:
        raise PackageError("relocated v3 extension CSV differs from its manifest")
    tmp = Path(tempfile.mkdtemp()) / "extension_manifest_v3.json"
    tmp.write_text(_json.dumps(manifest))
    if sha256_file(RUN / "alignment_v3.json") != _json.load(open(RUN / "steps" / "alignment.json"))["alignment_v3_sha256"]:
        raise PackageError("alignment_v3.json differs from steps/alignment.json")
    schema = _json.load(open(schema_path))
    source = _json.load(open(RUN10 / "prepared" / "manifests" / "sources.json"))["sources"]["panel"]
    pinned = rx._certified_panel(Path(wsl(source["path"])), source["sha256"], schema)
    panel = rx.load_extension(tmp, schema, pinned)
    obs = pd.read_csv(d / "observations.csv")
    led = pd.read_csv(d / "release_ledger.csv", dtype=str)
    ctx = av.Availability(obs[["area", "month", "country", "class_code"]], av.ReleaseLedger(led, real=True),
                          ff.Scaffold(panel, rx._covariate_columns(schema)), schema, int(fold["horizon"]),
                          _json.load(open(RUN / "alignment_v3.json")), truth=None)
    digest = crlf_digest_availability(ctx, av)
    if digest != fold["availability_inputs_sha256"]:
        raise PackageError(f"{scenario}: rebuilt Availability digest differs from the fold record")
    sp = s3.ScenarioPanel(ctx, 0, fold["strategy"], gate_k=fold["gate_k"])
    rows, _ = sp.target_rows(s3.mi(fold["target_month"]))
    return rows, crlf_panel_sha(sp, digest), list(ctx.features), schema_path


def build_scenario(out_root, scenario, src, runtime, per_unit=400):
    import xgboost as xgb
    d = RUN / scenario
    fold = json.load(open(d / "fold" / "fold.json"))
    frozen = json.load(open(RUN / "predictions_frozen.json"))["files"]
    for name in ("gate.json", "pooled_predictions.csv.gz", "predictions.csv.gz", "gate_pairs.csv.gz"):
        digest = sha256_file(d / "fold" / name)
        if digest != fold["outputs"][name] or digest != frozen[f"{scenario}/fold/{name}"]:
            raise PackageError(f"{scenario}/{name}: differs from fold.json outputs / predictions_frozen.json")
    if sha256_file(d / "fold" / "fold.json") != frozen[f"{scenario}/fold/fold.json"]:
        raise PackageError(f"{scenario}: fold.json differs from predictions_frozen.json")
    gate = json.load(open(d / "fold" / "gate.json"))
    want = gate["global"]
    ubj = next((p for p in sorted((d / "globals").glob("h*/G*/*.ubj")) if sha256_file(p) == want["booster_sha256"]), None)
    if ubj is None:
        raise PackageError(f"{scenario}: the gate's global booster is not retained")
    record = json.load(open(ubj.with_suffix(".json")))
    if (record["booster_sha256"], record["fit_keys_sha256"], record["origin_month"]) != \
            (want["booster_sha256"], want["fit_keys_sha256"], want["origin_month"]):
        raise PackageError(f"{scenario}: global record disagrees with the gate")
    rows, panel_sha, features, schema_path = rebuild(src, scenario, fold)
    if record["snapshot_sha256"] != panel_sha:
        raise PackageError(f"{scenario}: rebuilt panel identity differs from the global's snapshot_sha256")
    booster = xgb.Booster()
    booster.load_model(bytearray(ubj.read_bytes()))
    X = np.array(rows.X, dtype=np.float64, copy=True)
    Xc = X.copy()
    Xc[np.isinf(Xc)] = np.nan
    proba = booster.predict(xgb.DMatrix(Xc, missing=np.nan, nthread=4)).astype(np.float64)
    saved = pd.read_csv(d / "fold" / "pooled_predictions.csv.gz", dtype={"route": str, "target_month": str})
    order = pd.Series(np.arange(len(saved)), index=saved["area"].astype(int))
    if len(saved) != len(rows.area) or set(order.index) != set(np.asarray(rows.area, dtype=int)):
        raise PackageError(f"{scenario}: saved pooled predictions do not cover the rebuilt cohort")
    saved = saved.iloc[order.loc[np.asarray(rows.area, dtype=int)].to_numpy()].reset_index(drop=True)
    err = np.abs(saved[PROB].to_numpy(np.float64) - proba)
    decided = saved["y_pred_code"].to_numpy(int) == np.argmax(proba, axis=1)
    cohort = {"rows": int(len(saved)), "max_abs_err": float(err.max()), "decision_matches": int(decided.sum())}
    if not (np.isfinite(err).all() and (err <= 1e-6).all()) or not decided.all() or (saved["route"] != "pooled_arm").any():
        raise PackageError(f"{scenario}: pooled full-cohort check failed {cohort}")
    system = pd.read_csv(d / "fold" / "predictions.csv.gz", dtype={"route": str})
    local = system[system["route"] == "local_model"]
    b = PackageBuilder(os.path.join(out_root, f"fews-confirm-onset-v1-{scenario}-pooled"))
    b.add_file(str(ubj), "weights/global.ubj", record["booster_sha256"], None)
    b.add_file(str(ubj.with_suffix(".json")), "weights/global.json")
    for name in ("fold.json", "gate.json", "pooled_predictions.csv.gz", "predictions.csv.gz"):
        b.add_file(str(d / "fold" / name), f"deps/source/{name}")
    for rel in ("predictions_frozen.json", "inputs_manifest.json", "steps/inputs.json", "steps/extension.json",
                "steps/alignment.json", "alignment_v3.json", "extension_v3/extension_manifest_v3.json"):
        b.add_file(str(RUN / rel), f"deps/source/{rel}")
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": features}).to_csv(index=False).encode())
    routing = saved[["area", "target_month", "route", "cluster_id"]].copy()
    b.add_bytes("deps/routing.csv", routing.to_csv(index=False).encode())
    frame = saved.copy()
    frame["row"] = np.arange(len(saved))
    frame["unit"] = record["booster_sha256"][:16]
    frame["route"] = "pooled"
    margin = np.sort(frame[PROB].to_numpy(np.float64), axis=1)
    ref = select_reference(frame, "unit", pd.Series(margin[:, -1] - margin[:, -2]), ["area", "target_month"],
                           per_unit=per_unit, cover_cols=("route",))
    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(X[ref["row"].to_numpy()], dtype=np.float64), allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    b.add_bytes("reference/expected.csv", ref[["area", "target_month", "unit", "route"] + PROB + ["y_pred_code"]]
                .to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())
    return b.finalize({
        "family": "fewsnet_confirm_onset_pooled", "arm": "pooled", "lead_months": int(fold["horizon"]),
        "target_month": fold["target_month"], "status": "complete", "gaps": [],
        "identity": {"run": "confirm-onset-v1", "scenario": scenario, "phase": fold["phase"], "role": fold["role"],
                     "strategy": fold["strategy"], "map_id": fold["map_id"], "gate_k": fold["gate_k"]},
        "system_arm_not_packaged": {"rows": int(len(system)), "local_model_rows": int(len(local)),
                                    "disposition": "pending user disposition (fews/confirm-onset-missing-local-boosters-"
                                                   "receipt.md); the scen-b43ef6a-v1 exception does not apply",
                                    "no_substitute": True},
        "fitted_units": 1, "global": {"booster_sha256": record["booster_sha256"], "origin_month": record["origin_month"],
                                      "fit_keys_sha256": record["fit_keys_sha256"], "file": ubj.name},
        "binding": {"availability_inputs_sha256": fold["availability_inputs_sha256"], "panel_snapshot_sha256": panel_sha,
                    "steps": "observations/ledger == steps/inputs.json; extension v3 == steps/extension.json; "
                             "alignment_v3 == steps/alignment.json; fold outputs == predictions_frozen.json",
                    "schema": {"path": str(schema_path), "sha256": sha256_file(schema_path)},
                    "line_terminator_note": "digests reproduced with to_csv lineterminator='\\r\\n' (original Windows "
                                            "os.linesep)"},
        "full_cohort_check": cohort,
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "served_keys": int(len(saved)),
                    "routes_in_version": ["pooled"]},
        "runtime": {"original": fold.get("runtime"), "linux": runtime},
        "code": {"loader": "thin reimplementation (native_xgb.clean/proba, fourclass.argmax_codes) accepted by replay",
                 "original_code_sha256": fold.get("code")},
        "loader": {"entry": "loader/entry.py", "keys": ["area", "target_month"],
                   "call": "load(package_dir).predict(keys[area,target_month], X)",
                   "inputs": f"prepared float64 X: {len(features)} columns in deps/feature_order.csv order (scenario "
                             "features at the 2025-10 origin). Raw reconstruction uses the preserved run inputs; Windows "
                             "paths in deps/source are provenance only.",
                   "unserved_keys": "KeyError"},
        "reference": {"rows": int(len(ref)), "per_unit_cap": per_unit, "compare_columns": PROB + ["y_pred_code"],
                      "routes_covered": ["pooled"], "selection": "half nearest an argmax tie, rest by key hash"},
        "tolerance": {"declared_before_comparison": True, "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for p_1..p_4",
                      "decision": "y_pred_code exactly", "routing": "unit and route exactly"},
    })


def main():
    import argparse
    from research_cloud.packages.build_fews_scen import RUNTIME, SRC
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--fews-src", default=SRC)
    args = ap.parse_args()
    for scenario in SCENARIOS:
        if os.path.exists(os.path.join(args.out, f"fews-confirm-onset-v1-{scenario}-pooled", "package.json")):
            print(scenario, "exists")
            continue
        m = build_scenario(args.out, scenario, args.fews_src, RUNTIME)
        print(scenario, m["status"], m["full_cohort_check"], m["reference"]["rows"], flush=True)


if __name__ == "__main__":
    main()
