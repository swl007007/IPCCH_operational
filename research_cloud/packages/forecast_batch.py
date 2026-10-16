"""Package builder for IPCCH forecasting registered versions in batch and launch formats.

Batch versions (compact climate original/2026-extension, global and Somalia-local; origin-safe climate
IDP; origin-safe weather ORACLE): one fit per test year (``batches/<year>``) with four cumulative-share
boosters ``model_phase{2..5}_worse.ubj``. A key (area_id, year, month) is served by the batch of its own
year. Launch versions: one fit (``launch``) scoring ``inference_features.csv.gz``.

Inference matches the producing code (``scripts/modeling/run_deep_feature_weight_decay_forecasting.py``
``run_origin_batch``: ``XGBRegressor.predict(data.loc[rows, features])``, raw unclipped scores;
``src/ipcch/origin_safe.py:328-336`` ``classify_cumulative``: highest phase whose unrounded score is
>= the threshold, else 1). No projection is applied, so projected columns equal raw ones.

Reference input rows come from the run's own pinned dataset (manifest chain, sha256 verified) for batch
versions and from the saved ``inference_features.csv.gz`` for launch versions.
"""
import hashlib
import io
import json
import os

import numpy as np
import pandas as pd

from research_cloud.packages.common import PackageBuilder, PackageError, ensure_local, select_reference, sha256_file

TARGETS = ("phase2_worse", "phase3_worse", "phase4_worse", "phase5_worse")
PRED = ("phase2_pred", "phase3_pred", "phase4_pred", "phase5_pred")
KEYS = ["area_id", "year", "month"]

ENTRY = '''"""Keyed loader for one historical IPCCH forecasting package (generated; see package.json)."""
import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ("phase2_worse", "phase3_worse", "phase4_worse", "phase5_worse")


def classify_cumulative(scores, threshold):
    """IPCCH src/ipcch/origin_safe.py:328-336: highest phase whose unrounded score >= threshold, else 1."""
    out = np.ones(len(scores), dtype=int)
    assigned = np.zeros(len(scores), dtype=bool)
    for phase in (5, 4, 3, 2):
        hit = ~assigned & (scores[:, phase - 2] >= threshold)
        out[hit] = phase
        assigned |= hit
    return out


class Model:
    def __init__(self, package_dir=ROOT):
        self.root = package_dir
        self.meta = json.load(open(os.path.join(package_dir, "package.json")))
        self.features = json.load(open(os.path.join(package_dir, "deps", "features.json")))
        self.threshold = float(self.meta["loader"]["phase_threshold"])
        routing = pd.read_csv(os.path.join(package_dir, "deps", "routing.csv"), dtype={"unit": str})
        self.served = {tuple(int(x) for x in k): u for *k, u in routing.itertuples(index=False)}
        self._models = {}

    def unit(self, name):
        if name not in self._models:
            models = {}
            for target in TARGETS:
                m = xgb.XGBRegressor()
                m.load_model(os.path.join(self.root, "weights", name, "model_%s.ubj" % target))
                if list(m.get_booster().feature_names) != self.features:
                    raise ValueError("booster feature order differs from the package feature list")
                models[target] = m
            self._models[name] = models
        return self._models[name]

    def resolve(self, keys):
        out = []
        for k in keys[["area_id", "year", "month"]].astype(int).itertuples(index=False, name=None):
            if k not in self.served:
                raise KeyError(f"key {k} is not served by this package's frozen batches")
            out.append(self.served[k])
        return out

    def predict(self, keys, X):
        """keys: DataFrame[area_id, year, month]; X: (n, n_features) float64 in deps/features.json order, NaN = missing."""
        X = np.asarray(X, dtype=np.float64)
        if len(X) != len(keys) or X.ndim != 2 or X.shape[1] != len(self.features):
            raise ValueError("keys/X shape mismatch")
        units = np.array(self.resolve(keys), dtype=object)
        scores = np.zeros((len(X), 4))
        for name in sorted(set(units)):
            idx = np.flatnonzero(units == name)
            frame = pd.DataFrame(X[idx], columns=self.features)
            for j, (target, model) in enumerate(self.unit(name).items()):
                scores[idx, j] = model.predict(frame).astype(float)
        out = keys[["area_id", "year", "month"]].reset_index(drop=True).copy()
        out["unit"], out["route"] = units, ["batch_" + u if u != "launch" else "launch" for u in units]
        for j, q in enumerate(("q2", "q3", "q4", "q5")):
            out[q + "_raw"] = scores[:, j]
            out[q + "_star"] = scores[:, j]          # no projection in this family
        out["phase"] = classify_cumulative(scores, self.threshold)
        return out


def load(package_dir=ROOT):
    return Model(package_dir)
'''


