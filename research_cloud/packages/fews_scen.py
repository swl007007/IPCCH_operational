"""FEWS NET ``scen-b43ef6a-v1`` actual-case packages (4 cases x pooled/system arm).

Each actual case (H4/H8 x 2025-06/2025-10; ``scenario_actual/hH/T``) predicted every prediction area with the frozen
pooled global booster (``gate.json`` ``global``); the system arm additionally routed gated regions to local
continuation boosters (``route == local_model``). Those 18 local boosters were never written (``save_fold(..., False)``)
and the user accepted an explicit incomplete-history exception for exactly these rows
(``fews/missing-local-boosters-receipt.md``). Therefore:

* ``pooled`` package: complete - every area takes the retained global;
* ``system`` package: ``incomplete_history_accepted_exception`` - global-routed areas (``global_fallback:*``,
  ``unmapped_area_global``) take the same global; ``local_model`` areas raise LocalBoosterNotRetained, are excluded
  from references and are listed in ``package.json``. No substitute is produced.

Inputs are rebuilt on Linux with FEWS's own builders (``scenario_context`` minus ``accept_prepared``, the historical
Windows identity guard, which is not changed): the certified pinned panel (sha256 re-checked), the hashed covariate
extension manifest (its sha equal to the case's ``extension_manifest_sha256``; Windows paths relocated to /mnt/c and
re-hashed), ``Availability`` and ``ScenarioPanel(k=0, strategy, gate_k)``. Binding: the rebuilt ``Availability``
input digest equals the case's recorded ``availability_inputs_sha256`` and the rebuilt panel identity equals the
global's ``snapshot_sha256`` - both computed as the original Windows run did, with ``to_csv`` line terminators
``\\r\\n`` (``os.linesep`` there). Every one of the cohort's rows is predicted at build time and compared with the saved
predictions; the package keeps a reference sample.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file

RUN = Path("/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1")
EXTENSION = Path("/mnt/c/Users/swl00/geoxgb_runs/scen-b43ef6a-v1.actual-inputs-v1/extension_manifest.v2.json")
CASES = (("h4", "2025-06"), ("h4", "2025-10"), ("h8", "2025-06"), ("h8", "2025-10"))
CLASS_LABELS = ("1", "2", "3", "4或5")
PROB = [f"p_{c}" for c in CLASS_LABELS]
LOCAL = "local_model"
RECEIPT = Path("/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/"
               "10-16-gcp-research-modeling-migration/research/fews/missing-local-boosters-receipt.md")

ENTRY = '''"""Keyed loader for one FEWS NET scen-b43ef6a-v1 actual-case package (generated; see package.json)."""
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LocalBoosterNotRetained(KeyError):
    """The original system routed this area to a local continuation booster that was never saved."""


class Model:
    def __init__(self, package_dir=ROOT):
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.arm = self.meta["arm"]
        self.booster = xgb.Booster()
        self.booster.load_model(bytearray(open(os.path.join(package_dir, "weights", "global.ubj"), "rb").read()))
        self.n_features = len(pd.read_csv(os.path.join(package_dir, "deps", "feature_order.csv")))
        if self.booster.num_features() != self.n_features:
            raise RuntimeError(f"booster expects {self.booster.num_features()} features, feature_order declares {self.n_features}")
        route = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"), dtype={"route": str, "target_month": str})
        self.route = {(int(a), t): (r, c) for a, t, r, c in route[["area", "target_month", "route", "cluster_id"]].itertuples(index=False)}

    def predict(self, keys, X):
        """keys: DataFrame[area, target_month]; X: (len(keys), F) rows in deps/feature_order.csv order (F columns)."""
        X = np.array(X, dtype=np.float64, copy=True)
        if X.shape != (len(keys), self.n_features):
            raise ValueError(f"X must be ({len(keys)}, {self.n_features}) for {len(keys)} keys, got {X.shape}")
        routes = [self.route[(int(a), str(t))] for a, t in zip(keys["area"], keys["target_month"])]   # KeyError if unserved
        if self.arm == "system":
            local = [i for i, (r, _) in enumerate(routes) if r == "local_model"]
            if local:
                raise LocalBoosterNotRetained(f"{len(local)} rows route to local boosters that were not retained "
                                              "(accepted incomplete-history exception)")
        X[np.isinf(X)] = np.nan                      # native_xgb.clean
        proba = self.booster.predict(xgb.DMatrix(X, missing=np.nan, nthread=4))
        if proba.ndim != 2 or proba.shape[1] != 4:
            raise RuntimeError(f"booster returned shape {proba.shape}, not (n, 4)")
        out = keys.reset_index(drop=True)[["area", "target_month"]].copy()
        out["unit"] = self.meta["global"]["booster_sha256"][:16]
        out["route"] = [r if self.arm == "system" else "pooled" for r, _ in routes]
        for k, label in enumerate(("1", "2", "3", "4或5")):
            out[f"p_{label}"] = proba[:, k].astype(np.float64)
        out["y_pred_code"] = np.argmax(proba, axis=1).astype(np.int64)   # fourclass.argmax_codes: first max wins
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def wsl(path):
    return "/mnt/c/" + path[3:].replace("\\", "/") if path[1:3] == ":\\" else path


def crlf_digest_availability(ctx, av):
    payload = [ctx.obs.sort_values(["area", "month"]).to_csv(index=False, lineterminator="\r\n"),
               ctx.ledger.frame[list(av.LEDGER_COLUMNS)].to_csv(index=False, lineterminator="\r\n"),
               json.dumps(ctx.alignment, sort_keys=True, default=str), str(ctx.horizon), json.dumps(ctx.features)]
    return hashlib.sha256("\x1e".join(payload).encode()).hexdigest()


def crlf_panel_sha(sp, availability_digest):
    """ScenarioPanel.sha256 as the Windows run computed it: its identity embeds the ledger digest and the
    Availability input digest, both of which depend on to_csv's os.linesep."""
    led = sp.av.ledger
    identity = dict(sp.identity)
    identity["availability_inputs_sha256"] = availability_digest
    identity["ledger_sha256"] = hashlib.sha256(led.frame[["cycle_id", "product", "country", "reference_month", "release_date",
                                                           "evidence"]].to_csv(index=False, lineterminator="\r\n").encode()).hexdigest()
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def fews_modules(src):
    for p in (src, os.path.join(src, "scripts")):
        if p not in sys.path:
            sys.dont_write_bytecode = True   # never write __pycache__ into the source tree
            sys.path.insert(0, p)
    import run_experiment as rx
    from src.experiment import availability as av, stage3 as s3
    from src.feature import fourclass_features as ff
    from src.utils.run_identity import SCHEMA_PATH
    return rx, av, s3, ff, SCHEMA_PATH


