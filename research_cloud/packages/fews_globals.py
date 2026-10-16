"""FEWS NET ``geoxgb-v1-20261001`` pooled global screen: one package with the 72 retained globals (H4/H8/H12 x G1-G4
x 6 development origins).

Each global (``globals/h<H>/<G>/O<origin>[_<id>].ubj`` + record) predicted every area of its development fold
(``gscreen/predictions.csv.gz``, route ``pooled_arm``). Binding before predictions: the predictions and scores equal
``gscreen/selection.json`` outputs, whose ``prepared`` equals sha256(prepared ``outputs.json``); each global's bytes
equal its record ``booster_sha256`` and its record ``snapshot_sha256`` equals the run's prepared snapshot for that
horizon (bound to ``outputs.json``). Every saved row is re-predicted from the snapshot (unique keys per global,
finite probabilities, <= 1e-6, ``y_pred_code`` = argmax, truth equal to the snapshot class code). A row is served by
naming its global (horizon, G config, origin month); there is no key router.
"""
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, select_reference, sha256_file
from research_cloud.packages.fews_ordinary import LABELS, ROOT, month_index
from research_cloud.packages.fews_stage1 import agree, numeric, prepared

RUN = "geoxgb-v1-20261001"
PROB = [f"p_{l}" for l in LABELS]