def list_sha256(values):
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def recorded_payload(run_metadata):
    """The run's own recorded fingerprint payload; extension runs record the parent run's under ``parent_fingerprint_payload``."""
    payload = run_metadata.get("fingerprint_payload") or {}
    return payload.get("parent_fingerprint_payload", payload)


def resolve_manifest(run_metadata):
    """Model-ready manifest that pins this run's input dataset. Extension runs re-ran the original suite's loader with
    the parent manifest (run_compact_eval_2026_extension.py run_args: origin_manifest=parent manifest)."""
    if "manifest" in run_metadata:
        return run_metadata["manifest"], "run_metadata.manifest"
    if "extension_manifest" in run_metadata:
        ensure_local([run_metadata["extension_manifest"]["path"]])
        if sha256_file(run_metadata["extension_manifest"]["path"]) != run_metadata["extension_manifest"]["sha256"]:
            raise PackageError("extension manifest sha256 differs from the run metadata")
        ext = json.load(open(run_metadata["extension_manifest"]["path"]))
        return ext["parent"]["manifest"]["path"], "extension_manifest.parent.manifest"
    return None, None


def resolve_dataset(run_metadata, horizon, arm):
    """Pinned dataset: manifest -> horizon/arm (else horizon) dataset; the manifest and dataset sha256 must equal
    the run's own recorded fingerprint payload where recorded. Returns (path, sha256, chain)."""
    manifest_path, via = resolve_manifest(run_metadata)
    if manifest_path is None:
        raise PackageError("run metadata names no model-ready manifest")
    ensure_local([manifest_path])
    manifest_sha = sha256_file(manifest_path)
    entry = json.load(open(manifest_path))["horizons"][str(horizon)]
    ds = entry.get("arms", {}).get(arm, {}).get("dataset") or entry.get("dataset")
    if not ds:
        raise PackageError(f"manifest {manifest_path} has no dataset for horizon {horizon} arm {arm}")
    payload = recorded_payload(run_metadata)
    chain = {"manifest": manifest_path, "manifest_via": via, "manifest_sha256": manifest_sha, "dataset": ds["path"],
             "dataset_sha256_manifest": ds["sha256"], "recorded_manifest_sha256": payload.get("manifest_sha256"),
             "recorded_dataset_sha256": payload.get("dataset_sha256")}
    if payload.get("manifest_sha256") and payload["manifest_sha256"] != manifest_sha:
        raise PackageError("manifest sha256 differs from the run's recorded fingerprint")
    if payload.get("dataset_sha256") and payload["dataset_sha256"] != ds["sha256"]:
        raise PackageError("manifest dataset sha256 differs from the run's recorded fingerprint")
    return ds["path"], ds["sha256"], chain


def information_status(run_metadata, features):
    """Oracle status from the manifest arm contract (declared ``appended`` oracle inputs actually served), never from
    the source path. Without a manifest arm contract the status is recorded as undeclared."""
    manifest_path, _ = resolve_manifest(run_metadata) if ("manifest" in run_metadata or "extension_manifest" in run_metadata) else (None, None)
    if manifest_path is None:
        return {"status": "undeclared", "evidence": "no model-ready manifest arm contract for this run"}
    arm = json.load(open(manifest_path))["horizons"][str(run_metadata["horizon"])].get("arms", {}).get(run_metadata["arm"], {})
    appended = arm.get("appended") or []
    if isinstance(appended, str):
        appended = json.loads(appended.replace("'", '"'))
    served = [f for f in appended if f in features and f.startswith("oracle_")]
    if served:
        return {"status": "oracle_realized_future_information", "evidence": f"manifest arm {run_metadata['arm']} appends {len(served)} oracle inputs, all served",
                "oracle_features": served}
    return {"status": "origin_safe_ordinary", "evidence": f"manifest arm {run_metadata['arm']} serves no appended oracle input"}


