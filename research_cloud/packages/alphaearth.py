"""Package builder for the IPCCH AlphaEarth supervised-partition registered versions.

Arms: ``pooled`` = B0 backbone quartet on the 296 compact features; ``pooled_plus_alphaearth`` = B1
backbone on 296 + 128 AlphaEarth descriptors (looked up by admin_code; NaN when the admin is not
routable); ``shared_calibration`` = B2 and ``regional_calibration`` = G, both the per-block
correction of B1 recorded in ``predict/contexts_hXX.json`` (``CorrectionFit.from_record``) on the
three core inputs. A target month belongs to exactly one block; the block fixes the B0/B1 units
(``predict/request_ledger.csv.gz``) and the correction context. Only frozen-map-free runs are
packaged here: a selected regional map would also need the partition router, which is a gap.

Loader code is vendored from the run's MLflow ``source_code/`` artifact (the recorded code identity
is uncommitted 57ca2ef1 + 385a8db8, so that copy, not a checkout, is authoritative).
"""
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file

TARGETS = ("q2", "q3", "q4", "q5")
ARMS = {"pooled": "B0", "pooled_plus_alphaearth": "B1", "shared_calibration": "B2", "regional_calibration": "G"}
LOADER_FILES = ("errors.py", "artifacts.py", "backbone.py", "correction.py", "projection.py")
REQUIRED_UNIT_FILES = ("q2.ubj", "q3.ubj", "q4.ubj", "q5.ubj", "record.json")

