"""FEWS NET map-transfer diagnostic runs: D42 (current vs old D34 map) and D43 (random vs temporal map), one package
per run.

Each pair cell refit region continuation boosters on a spatial map's named regions; a row is routed by its area's
partition in that map (``stage1_map_transfer.route``): an eligible named region with a saved booster -> that region's
booster; ``s-1`` (no search rows), an area absent from the map (``missing``) or an ineligible region
(``insufficient_support``) -> the cell's current root (a D34 checkpoint, ``pair.json`` ``root_booster_sha256``).
Maps are the D32 ``assignment_evidence.csv`` of the named candidate (D34 stage candidates; D43's temporal candidates
live under the pair), parsed as the producer did (area -> partition id with leading zeros; ``s-1`` <=> 0 search
rows).

Binding before predictions: every consumed run file (rows, ``pair.json``, region records and weights, the run's own
candidates, gate, summary) hashes to the run's ``completion.json`` ``outputs``; assignment evidence sha256 equals
``pair.json`` maps and the candidate record; every region booster equals its record ``ubj_sha256`` and continuation ``booster_sha256``; region records name the pair root; the
root checkpoint equals ``root_booster_sha256``; D34 snapshots equal the run identity. At build time every saved row of
every part is re-routed (``region_<arm>``/``route_<arm>`` exactly) and re-predicted for both map arms and the root
(<= 1e-6, argmax equal). D43 saved only E3 rows. The global+20 arm is D35's (packaged with D35); search boosters and
equivalence/search evidence are preserved with the run, not packaged.
"""
import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, select_reference, sha256_file
from research_cloud.packages.fews_ordinary import D34, LABELS, ROOT, frozen, month_index

S_NONE = "s-1"
RUNS = {
    "geoxgb-d42-map-transfer-20261002": {"cells_dir": "", "arms": {"current": "current_map_refit", "old": "old_map_refit"},
                                         "parts": ("C", "E3"), "root_map": "current"},
    "geoxgb-d43-temporal-map-refit-20261002": {"cells_dir": "pairs", "parts": ("E3",), "root_map": "random",
                                               "arms": {"random": "random_map_refit", "temporal": "temporal_map_refit"}},
}