def booster_version(path):
    import xgboost as xgb
    booster = xgb.Booster()
    booster.load_model(path)
    return ".".join(str(x) for x in json.loads(bytes(booster.save_raw("json")))["version"])


def build(out_dir, *, ipcch_root, plan_version, version_key, source_key, version, runtime, per_unit=32):
    members = plan_version["members"]
    meta_paths = [m["path"] for m in members if m["role"] == "run_metadata_feature_order"]
    if len(meta_paths) != 1:
        raise PackageError(f"{version_key}: expected one run_metadata member, got {len(meta_paths)}")
    rm_path = os.path.join(ipcch_root, meta_paths[0])
    ensure_local([os.path.join(ipcch_root, m["path"]) for m in members])
    run_meta = json.load(open(rm_path))
    features = list(run_meta["features"])
    launch = any(m["role"] == "launch_predictions" for m in members)
    gaps = []

    units = {}
    for m in members:
        if m["role"] == "booster":
            unit = "launch" if launch else str(m["job"])
            units.setdefault(unit, {})[os.path.basename(m["path"])] = m
    for unit, files in units.items():
        missing = sorted({f"model_{t}.ubj" for t in TARGETS} - set(files))
        if missing:
            gaps.append(f"unit {unit}: missing boosters {missing}")
    if launch:
        pred_member = [m for m in members if m["role"] == "launch_predictions"]
        pred = pd.read_csv(os.path.join(ipcch_root, pred_member[0]["path"]))
        pred["unit"] = "launch"
        feats_member = [m for m in members if m["role"] == "inference_features"][0]
        source_rows = pd.read_csv(os.path.join(ipcch_root, feats_member["path"]), float_precision="round_trip", low_memory=False)
        dataset_info = {"input_chain": {"inference_features": feats_member["path"], "sha256": feats_member["sha256"]}}
    else:
        frames = []
        for m in members:
            if m["role"] == "batch_predictions":
                part = pd.read_csv(os.path.join(ipcch_root, m["path"]), float_precision="round_trip")
                part["unit"] = str(m["job"])
                frames.append(part)
            if m["role"] == "batch_record":
                rec = json.load(open(os.path.join(ipcch_root, m["path"])))
                if rec.get("feature_sha256") != list_sha256(features):
                    gaps.append(f"batch {m['job']}: batch_record feature_sha256 differs from the served feature list")
        pred = pd.concat(frames, ignore_index=True)
        ds_path, ds_sha, chain = resolve_dataset(run_meta, int(run_meta["horizon"]), run_meta["arm"])
        ensure_local([ds_path])
        if sha256_file(ds_path) != ds_sha:
            raise PackageError(f"dataset {ds_path} sha256 differs from its manifest")
        source_rows = pd.read_csv(ds_path, float_precision="round_trip", low_memory=False)
        dataset_info = {"input_chain": chain}
    if pred.duplicated(KEYS).any():
        raise PackageError("saved predictions repeat a key")
    if not launch and not (pred["year"].astype(str) == pred["unit"]).all():
        raise PackageError("a batch prediction row is not in its own test-year batch")
    missing_units = sorted(set(pred["unit"]) - set(units))
    gaps += [f"saved predictions reference unit {u} with no boosters" for u in missing_units]

    embedded = {unit: sorted({booster_version(os.path.join(ipcch_root, m["path"])) for m in files.values()})
                for unit, files in units.items()}
    b = PackageBuilder(out_dir)
    for unit, files in sorted(units.items()):
        for name, m in sorted(files.items()):
            b.add_file(os.path.join(ipcch_root, m["path"]), f"weights/{unit}/{name}", m["sha256"], m["bytes"])
    for m in members:
        if m["role"] != "booster":
            b.add_file(os.path.join(ipcch_root, m["path"]), "deps/" + m["path"], m["sha256"], m["bytes"])
    b.add_json("deps/features.json", features)
    routing = pred[KEYS + ["unit"]].sort_values(KEYS)
    b.add_bytes("deps/routing.csv", routing.to_csv(index=False).encode())

    pred["route"] = ["launch" if u == "launch" else f"batch_{u}" for u in pred["unit"]]
    boundary = (pred[list(PRED)] - float(run_meta.get("phase_threshold", 0.2))).abs().min(axis=1)
    ref = select_reference(pred, "unit", boundary, KEYS, per_unit=per_unit)
    lookup = source_rows.set_index(KEYS)
    if lookup.index.duplicated().any():
        raise PackageError("input rows repeat a key")
    absent = [k for k in zip(ref["area_id"], ref["year"], ref["month"]) if k not in lookup.index]
    if absent:
        raise PackageError(f"{len(absent)} reference keys absent from the pinned input rows, e.g. {absent[:2]}")
    rows = lookup.loc[list(zip(ref["area_id"], ref["year"], ref["month"])), features]
    inputs = np.ascontiguousarray(rows.to_numpy(dtype=np.float64))
    buf = io.BytesIO()
    np.save(buf, inputs, allow_pickle=False)
    b.add_bytes("reference/inputs.npy", buf.getvalue())
    expected = ref[KEYS + ["route", "unit"]].copy()
    for q, p in zip(("q2", "q3", "q4", "q5"), PRED):
        expected[f"{q}_raw"] = ref[p].to_numpy()
        expected[f"{q}_star"] = ref[p].to_numpy()
    expected["phase"] = ref["overall_phase_pred"].to_numpy()
    b.add_bytes("reference/expected.csv", expected.to_csv(index=False, float_format="%.17g").encode())
    b.add_bytes("loader/entry.py", ENTRY.encode())
    b.add_bytes("deps/feature_order.csv", pd.DataFrame({"name": features}).to_csv(index=False).encode())

    return b.finalize({
        "family": version.get("family"), "identity": version, "source_key": source_key, "version_key": version_key,
        "lead_months": int(run_meta.get("horizon", 0)), "arm": run_meta.get("arm") or run_meta.get("run_id"),
        "information": information_status(run_meta, features),
        "source_vintage": {"source_key": source_key, "family": version.get("family")},
        "status": "complete" if not gaps else "retained_weights_missing_dependencies", "gaps": gaps,
        "fitted_units": len(units),
        "routing": {"table": "deps/routing.csv", "feature_order": "deps/feature_order.csv", "served_keys": int(len(pred)),
                    "routes_in_version": sorted(pred["route"].unique())},
        "source": {"ipcch_root": ipcch_root, "run_metadata": meta_paths[0], **dataset_info},
        "code": {"loader": "new thin loader (XGBRegressor.load_model + predict on the feature-ordered frame; highest-crossing "
                           "phase rule); it is NOT the producing code and is accepted only through replay against the saved predictions",
                 "rule_sources_read": ["IPCCH scripts/modeling/run_deep_feature_weight_decay_forecasting.py run_origin_batch",
                                       "IPCCH src/ipcch/origin_safe.py:328-336 classify_cumulative"],
                 "producing_code_recorded": {k: run_meta.get(k) for k in ("git_head", "git_status_porcelain") if k in run_meta}
                                            | {"code_sha256": recorded_payload(run_meta).get("code_sha256", "not recorded")}},
        "runtime": {"original": {"xgboost_recorded": recorded_payload(run_meta).get("xgboost", "not recorded"),
                                 "booster_embedded_versions_by_unit": embedded},
                    "linux": runtime},
        "loader": {"entry": "loader/entry.py", "keys": KEYS, "call": "load(package_dir).predict(keys[area_id,year,month], X)",
                   "inputs": f"float64 rows ({len(features)} features) in deps/features.json order; NaN = missing",
                   "phase_threshold": float(run_meta.get("phase_threshold", 0.2)),
                   "unserved_keys": "KeyError (key not in the frozen batches)"},
        "reference": {"rows": int(len(expected)), "per_unit_cap": per_unit,
                      "selection": "per batch unit (cap): half nearest the 0.20 threshold, rest by key hash",
                      "rows_with_missing_features": int(np.isnan(inputs).any(axis=1).sum()),
                      "routes_covered": sorted(expected["route"].unique()),
                      "raw_range_in_sample": [float(ref[list(PRED)].min().min()), float(ref[list(PRED)].max().max())]},
        "tolerance": {"declared_before_comparison": True,
                      "raw_scores": "abs(new-ref) <= 1e-3 + 1e-3*abs(ref); scores are unclipped regression outputs (range recorded)",
                      "projected": "not applicable: no projection; *_star columns repeat the raw scores",
                      "phase": "new phase must decode from new scores (highest phase >= 0.20); drift only within that reference's tolerance",
                      "routing": "resolved batch unit must equal the frozen reference exactly"},
    })
