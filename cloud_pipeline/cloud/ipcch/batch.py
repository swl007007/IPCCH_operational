"""Immutable IPCCH feature batches (task 10-29; R13, R19, R32, R36, R40, R43, R52, R53, R59, R62, R65).

Every generation writes a NEW batch with a unique id bound to the run id (``ipcch-<M>-<run_id>-<uuid12>``); batches are
never overwritten and never cleaned up. Layout under the mode's batch root (isolated per mode, R48)::

    <root>/feature_batches/<batch_id>/h02.csv, h08.csv, h14.csv     create-only
    <root>/feature_batches/<batch_id>/summary.json                   create-only (generation-only summary)
    <root>/feature_batches/<batch_id>/manifest.json                  create-only, written LAST (= the batch is complete)

Each horizon file is one row per roster area: identity columns (admin_code, area_id, population output fields) then
exactly the bound package's 527-name feature order (values as written by the assembly; NaN as empty). Writing refuses:
a mode differing from the binding's, horizons other than H2/H8/H14, a feature order differing from the package, rows
that are not exactly the roster (real: the full bound roster; smoke: its declared subset), duplicate area keys (R32),
infinite feature values, and non-canonical months.

The manifest records M, O, mode/designation, the model-combination reference (envelope + package + feature order,
R19), per-horizon file sha256/rows/target month/missing counts, method identifiers (R40), per-family coverage ends and
source-level gaps (R43/R53/R59/R65), warnings (e.g. snapshot older than O, R62), acceptance records consumed (R45) and
retained-input references (table HEAD versions), and the generation time. Inference-only requests reference the
manifest by ``{uri, generation, sha256}``.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from cloud.common.object_store import ObjectStore
from cloud.ipcch import binding as bd
from cloud.ipcch.stores import StoreError

SCHEMA = "ipcch-feature-batch-v1"
HORIZONS = {2: 0, 8: 6, 14: 12}                       # model horizon -> public lead
IDENTITY = ("admin_code", "area_id", "population_estimate", "population_reference_period",
            "population_imputation_method")
_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


class BatchError(StoreError):
    """A feature batch violates the batch contract; nothing usable was written."""


def add_months(month: str, k: int) -> str:
    y, m = (int(x) for x in month.split("-"))
    o = y * 12 + m - 1 + k
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def new_batch_id(run_id: str, execution_month: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id or "") or not _MONTH.fullmatch(execution_month or ""):
        raise BatchError("run_id must be a plain identifier and M a YYYY-MM month")
    return f"ipcch-{execution_month}-{run_id}-{uuid.uuid4().hex[:12]}"


def roster_sha256(roster: Iterable[Any]) -> str:
    return hashlib.sha256("\n".join(sorted(str(a) for a in roster)).encode()).hexdigest()


def _check_frame(frame: pd.DataFrame, h: int, order: tuple[str, ...], roster: list[str]) -> None:
    cols = list(frame.columns)
    if cols != [*IDENTITY, *order]:
        lacking = [c for c in [*IDENTITY, *order] if c not in cols]
        raise BatchError(f"H{h}: columns must be identity + the package feature order; lacking {lacking[:5]}, "
                         f"{len(cols)} columns")
    codes = frame["admin_code"].astype(str)
    if codes.duplicated().any():
        raise BatchError(f"H{h}: duplicate area keys {sorted(set(codes[codes.duplicated()]))[:5]} (R32)")
    if set(codes) != set(roster):
        missing, extra = sorted(set(roster) - set(codes)), sorted(set(codes) - set(roster))
        raise BatchError(f"H{h}: rows must be exactly the roster; missing {missing[:5]} ({len(missing)}), "
                         f"unknown {extra[:5]} ({len(extra)})")
    values = frame[list(order)].to_numpy(dtype="float64")
    if np.isinf(values).any():
        r, c = np.argwhere(np.isinf(values))[0]
        raise BatchError(f"H{h}: infinite value at area {codes.iloc[r]} column {order[c]}")


def write_batch(store: ObjectStore, batch_root: str, *, batch_id: str, run_id: str, mode: str, execution_month: str,
                binding: bd.Binding, horizons: Mapping[int, pd.DataFrame], roster: Iterable[Any],
                generation: Mapping[str, Any], acceptance: list[Mapping[str, Any]], retained_refs: Mapping[str, Any],
                generated_at: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Write one immutable batch; returns (manifest reference {uri, generation, sha256}, manifest)."""
    if mode != binding.mode:
        raise BatchError(f"a {mode} batch cannot be written with a {binding.mode} combination binding (R36)")
    if not batch_root.startswith("gs://") or batch_root.endswith("/") or batch_root.rsplit("/", 1)[-1] != mode:
        raise BatchError(f"batch root must be the {mode} namespace root gs://.../{mode} (R48)")
    if not batch_id.startswith(f"ipcch-{execution_month}-{run_id}-"):
        raise BatchError("batch id must be bound to this run id and execution month (R52)")
    if sorted(horizons) != sorted(HORIZONS):
        raise BatchError(f"a batch holds exactly H2/H8/H14, got {sorted(horizons)} (R18)")
    origin = add_months(execution_month, -2)
    roster = [str(a) for a in roster]
    order = tuple(binding.feature_order)
    for h, frame in horizons.items():
        _check_frame(frame, h, order, roster)
    base = f"{batch_root}/feature_batches/{batch_id}"
    if store.list(base + "/"):
        raise BatchError(f"batch {batch_id} already has objects; batches are never overwritten (R52)")
    files = {}
    for h in sorted(horizons):
        frame = horizons[h]
        text = frame.to_csv(index=False, lineterminator="\n", float_format=None)
        uri = f"{base}/h{h:02d}.csv"
        meta = store.write_text(uri, text, if_generation_match=0)
        target = add_months(origin, h)
        files[str(h)] = {"file": uri, "generation": meta.generation, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "rows": int(len(frame)), "model_horizon_months": h, "public_lead_months": HORIZONS[h],
                         "feature_origin": origin, "target_month": target,
                         "missing_by_column": {c: int(n) for c, n in frame[list(order)].isna().sum().items() if n}}
    manifest = {
        "schema": SCHEMA, "batch_id": batch_id, "run_id": run_id, "mode": mode,
        "designation": "dummy" if mode == "smoke" else "real", "execution_month": execution_month,
        "feature_origin": origin, "generated_at": generated_at,
        "combination": {**binding.reference(), "scopes": dict(binding.scopes)},
        "feature_order_sha256": binding.feature_order_sha256, "feature_count": len(order),
        "identity_columns": list(IDENTITY),
        "roster": {"size": len(roster), "sha256": roster_sha256(roster),
                   "kind": "declared smoke subset" if mode == "smoke" else "full bound roster"},
        "horizons": files, "generation": dict(generation), "acceptance_consumed": list(acceptance),
        "retained_inputs": dict(retained_refs),
    }
    text = json.dumps(manifest, indent=1, sort_keys=True, default=str) + "\n"
    summary = {k: manifest[k] for k in ("batch_id", "run_id", "mode", "designation", "execution_month", "feature_origin",
                                        "generated_at", "combination")}
    summary["horizons"] = {h: {k: v[k] for k in ("rows", "target_month", "public_lead_months")} for h, v in files.items()}
    summary["coverage_and_warnings"] = {k: manifest["generation"].get(k) for k in ("coverage_end", "gaps", "warnings")}
    store.write_text(f"{base}/summary.json", json.dumps(summary, indent=1, sort_keys=True, default=str) + "\n",
                     if_generation_match=0)
    meta = store.write_text(f"{base}/manifest.json", text, if_generation_match=0)            # last: batch complete
    return {"uri": f"{base}/manifest.json", "generation": meta.generation,
            "sha256": hashlib.sha256(text.encode()).hexdigest()}, manifest
