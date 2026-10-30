"""IPCCH inference from an immutable feature batch (task 10-29; R18, R19, R32, R36, R51, R61).

``load_batch`` validates a referenced batch before any scoring:

* the manifest at its exact pinned generation and sha256; schema; batch id; mode and real/dummy designation equal the
  request (a real request rejects dummy batches; a smoke request uses smoke batches); M and O = M - 2 equal the request;
* the selected model combination EXACTLY matches the batch's recorded combination (combination id, package manifest,
  feature order and, when both carry one, the bound handoff manifest) and per-scope training cutoffs - a match of column
  names alone is not enough (R19);
* namespace admission BEFORE any read: the manifest and every horizon file must be the canonical paths of this batch
  id under the request mode's root (R48); the roster must be the store's bound roster (real: the accepted 6,226);
  each horizon's H, public lead, O and T = O + H must follow from M (R19/R23);
* each horizon file at its recorded generation and sha256; header duplicates and ragged rows rejected (never resolved
  positionally); area_id must equal admin_code;
  every model-required column present (no synthesized all-NaN column); extras ignored; rows exactly the roster with
  unique area keys (R32); required numeric values parse strictly - blank/NaN are missing, unparseable text or
  +/-infinity fail with area and column (R19); columns reordered by the model's saved feature names.

``score_batch`` first re-verifies the package itself (every listed member re-hashed, manifest sha256 and combination
id equal to the binding), then scores each horizon through the existing runtime path unchanged (``load_scope_package`` ->
``apply_feature_contract`` -> ``score_scope``: unclipped raw scores, package thresholds, cummax on the binary
predictions, overall phase decoding; R61). Nonfinite raw model outputs fail the run with area, horizon and field
(R18); raw scores outside [0, 1] are counted, not clipped. Prediction tables carry ``mode`` and ``batch_id`` (R36).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from cloud.common.object_store import ObjectStore
from cloud.ipcch import batch as bt
from cloud.ipcch import binding as bd
from cloud.ipcch import retained
from cloud.ipcch.stores import StoreError, StoreRoot

TARGETS = ("phase2_worse", "phase3_worse", "phase4_worse", "phase5_worse")


class BatchValidationError(RuntimeError):
    """The referenced feature batch cannot be used for this request; nothing was scored."""


class InferenceOutputError(RuntimeError):
    """A model produced a nonfinite raw output (R18); the IPCCH run fails and current is preserved."""


def read_pinned(store: ObjectStore, ref: Mapping[str, str]) -> str:
    before = store.get_metadata(ref["uri"])
    if before is None or str(before.generation) != str(ref["generation"]):
        raise BatchValidationError(f"{ref['uri']}#{ref['generation']} is not the current immutable object")
    text = store.read_text(ref["uri"])
    after = store.get_metadata(ref["uri"])
    if after is None or after.generation != before.generation:
        raise BatchValidationError(f"{ref['uri']} changed while it was read")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != ref["sha256"]:
        raise BatchValidationError(f"{ref['uri']}#{ref['generation']} sha256 differs from its reference")
    return text


def _strict_numeric(text: pd.Series, column: str, areas: pd.Series) -> np.ndarray:
    out = np.empty(len(text), dtype="float64")
    for i, v in enumerate(text):
        s = v.strip()
        if s == "" or s.lower() == "nan":
            out[i] = math.nan
            continue
        try:
            x = float(s)
        except ValueError:
            raise BatchValidationError(f"unparseable value {v!r} at area {areas.iloc[i]} column {column} (R19)") from None
        if math.isinf(x):
            raise BatchValidationError(f"infinite value {v!r} at area {areas.iloc[i]} column {column} (R19)")
        out[i] = x
    return out


def parse_horizon(text: str, h: int, order: tuple[str, ...], roster: list[str]) -> pd.DataFrame:
    header = next(csv.reader(io.StringIO(text.split("\n", 1)[0])), [])
    dup = sorted({c for c in header if header.count(c) > 1})
    if dup:
        raise BatchValidationError(f"H{h}: duplicate column names {dup[:5]} (R19)")
    try:
        raw = retained.strict_csv(text, f"H{h}")         # ragged rows are never re-aligned
    except StoreError as exc:
        raise BatchValidationError(str(exc)) from exc
    required = [*bt.IDENTITY, *order]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise BatchValidationError(f"H{h}: missing model-required columns {missing[:5]} ({len(missing)}) (R19)")
    areas = raw["admin_code"]
    if not raw["area_id"].equals(areas):
        raise BatchValidationError(f"H{h}: area_id must equal admin_code on every row (R32)")
    if areas.duplicated().any():
        raise BatchValidationError(f"H{h}: duplicate area keys {sorted(set(areas[areas.duplicated()]))[:5]} (R32)")
    if set(areas) != set(roster):
        lacking, unknown = sorted(set(roster) - set(areas)), sorted(set(areas) - set(roster))
        raise BatchValidationError(f"H{h}: rows are not the roster; missing {lacking[:5]} ({len(lacking)}), "
                                   f"unknown {unknown[:5]} ({len(unknown)}) (R32)")
    features = pd.DataFrame({c: _strict_numeric(raw[c], c, areas) for c in order}, index=raw.index)
    identity = raw[list(bt.IDENTITY)].copy()
    identity["population_estimate"] = _strict_numeric(identity["population_estimate"], "population_estimate", areas)
    return pd.concat([identity, features], axis=1)                    # model order; extras dropped


def load_batch(store: ObjectStore, ref: Mapping[str, str], *, batch_root: str, batch_id: str, mode: str,
               execution_month: str, binding: bd.Binding, roster: Iterable[Any]) -> tuple[dict[str, Any], dict[int, pd.DataFrame]]:
    if binding.mode != mode:
        raise BatchValidationError(f"{mode} request with a {binding.mode} combination binding")
    try:                                                   # namespace admission BEFORE any read (R48)
        root = StoreRoot(mode, batch_root)
    except StoreError as exc:
        raise BatchValidationError(f"batch root: {exc}") from exc
    paths = bt.batch_paths(batch_root, batch_id)
    if ref.get("uri") != paths["manifest"]:
        raise BatchValidationError(f"batch manifest {ref.get('uri')} is not {paths['manifest']} in the {mode} namespace; "
                                   "refused before reading (R48)")
    try:
        roster = bt.bound_roster(store, root, binding, roster)
    except StoreError as exc:
        raise BatchValidationError(str(exc)) from exc
    try:
        manifest = json.loads(read_pinned(store, ref))
    except ValueError as exc:
        raise BatchValidationError(f"batch manifest is not JSON: {exc}") from exc
    if manifest.get("schema") != bt.SCHEMA or manifest.get("batch_id") != batch_id:
        raise BatchValidationError(f"manifest schema/batch id {manifest.get('schema')}/{manifest.get('batch_id')} != "
                                   f"{bt.SCHEMA}/{batch_id}")
    designation = "dummy" if mode == "smoke" else "real"
    if manifest.get("mode") != mode or manifest.get("designation") != designation:
        raise BatchValidationError(f"a {mode} request cannot use a {manifest.get('mode')}/{manifest.get('designation')} "
                                   f"batch (R36)")
    if manifest.get("execution_month") != execution_month or manifest.get("feature_origin") != bt.add_months(execution_month, -2):
        raise BatchValidationError(f"batch M/O {manifest.get('execution_month')}/{manifest.get('feature_origin')} do not "
                                   f"match the request M {execution_month} (R19)")
    rec, want = manifest.get("combination", {}), binding.reference()
    keys = ["combination_id", "package_manifest_sha256", "feature_order_sha256"]
    if rec.get("handoff_manifest_sha256") and want.get("handoff_manifest_sha256"):
        keys.append("handoff_manifest_sha256")
    diff = {k: (rec.get(k), want.get(k)) for k in keys if rec.get(k) != want.get(k)}
    if diff or rec.get("scopes") != dict(binding.scopes):
        raise BatchValidationError(f"selected model combination differs from the batch's {diff or 'scope cutoffs'}; "
                                   "generate a new batch for this combination (R19)")
    if manifest.get("roster", {}).get("sha256") != bt.roster_sha256(roster):
        raise BatchValidationError("batch roster differs from this store's roster (R32)")
    origin = bt.add_months(execution_month, -2)
    if sorted(manifest.get("horizons", {})) != sorted(str(h) for h in bt.HORIZONS):
        raise BatchValidationError(f"batch horizons {sorted(manifest.get('horizons', {}))} are not exactly H2/H8/H14 (R18)")
    frames = {}
    for h in bt.HORIZONS:
        entry = manifest["horizons"][str(h)]
        expect = {"model_horizon_months": h, "public_lead_months": bt.HORIZONS[h], "feature_origin": origin,
                  "target_month": bt.add_months(origin, h)}
        wrong = {k: (entry.get(k), v) for k, v in expect.items() if entry.get(k) != v}
        if wrong:
            raise BatchValidationError(f"H{h} horizon metadata differs from M {execution_month}: {wrong} (R19/R23)")
        if entry.get("file") != paths[str(h)]:
            raise BatchValidationError(f"H{h} file {entry.get('file')} is not {paths[str(h)]}; refused before reading (R48)")
        text = read_pinned(store, {"uri": entry["file"], "generation": entry["generation"], "sha256": entry["sha256"]})
        frames[h] = parse_horizon(text, h, tuple(binding.feature_order), roster)
    return manifest, frames


def read_feature_provenance(store: ObjectStore, manifest: Mapping[str, Any], *, batch_root: str) -> bytes:
    """The batch's feature provenance sidecar at its canonical path, pinned generation and sha256."""
    entry = manifest.get("feature_provenance")
    if entry is None:
        raise BatchValidationError("batch has no feature provenance sidecar")
    if entry["file"] != bt.batch_paths(batch_root, manifest["batch_id"])["provenance"]:
        raise BatchValidationError(f"feature provenance {entry['file']} is not this batch's canonical path (R48)")
    return read_pinned(store, {"uri": entry["file"], "generation": entry["generation"], "sha256": entry["sha256"]}).encode()