ENTRY = '''"""Keyed loader for the FEWS NET v1 pooled global screen package (generated; see package.json)."""
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Model:
    def __init__(self, package_dir=ROOT):
        self.dir = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.n_features = len(pd.read_csv(os.path.join(package_dir, "deps", "feature_order.csv")))
        self.cache = {}

    def booster(self, unit):
        if unit not in self.cache:
            b = xgb.Booster()
            b.load_model(bytearray(open(os.path.join(self.dir, self.meta["units"][unit]["file"]), "rb").read()))
            self.cache[unit] = b
        return self.cache[unit]

    def predict(self, keys, X):
        """keys: DataFrame[horizon, g_config, origin_month, area, target_month]; X: (n, 162) in feature order."""
        X = np.array(X, dtype=np.float64, copy=True)
        if X.ndim != 2 or X.shape[1] != self.n_features:
            raise ValueError(f"X must be (n, {self.n_features})")
        if len(X) != len(keys):
            raise ValueError(f"{len(keys)} keys but {len(X)} feature rows")
        X[np.isinf(X)] = np.nan                      # native_xgb.clean
        keys = keys.reset_index(drop=True)
        horizon = pd.to_numeric(keys["horizon"], errors="coerce").to_numpy(np.float64)
        if not np.isfinite(horizon).all() or (horizon != np.round(horizon)).any():
            raise ValueError("horizon values must be finite whole numbers")
        units = [f"h{int(h)}/{g}/O{o}" for h, g, o in zip(horizon, keys["g_config"], keys["origin_month"])]
        for u in set(units):
            if u not in self.meta["units"]:
                raise KeyError(f"{u} is not a retained global of this run")
        proba = np.full((len(keys), 4), np.nan)
        for unit, idx in pd.Series(units).groupby(units).indices.items():
            pred = self.booster(unit).predict(xgb.DMatrix(X[idx], missing=np.nan, nthread=4))
            if pred.shape != (len(idx), 4):
                raise RuntimeError(f"{unit}: booster returned shape {pred.shape}")
            proba[idx] = pred
        out = keys[["horizon", "g_config", "origin_month", "area", "target_month"]].copy()
        out["unit"] = [self.meta["units"][u]["sha256"][:16] for u in units]
        out["route"] = "pooled_arm"
        for k, label in enumerate(("1", "2", "3", "4或5")):
            out[f"p_{label}"] = proba[:, k]
        out["y_pred_code"] = np.argmax(proba, axis=1).astype(np.int64)
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def globals_index(run_dir, snapshot_sha):
    """{unit: (ubj, record)} with each global hash-bound to its record and to the run's prepared snapshot."""
    out = {}
    for ubj in sorted((run_dir / "globals").glob("h*/G*/*.ubj")):
        record = json.load(open(ubj.with_suffix(".json")))
        h, g = int(ubj.parent.parent.name[1:]), ubj.parent.name
        stem = f"O{record['origin_month']}"
        named = ubj.stem == stem or ubj.stem.startswith(stem + "_")
        if (record["horizon"], record["g_config"]) != (h, g) or not named:
            raise PackageError(f"{ubj}: record identity differs from its path")
        if sha256_file(ubj) != record["booster_sha256"]:
            raise PackageError(f"{ubj}: bytes differ from the record booster_sha256")
        if record["snapshot_sha256"] != snapshot_sha[h]:
            raise PackageError(f"{ubj}: record snapshot differs from the prepared snapshot_h{h}")
        unit = f"h{h}/{g}/O{record['origin_month']}"
        if unit in out:
            raise PackageError(f"{unit}: two retained globals")
        out[unit] = (ubj, record)
    return out


def build(out_root, runtime, per_unit=16):
    run_dir = ROOT / RUN
    features, schema_sha, features_sha, snap_paths = prepared(run_dir)
    outputs_sha = sha256_file(run_dir / "prepared" / "manifests" / "outputs.json")
    selection = json.load(open(run_dir / "gscreen" / "selection.json"))
    if selection["prepared"] != outputs_sha:
        raise PackageError("gscreen selection.json prepared identity differs from outputs.json")
    for name, digest in selection["outputs"].items():
        if sha256_file(run_dir / "gscreen" / name) != digest:
            raise PackageError(f"gscreen/{name}: differs from selection.json outputs")
    snapshot_sha = {h: sha256_file(p) for h, p in snap_paths.items()}
    index = globals_index(run_dir, snapshot_sha)
    preds = pd.read_csv(run_dir / "gscreen" / "predictions.csv.gz", float_precision="round_trip",
                        dtype={"route": str, "target_month": str, "origin_month": str, "g_config": str})
    preds["unit_key"] = [f"h{int(h)}/{g}/O{o}" for h, g, o in zip(preds["horizon"], preds["g_config"], preds["origin_month"])]
    if set(preds["unit_key"]) != set(index) or (preds["route"] != "pooled_arm").any():
        raise PackageError("gscreen predictions do not cover exactly the retained globals")
    if preds.duplicated(["unit_key", "area", "target_month"]).any():
        raise PackageError("duplicate keys within a global's predictions")
    b = PackageBuilder(os.path.join(out_root, f"fews-{RUN}-globals"))
    units, refs, inputs, checks = {}, [], [], {}
    for h in (4, 8, 12):
        snap = pd.read_parquet(snap_paths[h], columns=["area", "target_month", "class_code"] + features)
        snap = snap.set_index(["area", "target_month"])
        for unit in sorted(u for u in index if u.startswith(f"h{h}/")):
            ubj, record = index[unit]
            rows = preds[preds["unit_key"] == unit].reset_index(drop=True)
            keys = list(zip(rows["area"].astype(int), rows["target_month"].map(month_index)))
            absent = ~pd.MultiIndex.from_tuples(keys).isin(snap.index)
            if absent.any():
                raise PackageError(f"{unit}: {int(absent.sum())} keys absent from the snapshot")
            data = snap.loc[keys]
            if not np.array_equal(data["class_code"].to_numpy(int), rows["y_true_code"].to_numpy(int)):
                raise PackageError(f"{unit}: saved truth differs from the snapshot class code")
            X = data[features].to_numpy(dtype=np.float64, copy=True)
            Xc = X.copy()
            Xc[np.isinf(Xc)] = np.nan
            import xgboost as xgb
            bst = xgb.Booster()
            bst.load_model(bytearray(ubj.read_bytes()))
            saved = numeric(rows, PROB)
            err = agree(saved, bst.predict(xgb.DMatrix(Xc, missing=np.nan, nthread=4)).astype(np.float64),
                        rows["y_pred_code"].to_numpy(int), unit)
            units[unit] = {"file": f"weights/{unit}.ubj", "sha256": record["booster_sha256"],
                           "record": f"weights/{unit}.json", "fit_keys_sha256": record["fit_keys_sha256"]}
            b.add_file(str(ubj), units[unit]["file"], record["booster_sha256"], None)
            b.add_file(str(ubj.with_suffix(".json")), units[unit]["record"])
            checks[unit] = {"rows": int(len(rows)), "max_abs_err": err}
            frame = rows[["horizon", "g_config", "origin_month", "area", "target_month", "unit_key"] + PROB + ["y_pred_code"]].copy()
            frame["unit"] = record["booster_sha256"][:16]
            frame["route"] = "pooled_arm"
            srt = np.sort(saved, axis=1)
            ref = select_reference(frame, "unit_key", pd.Series(srt[:, -1] - srt[:, -2], index=frame.index),
                                   ["unit_key", "area", "target_month"], per_unit=per_unit)
            refs.append(ref)
            inputs.append(X[ref.index.to_numpy()])
            print(unit, checks[unit], flush=True)
    for name in ("selection.json", "predictions.csv.gz", "scores.csv"):
        b.add_file(str(run_dir / "gscreen" / name), f"deps/source/gscreen/{name}")
    for f in ("outputs.json", "features.json", "identity.json"):
        b.add_file(str(run_dir / "prepared" / "manifests" / f), f"deps/source/prepared/{f}")
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": features}).to_csv(index=False).encode())
    ref = pd.concat(refs, ignore_index=True)
    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(np.vstack(inputs), dtype=np.float64), allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    b.add_bytes("reference/expected.csv", ref[["horizon", "g_config", "origin_month", "area", "target_month", "unit", "route"]
                                              + PROB + ["y_pred_code"]].to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())
    total = {"globals": len(units), "rows": sum(c["rows"] for c in checks.values()),
             "max_abs_err": max(c["max_abs_err"] for c in checks.values())}
    return b.finalize({
        "family": "fewsnet_global_screen", "status": "complete", "gaps": [],
        "identity": {"run": RUN, "stage": "gscreen", "selected": selection["selected"], "rule": selection["rule"],
                     "code": selection.get("code")},
        "fitted_units": len(units), "units": units,
        "binding": {"schema_sha256": schema_sha, "features_json_sha256": features_sha, "snapshots": {f"h{h}": s for h, s in snapshot_sha.items()},
                    "rule": "gscreen outputs == selection.json; selection prepared == sha256(outputs.json); global bytes "
                            "== record booster_sha256; record snapshot_sha256 == prepared snapshot"},
        "full_cohort_check": {"total": total, "globals": checks},
        "routing": {"by": "explicit global (horizon, g_config, origin_month)", "feature_order": "deps/feature_order.csv",
                    "routes_in_version": ["pooled_arm"]},
        "runtime": {"original": selection.get("runtime"), "linux": runtime},
        "code": {"loader": "thin reimplementation (native_xgb.clean/proba, argmax) accepted by replay"},
        "loader": {"entry": "loader/entry.py", "keys": ["horizon", "g_config", "origin_month", "area", "target_month"],
                   "call": "load(package_dir).predict(keys[horizon,g_config,origin_month,area,target_month], X)",
                   "inputs": "prepared float64 X: the run's 162 prepared snapshot features for the area and target month; "
                             "snapshots preserved with the run archive",
                   "unserved_keys": "KeyError for a global not retained by this run"},
        "reference": {"rows": int(len(ref)), "per_unit_cap": per_unit, "per_unit_cap_scope": "per global",
                      "compare_columns": PROB + ["y_pred_code"], "routes_covered": ["pooled_arm"],
                      "selection": "per global: half nearest an argmax tie, rest by key hash"},
        "tolerance": {"declared_before_comparison": True, "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for p_1..p_4",
                      "decision": "y_pred_code exactly", "routing": "unit and route exactly"},
    })


def main():
    import argparse
    from research_cloud.packages.build_fews_scen import RUNTIME
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    m = build(args.out, RUNTIME)
    print(m["status"], m["full_cohort_check"]["total"], m["reference"]["rows"])


if __name__ == "__main__":
    main()