ENTRY = '''"""Keyed loader for one historical IPCCH AlphaEarth package (generated; see package.json)."""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ipcch_alphaearth import backbone, correction, projection  # vendored from the run's source_code artifact


class Model:
    def __init__(self, package_dir=ROOT):
        self.root = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.code = self.meta["arm_code"]
        self.n_threads = int(self.meta["loader"]["n_threads"])
        self.core_idx = self.meta["loader"]["core_idx"]
        ae = json.load(open(os.path.join(package_dir, "deps", "ae_names.json")))
        table = pd.read_csv(os.path.join(package_dir, "deps", "descriptors", "descriptor_table.csv.gz")).set_index("admin_code")
        self.descriptors = table[ae]
        routes = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"))
        self.block_of = dict(zip(routes["target_ord"].astype(int), routes["block_id"]))
        self.units = {(r["arm"], r["block_id"]): r["unit"] for r in pd.read_csv(os.path.join(package_dir, "deps", "units.csv")).to_dict("records")}
        contexts = json.load(open(os.path.join(package_dir, "deps", "predict", "contexts_h%02d.json" % self.meta["lead_months"])))
        self.contexts = {cx["block"]["block_id"]: correction.CorrectionFit.from_record(cx["correction"]) for cx in contexts}
        self._boosters = {}

    def quartet(self, digest):
        if digest not in self._boosters:
            base = os.path.join(self.root, "weights", digest)
            self._boosters[digest] = {q: backbone.booster_from_raw(open(os.path.join(base, q + ".ubj"), "rb").read())
                                      for q in backbone.TARGETS}
        return self._boosters[digest]

    def row_descriptors(self, admins):
        """Same contract as the frozen source (descriptors.row_descriptors): every admin must have a row, and
        each row is all finite (routable) or all NaN (not routable)."""
        missing = sorted(set(admins) - set(self.descriptors.index))
        if missing:
            raise KeyError(f"{len(missing)} admins absent from the descriptor table")
        D = self.descriptors.loc[admins].to_numpy(dtype=np.float64)
        finite = np.isfinite(D)
        if not (finite.all(axis=1) | (~finite).all(axis=1)).all():
            raise ValueError("descriptor rows must be all finite or all NaN together")
        return D

    def resolve(self, keys):
        out = []
        for a, t in zip(keys["admin_code"].astype(int), keys["target_ord"].astype(int)):
            block = self.block_of.get(t)
            if block is None:
                raise KeyError(f"no frozen block for target_ord={t} in this package")
            if a not in self.descriptors.index:
                raise KeyError(f"admin_code={a} has no descriptor row (outside the frozen cohort)")
            out.append(block)
        return out

    def predict(self, keys, X296):
        """Keyed prediction. keys: DataFrame[admin_code, target_ord]; X296: (n, 296) float64 rows in
        deps/prepared/feature_order_296.csv.gz order, NaN = missing."""
        X296 = np.asarray(X296, dtype=np.float64)
        if len(X296) != len(keys) or X296.ndim != 2 or X296.shape[1] != 296:
            raise ValueError("keys/X296 shape mismatch")
        blocks = np.array(self.resolve(keys), dtype=object)
        raw = np.zeros((len(X296), 4)); route = np.empty(len(X296), dtype=object); unit = np.empty(len(X296), dtype=object)
        D = self.row_descriptors(keys["admin_code"].astype(int).to_numpy())
        for block in sorted(set(blocks)):
            idx = np.flatnonzero(blocks == block)
            if self.code == "B0":
                unit[idx] = self.units[("B0", block)]
                raw[idx] = backbone.predict_quartet(self.quartet(unit[idx][0]), X296[idx], self.n_threads)
                route[idx] = "B0"
                continue
            unit[idx] = self.units[("B1", block)]
            p1 = backbone.predict_quartet(self.quartet(unit[idx][0]), np.hstack([X296[idx], D[idx]]), self.n_threads)
            if self.code == "B1":
                raw[idx], route[idx] = p1, "B1"
                continue
            fit = self.contexts[block]
            out = fit.predict(p1, X296[idx][:, self.core_idx], np.full(len(idx), None, dtype=object))
            raw[idx] = out["b2"] if self.code == "B2" else out["g"]
            route[idx] = "B2" if self.code == "B2" else out["route"]
        star, phase = projection.project_and_decode(raw)
        frame = pd.DataFrame({"admin_code": keys["admin_code"].to_numpy(), "target_ord": keys["target_ord"].to_numpy(),
                              "unit": unit, "route": route})
        for j, q in enumerate(backbone.TARGETS):
            frame[q + "_raw"], frame[q + "_star"] = raw[:, j], star[:, j]
        frame["phase"] = phase
        return frame


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def resolve_units(ledger, pred, code, lead):
    """(arm, block) -> unit, requiring exactly one distinct ledger identity per serving arm/block AND agreement
    with the saved predictions' own B0_identity/B1_identity on every served row. Returns (units, gaps)."""
    backbone_arm = "B0" if code == "B0" else "B1"
    ledger = ledger[(ledger["horizon"] == int(lead)) & (ledger["arm"] == backbone_arm)]
    gaps, rows = [], []
    for block, part in pred.groupby("block_id", sort=True):
        ids = sorted(ledger.loc[ledger["block_id"] == block, "identity"].unique())
        saved = sorted(part[f"{backbone_arm}_identity"].astype(str).unique())
        if len(ids) != 1:
            gaps.append(f"block {block}: {len(ids)} distinct {backbone_arm} request-ledger identities")
            continue
        if saved != ids:
            gaps.append(f"block {block}: saved prediction {backbone_arm}_identity {saved} != request ledger {ids}")
            continue
        rows.append({"arm": backbone_arm, "block_id": block, "unit": ids[0]})
    return pd.DataFrame(rows, columns=["arm", "block_id", "unit"]), gaps


def build(out_dir, *, run_root, source_code_dir, members_manifest, version, lead, arm, code_identity,
          original_runtime, linux_runtime, per_unit=32):
    if arm not in ARMS:
        raise PackageError(f"unknown arm {arm}")
    code = ARMS[arm]
    h = f"h{int(lead):02d}"
    contract = json.load(open(os.path.join(source_code_dir, "config", "experiment-contract.json")))
    f = contract["features"]
    ae_names = [f"{f['alphaearth_prefix_mean']}{j:02d}" for j in range(int(f["alphaearth_bands"]))] + \
               [f"{f['alphaearth_prefix_sd']}{j:02d}" for j in range(int(f["alphaearth_bands"]))]
    deps = ["prepared/feature_order_296.csv.gz", "descriptors/descriptor_table.csv.gz", f"predict/contexts_{h}.json",
            f"maps/final_map_{h}.json", "predict/request_ledger.csv.gz", "develop/request_ledger.csv.gz",
            f"predict/predictions_{h}.csv.gz"]
    ensure_local([os.path.join(run_root, d) for d in deps] +
                 [os.path.join(run_root, "prepared", f"keys_{h}.csv.gz"), os.path.join(run_root, "prepared", f"X296_{h}.npy")])
    members = {m["path"]: m for m in json.load(open(members_manifest))}
    pred = pd.read_csv(os.path.join(run_root, "predict", f"predictions_{h}.csv.gz"), keep_default_na=False,
                       na_values={c: [""] for c in ("q2", "q3", "q4", "q5", "persistence_q3")})
    keys = pd.read_csv(os.path.join(run_root, "prepared", f"keys_{h}.csv.gz"))
    X = np.load(os.path.join(run_root, "prepared", f"X296_{h}.npy"), mmap_mode="r")
    order = pd.read_csv(os.path.join(run_root, "prepared", "feature_order_296.csv.gz"))
    if X.shape[1] != len(order) or len(keys) != len(X):
        raise PackageError("X296/keys/feature order misaligned")
    if not (keys.loc[pred["row"], "admin_code"].to_numpy() == pred["admin_code"].to_numpy()).all() or \
            not (keys.loc[pred["row"], "target_ord"].to_numpy() == pred["target_ord"].to_numpy()).all():
        raise PackageError("prediction rows do not address keys/X")
    names = list(order.iloc[:, 0]) if "name" not in order else list(order["name"])
    core_idx = [names.index(c) for c in contract["correction"]["core_inputs"]]
    frozen = json.load(open(os.path.join(run_root, "maps", f"final_map_{h}.json")))
    gaps = []
    if frozen["map"] is not None and code == "G":
        gaps.append("a regional map is selected for this lead; the partition router is not packaged")

    ledger = pd.concat([pd.read_csv(os.path.join(run_root, s, "request_ledger.csv.gz")) for s in ("develop", "predict")])
    if pred.groupby("target_ord")["block_id"].nunique().max() != 1:
        raise PackageError("a target month maps to more than one block")
    backbone_arm = "B0" if code == "B0" else "B1"
    units, unit_gaps = resolve_units(ledger, pred, code, lead)
    gaps += unit_gaps
    unit_files = sorted(p for d in units["unit"] for p in members if p.startswith(f"models/{d[:2]}/{d}/"))
    ensure_local([os.path.join(run_root, m) for m in unit_files])
    for d in units["unit"]:
        for name in REQUIRED_UNIT_FILES:
            if f"models/{d[:2]}/{d}/{name}" not in members:
                gaps.append(f"unit {d}: required member {name} absent from the member manifest")

    b = PackageBuilder(out_dir)
    for m in unit_files:
        b.add_file(os.path.join(run_root, m), "weights/" + "/".join(m.split("/")[2:]), members[m]["sha256"], members[m]["bytes"])
    for rel in deps:
        b.add_file(os.path.join(run_root, rel), "deps/" + rel)
    b.add_json("deps/ae_names.json", ae_names)
    b.add_bytes("deps/units.csv", units.to_csv(index=False).encode())
    routing = pred[["target_ord", "block_id"]].drop_duplicates().sort_values("target_ord")
    b.add_bytes("deps/routing.csv", routing.to_csv(index=False).encode())

    served = pred[pred["block_id"].isin(set(units["block_id"]))]
    ref_frame = served.assign(unit=served[f"{backbone_arm}_identity"].astype(str),   # expected unit from the saved predictions
                              route=served["G_route"] if code == "G" else code,
                              routable_s=served["routable"].astype(str))
    star_cols = [f"{code}_{q}_star" for q in TARGETS]
    boundary = (ref_frame[star_cols] - 0.20).abs().min(axis=1)
    cover = ("routable_s",) if code != "B0" else ()
    ref = select_reference(ref_frame, "unit", boundary, ["admin_code", "target_ord"], per_unit=per_unit, cover_cols=cover)
    inputs = np.ascontiguousarray(X[ref["row"].to_numpy()], dtype=np.float64)
    buf = io.BytesIO()
    np.save(buf, inputs, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[["admin_code", "target_ord", "block_id", "route", "unit"]].copy()
    for q in TARGETS:
        expected[f"{q}_raw"] = ref[f"{code}_{q}_raw"].to_numpy()
        expected[f"{q}_star"] = ref[f"{code}_{q}_star"].to_numpy()
    expected["phase"] = ref[f"{code}_phase"].to_numpy()
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())

    src_pkg = os.path.join(source_code_dir, "ipcch_alphaearth")
    b.add_bytes("loader/ipcch_alphaearth/__init__.py", b"")
    for name in LOADER_FILES:
        b.add_file(os.path.join(src_pkg, name), f"loader/ipcch_alphaearth/{name}")
    b.add_bytes("loader/entry.py", ENTRY.encode())

    raw_cols = [f"{code}_{q}_raw" for q in TARGETS]
    return b.finalize({
        "family": "alphaearth_supervised_partition", "identity": version, "lead_months": int(lead), "arm": arm,
        "arm_code": code, "status": "complete" if not gaps else "retained_weights_missing_dependencies", "gaps": gaps,
        "fitted_units": int(len(units)),
        "routing": {"table": "deps/routing.csv", "units": "deps/units.csv", "frozen_map": f"deps/maps/final_map_{h}.json",
                    "feature_order": "deps/prepared/feature_order_296.csv.gz", "selected_map": frozen["selected"],
                    "served_keys": int(len(pred)), "routes_in_version": sorted(ref_frame["route"].astype(str).unique())},
        "source": {"run_root": run_root, "members_manifest": members_manifest,
                   "members_manifest_sha256": sha256_file(members_manifest),
                   "predictions_sha256": sha256_file(os.path.join(run_root, "predict", f"predictions_{h}.csv.gz"))},
        "code": {"identity": code_identity, "package": "ipcch_alphaearth", "vendored_from": src_pkg,
                 "vendored_files": {n: sha256_file(os.path.join(src_pkg, n)) for n in LOADER_FILES}},
        "runtime": {"original": original_runtime, "linux": linux_runtime},
        "loader": {"entry": "loader/entry.py", "call": "load(package_dir).predict(keys[admin_code,target_ord], X296)",
                   "inputs": "float64 rows (296 features) in deps/prepared/feature_order_296.csv.gz order; NaN = missing; "
                             "AlphaEarth descriptors are attached inside the loader by admin_code",
                   "n_threads": int(contract["backbone"]["fixed"]["n_jobs"]), "core_idx": core_idx,
                   "unserved_keys": "KeyError (target month outside the frozen blocks, or admin without a descriptor row)"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit,
                      "selection": "per block unit (cap): >=1 row per routable state, half the rest nearest a 0.20 boundary, rest by key hash",
                      "rows_with_missing_features": int(np.isnan(inputs).any(axis=1).sum()),
                      "routes_covered": sorted(expected["route"].astype(str).unique()),
                      "routable_states_covered": sorted(ref["routable_s"].unique()),
                      "routable_states_in_saved_predictions": sorted(pred["routable"].astype(str).unique()),
                      "raw_range_in_sample": [float(ref[raw_cols].min().min()), float(ref[raw_cols].max().max())]},
        "tolerance": {"declared_before_comparison": True,
                      "projected_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref)",
                      "raw_shares": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref) (unbounded regression/correction outputs; range recorded)",
                      "phase": "new phase must decode from new projected shares; boundary drift only within that reference's tolerance",
                      "routing": "resolved unit and route must equal the frozen reference exactly",
                      "note": "original runtime is Linux with the same pinned numerical versions; differences are expected to be exactly zero"},
    })