ENTRY = '''"""Keyed loader for one FEWS NET map-transfer run package (generated; see package.json)."""
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
        table = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"),
                            dtype={"cell": str, "arm": str, "region": str, "reason": str}, keep_default_na=False)
        self.route = {(c, a, int(area)): (r, why) for c, a, area, r, why in
                      table[["cell", "arm", "area", "region", "reason"]].itertuples(index=False)}
        self.n_features = len(pd.read_csv(os.path.join(package_dir, "deps", "feature_order.csv")))
        self.cache = {}

    def booster(self, unit):
        if unit not in self.cache:               # lazy: a run holds hundreds of region boosters
            b = xgb.Booster()
            b.load_model(bytearray(open(os.path.join(self.dir, self.meta["units"][unit]["file"]), "rb").read()))
            self.cache[unit] = b
        return self.cache[unit]

    def predict(self, keys, X):
        """keys: DataFrame[cell, arm, area, target_month]; X: (n, 162) rows in deps/feature_order.csv order."""
        X = np.array(X, dtype=np.float64, copy=True)
        if X.ndim != 2 or X.shape[1] != self.n_features:
            raise ValueError(f"X must be (n, {self.n_features})")
        if len(X) != len(keys):
            raise ValueError(f"{len(keys)} keys but {len(X)} feature rows")
        X[np.isinf(X)] = np.nan                      # native_xgb.clean
        keys = keys.reset_index(drop=True)
        units, reasons = [], []
        for cell, arm, area in zip(keys["cell"], keys["arm"], keys["area"]):
            if arm not in self.meta["arms"] or cell not in self.meta["cells"]:
                raise KeyError(f"{cell}/{arm} is not served by this package")
            region, reason = self.route.get((cell, arm, int(area)), ("", "missing"))
            units.append(f"{cell}|{arm}|{region}" if reason == "region" else f"{cell}|root")
            reasons.append(reason)
        proba = np.full((len(keys), 4), np.nan)
        for unit, idx in pd.Series(units).groupby(units).indices.items():
            pred = self.booster(unit).predict(xgb.DMatrix(X[idx], missing=np.nan, nthread=4))
            if pred.shape != (len(idx), 4):
                raise RuntimeError(f"{unit}: booster returned shape {pred.shape}")
            proba[idx] = pred
        out = keys[["cell", "arm", "area", "target_month"]].copy()
        out["unit"] = [self.meta["units"][u]["sha256"][:16] for u in units]
        out["route"] = reasons
        for k, label in enumerate(("1", "2", "3", "4或5")):
            out[f"p_{label}"] = proba[:, k]
        out["y_pred_code"] = np.argmax(proba, axis=1).astype(np.int64)   # first max wins
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def parse_map(path, recorded_sha):
    """D32 assignment evidence -> {area: partition id (leading zeros kept)}, as stage1_map_transfer.parse_map."""
    if sha256_file(path) != recorded_sha:
        raise PackageError(f"{path}: sha differs from the recorded assignment_evidence sha256")
    ev = pd.read_csv(path, dtype={"FEWSNET_admin_code": str, "spatial_partition_id": str, "prediction_branch_id": str},
                     keep_default_na=False)
    codes = ev["FEWSNET_admin_code"].to_numpy()
    if not all(c.isdigit() for c in codes):
        raise PackageError(f"{path}: non-numeric FEWSNET_admin_code")
    areas = [int(c) for c in codes]
    sp = ev["spatial_partition_id"].to_numpy()
    if len(set(areas)) != len(areas) or (sp == "").any():
        raise PackageError(f"{path}: duplicate areas or empty partition ids")
    if not np.array_equal(sp == S_NONE, ev["search_rows"].astype(np.int64).to_numpy() == 0):
        raise PackageError(f"{path}: s-1 is not equivalent to search_rows == 0")
    return dict(zip(areas, sp.tolist()))


def route(areas, area_map, eligible):
    sid = np.array([area_map.get(int(a), "") for a in areas], dtype=object)
    reason = np.array(["missing" if s == "" else S_NONE if s == S_NONE else "region" if eligible[s]
                       else "insufficient_support" for s in sid], dtype=object)
    return sid, reason


def candidate_dir(run_dir, spec, cell, cand, completion):
    """D34 stage candidates (bound through pair.json/candidate.json), or the run's own (bound to completion outputs)."""
    if (D34 / "stage1_e1pair" / "candidates" / cand).is_dir():
        return D34 / "stage1_e1pair" / "candidates" / cand
    rel = "/".join(p for p in (spec["cells_dir"], cell, "temporal", "candidates", cand) if p)
    if (run_dir / rel).is_dir():
        for f in ("candidate.json", "assignment_evidence.csv"):
            frozen(run_dir, completion, f"{rel}/{f}")
        return run_dir / rel
    raise PackageError(f"{cell}: candidate {cand} not found")


def load_arm(run_dir, spec, cell, pair, arm, completion):
    """(area_map, {region: record}, {region: ubj path}, candidate dir) for one map arm, all hash-bound."""
    meta = pair["maps"][arm]
    cdir = candidate_dir(run_dir, spec, cell, meta["candidate"], completion)
    record = json.load(open(cdir / "candidate.json"))["assignment_evidence"]
    if record.get("sha256") != meta["assignment_evidence_sha256"]:
        raise PackageError(f"{cell}/{arm}: candidate.json and pair.json disagree on the assignment evidence")
    area_map = parse_map(cdir / "assignment_evidence.csv", meta["assignment_evidence_sha256"])
    named = sorted({s for s in area_map.values() if s != S_NONE})
    if named != sorted(meta["named_regions"]):
        raise PackageError(f"{cell}/{arm}: named regions differ from pair.json")
    adir = run_dir / spec["cells_dir"] / cell / f"{arm}_map"
    records, ubjs = {}, {}
    for path in sorted(adir.glob("region_*.json")):
        rel = path.relative_to(run_dir).as_posix()
        rec = json.load(open(frozen(run_dir, completion, rel)))
        if rec["root_booster_sha256"] != pair["root_booster_sha256"]:
            raise PackageError(f"{path}: region record names another root")
        records[rec["region"]] = rec
        if rec["eligible"]:
            ubj = frozen(run_dir, completion, rel[:-len(".json")] + ".ubj")
            digest = sha256_file(ubj)
            if digest != rec["ubj_sha256"] or digest != rec["continuation"]["booster_sha256"]:
                raise PackageError(f"{ubj}: sha differs from its region record")
            ubjs[rec["region"]] = ubj
    if sorted(records) != named:
        raise PackageError(f"{cell}/{arm}: region records differ from the map's named regions")
    return area_map, records, ubjs, cdir


def build_run(out_root, run, snapshots, schema, runtime, per_unit=16):
    import xgboost as xgb
    spec = RUNS[run]
    run_dir = ROOT / run
    identity = json.load(open(run_dir / "identity.json"))
    gate = json.load(open(run_dir / "gate.json"))
    completion = json.load(open(run_dir / "completion.json"))
    if not gate.get("passed") or completion.get("status") != "completed":
        raise PackageError(f"{run}: gate not passed or run not completed")
    names, schema_sha, features_sha = schema
    cells = sorted(p.name for p in (run_dir / spec["cells_dir"]).iterdir() if p.is_dir() and (p / "pair.json").exists())
    if sorted(identity["inputs"]) != cells:
        raise PackageError(f"{run}: pair cells differ from identity inputs")
    b = PackageBuilder(os.path.join(out_root, f"fews-{run}"))
    units, routing, refs, inputs, checks = {}, [], [], [], {}
    for cell in cells:
        h = int(cell.split("_")[0][1:])
        cdir = run_dir / spec["cells_dir"] / cell
        rel = "/".join(p for p in (spec["cells_dir"], cell) if p)
        pair = json.load(open(frozen(run_dir, completion, f"{rel}/pair.json")))
        root_cand = pair["maps"][spec["root_map"]]["candidate"]
        root_ubj = D34 / "stage1_e1pair" / "checkpoints" / root_cand / "xgb_root.ubj"
        if sha256_file(root_ubj) != pair["root_booster_sha256"]:
            raise PackageError(f"{cell}: D34 root checkpoint differs from pair.json root_booster_sha256")
        snap, snap_sha = snapshots.get(h)
        if snap_sha != identity["inputs"][cell]["snapshot"]:
            raise PackageError(f"{cell}: D34 snapshot_h{h} differs from the run identity")
        boosters = {}

        def load(path):
            bst = xgb.Booster()
            bst.load_model(bytearray(Path(path).read_bytes()))
            return bst
        units[f"{cell}|root"] = {"file": f"weights/{cell}/root.ubj", "sha256": pair["root_booster_sha256"],
                                 "source": f"D34 checkpoints/{root_cand}/xgb_root.ubj"}
        b.add_file(str(root_ubj), f"weights/{cell}/root.ubj", pair["root_booster_sha256"], None)
        b.add_file(str(cdir / "pair.json"), f"deps/source/{cell}/pair.json")
        boosters["root"] = load(root_ubj)
        maps = {}
        for arm in spec["arms"]:
            area_map, records, ubjs, cand = load_arm(run_dir, spec, cell, pair, arm, completion)
            eligible = {r: rec["eligible"] and r in ubjs for r, rec in records.items()}
            maps[arm] = (area_map, eligible)
            for f in ("candidate.json", "assignment_evidence.csv"):
                b.add_file(str(cand / f), f"deps/maps/{cell}/{arm}/{f}")
            for region, rec in records.items():
                b.add_file(str(cdir / f"{arm}_map" / f"region_{region}.json"), f"deps/source/{cell}/{arm}_map/region_{region}.json")
            for region, ubj in ubjs.items():
                unit = f"{cell}|{arm}|{region}"
                units[unit] = {"file": f"weights/{cell}/{arm}/region_{region}.ubj", "sha256": records[region]["ubj_sha256"]}
                b.add_file(str(ubj), units[unit]["file"], records[region]["ubj_sha256"], None)
                boosters[(arm, region)] = load(ubj)
            areas = sorted(area_map)
            sid, reason = route(areas, area_map, eligible)
            routing.append(pd.DataFrame({"cell": cell, "arm": arm, "area": areas, "region": sid, "reason": reason}))
        checks[cell] = {}
        for part in spec["parts"]:
            path = frozen(run_dir, completion, f"{rel}/rows_{part}.csv.gz")
            rows = pd.read_csv(path, float_precision="round_trip", keep_default_na=False, na_values={"persistence_code": [""]},
                               dtype={"target_month": str, **{f"region_{a}": str for a in spec["arms"]},
                                      **{f"route_{a}": str for a in spec["arms"]}})
            keys = list(zip(rows["area"].astype(int), rows["target_month"].map(month_index)))
            absent = ~pd.MultiIndex.from_tuples(keys).isin(snap.index)
            if absent.any():
                raise PackageError(f"{cell}/{part}: {int(absent.sum())} keys absent from the snapshot")
            data = snap.loc[keys]
            if not np.array_equal(data["class_code"].to_numpy(int), rows["truth"].to_numpy(int)):
                raise PackageError(f"{cell}/{part}: saved truth differs from the snapshot class_code")
            X = data[snapshots.features].to_numpy(dtype=np.float64, copy=True)
            Xc = X.copy()
            Xc[np.isinf(Xc)] = np.nan
            p_root = boosters["root"].predict(xgb.DMatrix(Xc, missing=np.nan, nthread=4)).astype(np.float64)
            check = {"rows": int(len(rows)), "file_sha256": sha256_file(path),
                     "root_max_abs_err": float(np.abs(rows[[f"p_root_{l}" for l in LABELS]].to_numpy(np.float64) - p_root).max())}
            if not check["root_max_abs_err"] <= 1e-6:   # NaN fails
                raise PackageError(f"{cell}/{part}: root replay differs {check}")
            for arm, col in spec["arms"].items():
                area_map, eligible = maps[arm]
                sid, reason = route(rows["area"].to_numpy(), area_map, eligible)
                if not (np.array_equal(sid, rows[f"region_{arm}"].to_numpy(object))
                        and np.array_equal(reason, rows[f"route_{arm}"].to_numpy(object))):
                    raise PackageError(f"{cell}/{part}/{arm}: re-derived region/route differ from the saved rows")
                proba = p_root.copy()
                unit = np.array([f"{cell}|root"] * len(rows), dtype=object)
                for region in sorted(set(sid[reason == "region"].tolist())):
                    idx = np.flatnonzero((sid == region) & (reason == "region"))
                    proba[idx] = boosters[(arm, region)].predict(xgb.DMatrix(Xc[idx], missing=np.nan, nthread=4))
                    unit[idx] = f"{cell}|{arm}|{region}"
                saved = rows[[f"p_{col}_{l}" for l in LABELS]].to_numpy(np.float64)
                err = np.abs(saved - proba)
                decided = rows[f"y_{col}"].to_numpy(int) == np.argmax(proba, axis=1)
                check[arm] = {"max_abs_err": float(err.max()), "decision_matches": int(decided.sum()),
                              "region_rows": int((reason == "region").sum())}
                if not (np.isfinite(err).all() and (err <= 1e-6).all()) or not decided.all():
                    raise PackageError(f"{cell}/{part}/{arm}: full-part check failed {check[arm]}")
                frame = pd.DataFrame({"cell": cell, "arm": arm, "area": rows["area"].to_numpy(),
                                      "target_month": rows["target_month"].to_numpy(), "part": part,
                                      "unit_key": unit, "route": reason})
                frame["unit"] = [units[u]["sha256"][:16] for u in unit]
                for k, l in enumerate(LABELS):
                    frame[f"p_{l}"] = saved[:, k]
                frame["y_pred_code"] = rows[f"y_{col}"].to_numpy(np.int64)
                srt = np.sort(saved, axis=1)
                ref = select_reference(frame, "unit_key", pd.Series(srt[:, -1] - srt[:, -2], index=frame.index),
                                       ["cell", "arm", "area", "target_month", "part"], per_unit=per_unit, cover_cols=("route",))
                refs.append(ref)
                inputs.append(X[ref.index.to_numpy()])
            checks[cell][part] = check
            print(run, cell, part, {a: (check[a]["region_rows"], check[a]["max_abs_err"]) for a in spec["arms"]}, flush=True)
    for name in ("gate.json", "summary.json"):
        frozen(run_dir, completion, name)
    for name in ("identity.json", "gate.json", "completion.json", "summary.json"):
        b.add_file(str(run_dir / name), f"deps/source/{name}")
    b.add_file(str(D34 / "prepared" / "manifests" / "features.json"), "deps/source/d34_features.json", features_sha)
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": names}).to_csv(index=False).encode())
    b.add_bytes("deps/routing.csv", pd.concat(routing, ignore_index=True).to_csv(index=False).encode())
    ref = pd.concat(refs, ignore_index=True)
    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(np.vstack(inputs), dtype=np.float64), allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    prob = [f"p_{l}" for l in LABELS]
    b.add_bytes("reference/expected.csv", ref[["cell", "arm", "area", "target_month", "part", "unit", "route"] + prob
                                              + ["y_pred_code"]].to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())
    flat = [c for cell in checks.values() for c in cell.values()]
    total = {"rows_per_arm": sum(c["rows"] for c in flat), "arms": list(spec["arms"]),
             "max_abs_err": max(max(c[a]["max_abs_err"] for a in spec["arms"]) for c in flat),
             "root_max_abs_err": max(c["root_max_abs_err"] for c in flat),
             "region_rows": {a: sum(c[a]["region_rows"] for c in flat) for a in spec["arms"]}}
    return b.finalize({
        "family": "fewsnet_map_transfer_diagnostic", "status": "complete", "gaps": [],
        "identity": {"run": run, "stage": identity.get("stage"), "d34_run": "geoxgb-d34-e1-brier-20261002",
                     "producer_rev": identity.get("producer_rev"), "producer_code": identity.get("producer_code"),
                     "script_code": identity.get("script_code")},
        "cells": cells, "arms": spec["arms"], "fitted_units": len(units), "units": units,
        "binding": {"d34_features_schema_sha256": schema_sha, "d34_features_json_sha256": features_sha,
                    "snapshots": {f"h{h}": snapshots.get(h)[1] for h in (4, 8, 12)},
                    "rule": "every consumed run file (rows, pair.json, region records/weights, own candidates, gate, "
                            "summary) == completion.json outputs; assignment evidence == pair.json maps == candidate.json; region ubj == record ubj_sha256 == "
                            "continuation booster_sha256; root checkpoint == pair root_booster_sha256; snapshot == identity"},
        "full_cohort_check": {"total": total, "cells": checks},
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv",
                    "rule": "stage1_map_transfer.route: region (eligible, booster saved) -> region booster; s-1, missing "
                            "(area not in map) or insufficient_support -> the cell root",
                    "routes_in_version": ["region", S_NONE, "missing", "insufficient_support"]},
        "runtime": {"original": identity.get("runtime"), "linux": runtime},
        "code": {"loader": "thin reimplementation (map routing, native_xgb.clean/proba, argmax) accepted by replay",
                 "original_code_sha256": identity.get("producer_code")},
        "loader": {"entry": "loader/entry.py", "keys": ["cell", "arm", "area", "target_month"],
                   "call": "load(package_dir).predict(keys[cell,arm,area,target_month], X)",
                   "inputs": "prepared float64 X: the 162 D34 prepared snapshot features (deps/feature_order.csv) for "
                             "the row's area and target month at the cell horizon; D34 snapshots are preserved with the "
                             "D34 run record. Windows paths in deps/source are provenance only.",
                   "unserved_keys": "KeyError for a cell or arm outside this run; areas outside the map route to the root"},
        "preserved_not_packaged": "global+20 columns (D35 package), search/temporal candidate boosters, equivalence and "
                                  "search evidence, legal-pool membership and descriptive files",
        "reference": {"rows": int(len(ref)), "per_unit_cap": per_unit,
                      "per_unit_cap_scope": "per served booster within each (cell, part, arm) selection; a booster that "
                                            "serves several parts or both arms (e.g. a cell root) can have more rows",
                      "compare_columns": prob + ["y_pred_code"],
                      "routes_covered": sorted(ref["route"].unique()),
                      "selection": "per served booster: route coverage, then half nearest an argmax tie, rest by key hash"},
        "tolerance": {"declared_before_comparison": True, "continuous": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) for p_1..p_4",
                      "decision": "y_pred_code exactly", "routing": "unit and route exactly"},
    })