def rebuild_panel(src, horizon, fold):
    """The case's target cohort, rebuilt and bound to the recorded input digests."""
    rx, av, s3, ff, schema_path = fews_modules(src)
    if sha256_file(EXTENSION) != fold["extension_manifest_sha256"]:
        raise PackageError("extension manifest differs from the case's recorded sha256")
    manifest = json.load(open(EXTENSION))
    manifest["path"] = wsl(manifest["path"])
    if sha256_file(manifest["path"]) != manifest["sha256"]:
        raise PackageError("relocated extension file differs from its manifest sha256")
    tmp = Path(tempfile.mkdtemp()) / "extension_manifest.json"
    tmp.write_text(json.dumps(manifest))
    manifests = RUN / "prepared" / "manifests"
    if sha256_file(manifests / "outputs.json") != fold["prepared_outputs_sha256"]:
        raise PackageError("prepared outputs manifest differs from the case's recorded sha256")
    schema = rx.load_schema(schema_path)
    alignment = json.loads((manifests / "alignment.json").read_text(encoding="utf-8"))
    ledger = av.ReleaseLedger(pd.read_csv(manifests / "release_ledger.csv", dtype=str), real=True)
    obs = rx.read_csv(RUN / "prepared" / "ledgers" / "observations.csv")[["area", "month", "country", "class_code"]]
    source = json.loads((manifests / "sources.json").read_text(encoding="utf-8"))["sources"]["panel"]
    panel = rx.load_extension(tmp, schema, rx._certified_panel(Path(wsl(source["path"])), source["sha256"], schema))
    ctx = av.Availability(obs, ledger, ff.Scaffold(panel, rx._covariate_columns(schema)), schema, horizon, alignment, truth=None)
    digest = crlf_digest_availability(ctx, av)
    if digest != fold["availability_inputs_sha256"]:
        raise PackageError("rebuilt Availability inputs differ from the recorded availability_inputs_sha256")
    sp = s3.ScenarioPanel(ctx, 0, fold["strategy"], gate_k=fold["gate_k"])
    src_rows, test = sp.target_rows(s3.mi(fold["target_month"]))
    return src_rows, crlf_panel_sha(sp, digest), list(ctx.features)


