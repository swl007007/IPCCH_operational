"""CP0 DIAGNOSTIC REPORT (not a passing validator) for the six candidate April packages.

Task evidence script, not product code. It always exits 0 after writing its report;
mismatch counts must be read from the JSON, and nothing here constitutes acceptance. Loads each candidate package through the
existing validated loaders. IPCCH: scores the exact April input that produced the
saved April predictions and compares. FEWS: load/identity only at CP0; the 773 MB
panel replay is deferred. No training, no writes outside the
given evidence directory, no network.

Run from the repository root with the frozen environment:
    ~/.venvs/ipcch-h5-202609/bin/python -B \
        .trellis/tasks/10-07-october-cloud-delivery/research/cp0_replay_candidates.py \
        --evidence-dir /tmp/cp0-replay
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path.cwd()
sys.path.insert(0, str(REPO))

FEWS_PANEL = Path(
    "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/"
    "assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv"
)
FEWS_PANEL_SHA256 = "510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d"
FEWS_SUITE = "local-202604-57cb3b981198-510375f58cd8"
FEWS_ROOT = REPO / "Outcome/fewsnet_partitioned_rf"
IPCCH_INPUT = "Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv"
IPCCH_INPUT_SHA256 = "bc96b23d74c22d9e2e55fcb7e8d693b2dc978cb63a0a3e0fe92ec946443ec92d"
IPCCH_PACKAGE = REPO / "model_artifacts/launch_2026_04"
IPCCH_SAVED = REPO / "Outcome/ipcch_unified/predictions/202604"
FEATURE_MONTH = "2026-04"
HORIZONS = (0, 6, 12)
ATOL = 1e-12


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def environment() -> dict:
    names = [
        "numpy", "pandas", "scipy", "scikit-learn", "imbalanced-learn",
        "joblib", "xgboost", "geopandas", "pyarrow",
    ]
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "libraries": {name: metadata.version(name) for name in names},
    }


def compare_numeric(name: str, replay: pd.Series, saved: pd.Series) -> dict:
    left = pd.to_numeric(replay, errors="raise").to_numpy(dtype="float64")
    right = pd.to_numeric(saved, errors="raise").to_numpy(dtype="float64")
    both_nan = np.isnan(left) & np.isnan(right)
    equal = both_nan | (np.abs(left - right) <= ATOL)
    return {
        "column": name,
        "rows": int(len(left)),
        "mismatches": int((~equal).sum()),
        "max_abs_diff": float(np.nanmax(np.abs(left - right))) if len(left) else 0.0,
        "mismatch_index": np.flatnonzero(~equal).tolist()[:20],
    }


def load_fews_packages() -> dict:
    """Load-only check: full panel replay is deferred past CP0 (supervisor timebox)."""
    from fewsnet_partitioned_rf_pipeline.config import HORIZON_KEYS
    from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package

    result = {"panel_replay": "deferred_beyond_cp0", "horizons": {}}
    for horizon in HORIZONS:
        key = HORIZON_KEYS[horizon]
        package_dir = FEWS_ROOT / "model_artifacts" / FEWS_SUITE / key
        loaded = load_local_model_package(
            package_dir, expected_panel_sha256=FEWS_PANEL_SHA256
        )
        predictor = loaded.predictor
        result["horizons"][key] = {
            "loaded": True,
            "model_joblib_sha256": sha256(package_dir / "model.joblib"),
            "horizon_months": predictor.horizon_months,
            "threshold": float(predictor.threshold),
            "feature_count": len(predictor.feature_contract.feature_columns)
            if hasattr(predictor.feature_contract, "feature_columns") else None,
            "imputer_type": type(predictor.imputer).__name__,
            "manifest_feature_month": loaded.manifest["feature_month"],
            "manifest_latest_label_month": loaded.manifest["latest_label_month"],
        }
    return result


def replay_ipcch() -> dict:
    sys.path.insert(0, str(REPO / "model_pipeline"))
    from model_pipeline import run_operational_launch_inference as launch
    from model_pipeline.ipcch_launch_runtime import adapters

    observed_input_sha = sha256(REPO / IPCCH_INPUT)
    if observed_input_sha != IPCCH_INPUT_SHA256:
        raise SystemExit(f"IPCCH input hash mismatch: {observed_input_sha}")
    input_df = launch._read_monthly_csv(REPO / IPCCH_INPUT)
    monthly_rows, _ = adapters.validate_monthly_input(input_df, FEATURE_MONTH)

    result = {"input_sha256": observed_input_sha, "scopes": {}}
    for scope in HORIZONS:
        predictions, _ = launch.run_scope(
            monthly_rows=monthly_rows,
            model_package_root=IPCCH_PACKAGE,
            feature_month=FEATURE_MONTH,
            scope_months=scope,
            target_month=launch.add_calendar_months(FEATURE_MONTH, scope),
            source_input=IPCCH_INPUT,
        )
        saved = pd.read_csv(
            IPCCH_SAVED / f"ipcch_launch_202604_scope_{scope}m_predictions.csv",
            dtype={"area_id": "string", "admin_code": "string"},
        )
        replay = predictions.reset_index(drop=True)
        scope_result = {
            "rows": [len(saved), len(replay)],
            "area_ids_equal": replay["area_id"].astype(str).tolist()
            == saved["area_id"].astype(str).tolist(),
            "columns": {},
        }
        for phase in (2, 3, 4, 5):
            score = f"phase{phase}_worse_score"
            pred = f"phase{phase}_worse_pred"
            raw = pd.to_numeric(replay[score]).to_numpy(dtype="float64")
            kept = pd.to_numeric(saved[score]).to_numpy(dtype="float64")
            exact = np.abs(raw - kept) <= ATOL
            # Saved April files were clipped at zero on 2026-07-30; the only
            # accepted difference is a negative raw score saved as 0.
            clipped = (raw < 0) & (kept == 0)
            scope_result["columns"][score] = {
                "exact_matches": int(exact.sum()),
                "explained_by_saved_zero_clip": int((~exact & clipped).sum()),
                "unexplained_mismatches": int((~exact & ~clipped).sum()),
                "replay_negative_count": int((raw < 0).sum()),
                "max_abs_diff_unexplained": float(
                    np.max(np.abs(raw - kept)[~exact & ~clipped])
                ) if (~exact & ~clipped).any() else 0.0,
            }
            scope_result["columns"][pred] = {
                "mismatches": int(
                    (replay[pred].astype(int).to_numpy() != saved[pred].astype(int).to_numpy()).sum()
                )
            }
        scope_result["overall_phase_mismatches"] = int(
            (replay["overall_phase_pred"].astype(int).to_numpy()
             != saved["overall_phase_pred"].astype(int).to_numpy()).sum()
        )
        for model_file in sorted((IPCCH_PACKAGE / f"scope_{scope}m").iterdir()):
            scope_result.setdefault("package_sha256", {})[model_file.name] = sha256(model_file)
        result["scopes"][f"{scope}m"] = scope_result
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args()
    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "environment": environment(),
        "feature_month": FEATURE_MONTH,
        "tolerance": {"rtol": 0, "atol": ATOL},
        "fewsnet": load_fews_packages(),
        "ipcch": replay_ipcch(),
    }
    out = evidence_dir / "cp0_replay_report.json"
    with open(out, "x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