def score_batch(manifest: Mapping[str, Any], frames: Mapping[int, pd.DataFrame], package_root: str,
                binding: bd.Binding) -> dict[int, dict[str, Any]]:
    from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract
    from model_pipeline.ipcch_launch_runtime.inference import score_scope
    from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package

    try:                                                   # the package itself, every member re-hashed (R51)
        pkg_ident = bd.package_identity(package_root)
    except bd.BindingError as exc:
        raise BatchValidationError(f"package: {exc}") from exc
    if (pkg_ident["package_manifest_sha256"], pkg_ident["combination_id"]) != (binding.package_manifest_sha256,
                                                                                binding.combination_id):
        raise BatchValidationError("package_root is not the bound combination package (manifest sha256/combination id)")
    origin, results = manifest["feature_origin"], {}
    for h, scope in ((2, 0), (8, 6), (14, 12)):
        pkg = load_scope_package(Path(package_root), scope)
        meta = pkg["metadata"]
        if tuple(pkg["feature_columns"]) != tuple(binding.feature_order):
            raise BatchValidationError(f"H{h}: package feature order differs from the binding")
        if meta.get("training_cutoff") != binding.scopes[str(scope)]["training_cutoff"]:
            raise BatchValidationError(f"H{h}: package training cutoff differs from the bound scope")
        frame = frames[h].reset_index(drop=True)
        monthly = frame.copy()
        matrix, report = apply_feature_contract(monthly, pkg["contract"], pkg["feature_columns"],
                                                package_root=Path(package_root), metadata=meta)
        if report.get("status") != "passed":
            raise BatchValidationError(f"H{h}: feature contract {report.get('status')}")
        for target in TARGETS:                      # locate nonfinite raw outputs before the shared scorer (R18)
            raw = np.asarray(pkg["models"][target].predict(matrix), dtype="float64")
            bad = np.flatnonzero(~np.isfinite(raw))
            if bad.size:
                raise InferenceOutputError(f"H{h} {target}_score nonfinite at areas "
                                           f"{frame['admin_code'].iloc[bad[:5]].tolist()} ({bad.size} rows) (R18)")
        target_month = manifest["horizons"][str(h)]["target_month"]
        out, summary = score_scope(monthly_rows=monthly, feature_matrix=matrix, models=pkg["models"],
                                   thresholds=meta["thresholds"], scope_months=scope, feature_month=origin,
                                   target_month=target_month, model_package_id=binding.combination_id,
                                   source_input=manifest["batch_id"], monotonicity_policy=meta["monotonicity_policy"])
        out["mode"], out["batch_id"] = manifest["mode"], manifest["batch_id"]
        out["model_horizon_months"], out["public_lead_months"] = h, bt.HORIZONS[h]
        scores = out[[f"{t}_score" for t in TARGETS]].to_numpy()
        summary["raw_scores_outside_0_1"] = int(((scores < 0) | (scores > 1)).sum())
        summary["contract_report"] = report.get("status")
        results[h] = {"predictions": out, "summary": summary}
    return results