def locate_global(horizon, gate_global):
    """The stored global whose bytes hash to the gate's booster_sha256, with its record."""
    for ubj in sorted((RUN / "scenario_globals" / f"h{horizon}").glob("G*/*.ubj")):
        if sha256_file(ubj) == gate_global["booster_sha256"]:
            record = json.load(open(ubj.with_suffix(".json")))
            if record.get("booster_sha256") != gate_global["booster_sha256"] \
                    or record.get("fit_keys_sha256") != gate_global["fit_keys_sha256"] \
                    or record.get("origin_month") != gate_global["origin_month"]:
                raise PackageError(f"{ubj.name}: stored record disagrees with the gate's global identity")
            return ubj, record
    raise PackageError("the gate's global booster is not in scenario_globals")


def build_case(out_root, horizon_label, target, src, runtime, per_unit=400):
    import xgboost as xgb
    h = int(horizon_label[1:])
    case = RUN / "scenario_actual" / horizon_label / target
    ensure_local([str(case / n) for n in ("fold.json", "gate.json", "predictions.csv.gz", "pooled_predictions.csv.gz")])
    actual = json.load(open(RUN / "scenario_actual" / "actual.json"))
    fold = json.load(open(case / "fold.json"))
    if sha256_file(case / "fold.json") != actual["cases"][f"{horizon_label}_{target}"]["fold_sha256"]:
        raise PackageError("fold.json differs from actual.json")
    for name in ("gate.json", "predictions.csv.gz", "pooled_predictions.csv.gz"):
        if sha256_file(case / name) != actual["outputs"][f"{horizon_label}/{target}/{name}"]:
            raise PackageError(f"{name} differs from actual.json outputs")
    gate = json.load(open(case / "gate.json"))
    ubj, record = locate_global(h, gate["global"])
    src_rows, panel_sha, features = rebuild_panel(src, h, fold)
    if record.get("snapshot_sha256") != panel_sha:
        raise PackageError("rebuilt panel identity differs from the global's snapshot_sha256")
    keys = pd.DataFrame({"area": src_rows.area, "target_month": target})
    booster = xgb.Booster()
    booster.load_model(bytearray(ubj.read_bytes()))
    X = np.array(src_rows.X, dtype=np.float64, copy=True)
    X[np.isinf(X)] = np.nan
    proba = booster.predict(xgb.DMatrix(X, missing=np.nan, nthread=4)).astype(np.float64)

    metas = {}
    for arm, file in (("pooled", "pooled_predictions.csv.gz"), ("system", "predictions.csv.gz")):
        saved = pd.read_csv(case / file, dtype={"route": str})
        saved = saved.set_index("area").loc[keys["area"]].reset_index()
        if len(saved) != len(keys):
            raise PackageError(f"{arm}: saved predictions do not cover the rebuilt cohort")
        served = (saved["route"] != LOCAL).to_numpy() if arm == "system" else np.ones(len(saved), bool)
        err = np.abs(saved[PROB].to_numpy(dtype=np.float64)[served] - proba[served])
        decided = (saved["y_pred_code"].to_numpy()[served] == np.argmax(proba[served], axis=1))
        cohort = {"rows": int(len(saved)), "served_rows": int(served.sum()), "max_abs_err": float(err.max()),
                  "decision_matches": int(decided.sum())}
        if not (np.isfinite(err).all() and (err <= 1e-6).all()) or not decided.all():
            raise PackageError(f"{arm}: full-cohort check failed {cohort}")
        out_dir = os.path.join(out_root, f"fews-scen-b43ef6a-v1-actual-{horizon_label}-{target}-{arm}")
        b = PackageBuilder(out_dir)
        b.add_file(str(ubj), "weights/global.ubj", record["booster_sha256"], None)
        b.add_file(str(ubj.with_suffix(".json")), "weights/global.json")
        for name in ("fold.json", "gate.json", "predictions.csv.gz", "pooled_predictions.csv.gz"):
            b.add_file(str(case / name), f"deps/source/{name}")
        b.add_file(str(RUN / "scenario_actual" / "actual.json"), "deps/source/actual.json")
        b.add_file(str(EXTENSION), "deps/source/extension_manifest.v2.json")
        b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": features}).to_csv(index=False).encode())
        routing = saved[["area", "target_month", "route", "cluster_id"]].copy()
        b.add_bytes("deps/routing.csv", routing.to_csv(index=False).encode())
        frame = saved.copy()
        frame["row"] = np.arange(len(saved))
        frame["unit"] = record["booster_sha256"][:16]
        frame["route"] = saved["route"] if arm == "system" else "pooled"
        frame = frame[served].reset_index(drop=True)
        margin = np.sort(frame[PROB].to_numpy(dtype=np.float64), axis=1)
        boundary = pd.Series(margin[:, -1] - margin[:, -2])
        ref = select_reference(frame, "unit", boundary, ["area", "target_month"], per_unit=per_unit, cover_cols=("route",))
        buf = io.BytesIO()
        np.save(buf, np.ascontiguousarray(src_rows.X[ref["row"].to_numpy()], dtype=np.float64), allow_pickle=False)
        b.add_bytes("reference/inputs.npy", buf.getvalue())
        b.add_bytes("reference/expected.csv", ref[["area", "target_month", "unit", "route"] + PROB + ["y_pred_code"]]
                    .to_csv(index=False, float_format="%.17g").encode())
        b.add_bytes("loader/entry.py", ENTRY.encode())
        local_rows = saved.loc[~served, ["area", "cluster_id"]] if arm == "system" else saved.iloc[:0]
        exception = None
        if arm == "system":   # the user-approved receipt travels with the package, hash-bound
            b.add_file(str(RECEIPT), "deps/exception/missing-local-boosters-receipt.md")
            exception = {"receipt": "deps/exception/missing-local-boosters-receipt.md", "receipt_sha256": sha256_file(RECEIPT),
                         "disposition": "user-approved incomplete-history exception for scen-b43ef6a-v1 actual cases only",
                         "missing_local_units": [{"region": str(region), "child_sha256": rec.get("booster_sha256"),
                                                  "parent_sha256": rec.get("parent_sha256"), "rounds_total": rec.get("rounds_total")}
                                                 for region, rec in sorted(gate.get("locals", {}).items())],
                         "limits": "no full system replay; no global or pooled substitution under the system identity"}
        gaps = [] if arm == "pooled" else [f"{len(local_rows)} local_model rows: continuation boosters not retained "
                                            "(accepted incomplete-history exception)"]
        metas[arm] = b.finalize({
            "family": "fewsnet_scenario_actual", "arm": arm, "lead_months": h, "target_month": target,
            "identity": {"run": "scen-b43ef6a-v1", "phase": "scenario_actual", "case": f"{horizon_label}_{target}",
                         "strategy": fold["strategy"], "map_id": fold["map_id"], "gate_k": fold["gate_k"]},
            "status": "complete" if arm == "pooled" else "incomplete_history_accepted_exception", "gaps": gaps,
            "unreplayable": {"rows": int(len(local_rows)), "areas": local_rows["area"].astype(int).tolist(),
                             "clusters": sorted(set(local_rows["cluster_id"].astype(int).tolist())), **exception}
            if arm == "system" else None,
            "fitted_units": 1, "global": {"booster_sha256": record["booster_sha256"], "origin_month": record["origin_month"],
                                          "fit_keys_sha256": record["fit_keys_sha256"], "file": ubj.name},
            "binding": {"availability_inputs_sha256": fold["availability_inputs_sha256"],
                        "panel_snapshot_sha256": panel_sha, "extension_manifest_sha256": fold["extension_manifest_sha256"],
                        "prepared_outputs_sha256": fold["prepared_outputs_sha256"],
                        "line_terminator_note": "both digests reproduced with to_csv lineterminator='\\r\\n', the original "
                                                "Windows run's os.linesep; the rebuilt inputs are otherwise byte-identical"},
            "full_cohort_check": cohort,
            "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "served_keys": int(served.sum()),
                        "routes_in_version": sorted(frame["route"].unique())},
            "runtime": {"original": actual.get("runtime"), "linux": runtime},
            "code": {"loader": "thin reimplementation (native_xgb.clean/proba, fourclass.argmax_codes) accepted by replay",
                     "builders": "FEWSNETGeoXGBExperiment scenario_context pieces at Food_Crisis_Cluster@6c1ebf72",
                     "original_code_sha256": actual.get("code")},
            "loader": {"entry": "loader/entry.py", "keys": ["area", "target_month"],
                       "call": "load(package_dir).predict(keys[area,target_month], X)",
                       "inputs": f"prepared float64 X: {len(features)} columns in deps/feature_order.csv order (FEWS scenario "
                                 "features at the case origin). This package does not rebuild raw features; their "
                                 "reconstruction uses the versioned input/source snapshot (pinned panel, hashed covariate "
                                 "extension, prepared ledgers) preserved separately. Windows paths in deps/source records are "
                                 "provenance only.",
                       "unserved_keys": "KeyError; system arm local_model rows: LocalBoosterNotRetained"},
            "reference": {"rows": int(len(ref)), "per_unit_cap": per_unit, "compare_columns": PROB + ["y_pred_code"],
                          "routes_covered": sorted(ref["route"].unique()),
                          "selection": "half nearest an argmax tie (top-two probability margin), rest by key hash"},
            "tolerance": {"declared_before_comparison": True, "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for p_1..p_4",
                          "decision": "y_pred_code exactly", "routing": "unit and route exactly"},
        })
    return metas
