"""One-time builder: IPCCH training-resubstitution evidence for the accepted 0/6/12m scopes (D4).

No fitting. For each scope the exact training rows are rebuilt with the production-safe launch
trainer rules (``load_source`` / ``add_targets`` / ``build_training_frame`` of
``IPCCH/scripts/modeling/train_export_operational_launch_production_safe.py``, re-implemented
here verbatim), the saved feature contract + medians are applied with the cloud runtime, and the
four saved regressors are replayed:

* area evidence: per polygon, training rows and Phase3+ disagreements
  ``(phase3_worse score >= 0.2) != (phase3+ share >= 0.2)``;
* residual evidence: ``actual cumulative share - replayed score`` for phase2..5 per
  ``(polygon_id, target_month)``.

``regress-h5`` (gate G2) runs the same code path on the September h5 inputs (scope_5m package,
refreshed panel, saved training keys) and requires exact polygon counts and residuals within
``atol=1e-6`` of the accepted September files. ``build`` refuses to run unless a passing G2
report exists, then writes ``cloud_pipeline/bootstrap/evidence/ipcch_{h}m_resubstitution_*.csv``.

Float parsing follows each model's own trainer: the h5 trainer read the panel with
``float_precision="round_trip"``, the June launch trainer with the pandas default.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
sys.path.insert(0, str(CP))
from model_pipeline.ipcch_launch_runtime.feature_contract import apply_feature_contract  # noqa: E402
from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package  # noqa: E402

RAW_SHA = "ae696087c3bbb280537ae269a05924133acdb51060d31290523404fa8a717673"
H5_PANEL_SHA = "6ab4e44726666449b9c4c814cd52c89ef73fa83f7e05a480a066853d1e7e8ea3"
RAW_ORIGINAL = REPO.parent / "Google fund/Analysis/1.Source Data/assembled_IPCCH/raw/IPCCH_2026_completed.csv"
TRAINER = REPO.parent / ("Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/IPCCH/scripts/modeling/"
                         "train_export_operational_launch_production_safe.py")
PACKAGE = CP / "bootstrap/models/ipcch"
EVIDENCE = CP / "bootstrap/evidence"
REGRESSION_REPORT = HERE.parent / "ipcch_resubstitution_regression_h5.json"
BUILD_REPORT = HERE.parent / "ipcch_resubstitution_evidence.json"
SEPTEMBER = REPO / "september_manual"
TRAIN_CUTOFF = pd.Period("2026-04", freq="M")
PHASE_THRESHOLD = 0.2
BASIS = "training_resubstitution"
TARGET_PERCENT_COLUMNS = ("phase1_percent", "phase2_percent", "phase3_percent", "phase4_percent", "phase5_percent")
TARGET_FORMULAS = {
    "phase2_worse": ("phase2_percent", "phase3_percent", "phase4_percent", "phase5_percent"),
    "phase3_worse": ("phase3_percent", "phase4_percent", "phase5_percent"),
    "phase4_worse": ("phase4_percent", "phase5_percent"),
    "phase5_worse": ("phase5_percent",),
}
TARGETS = tuple(TARGET_FORMULAS)
RESIDUALS = [f"{t}_residual" for t in TARGETS]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def peak_rss_gb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 2)


# --- trainer rules (train_export_operational_launch_production_safe.py) ------------------------
def load_source(raw_csv: Path, feature_columns, float_precision) -> pd.DataFrame:
    usecols = ["admin_code", "year", "month", *TARGET_PERCENT_COLUMNS, *feature_columns]
    kwargs = {"float_precision": float_precision} if float_precision else {}
    source = pd.read_csv(raw_csv, usecols=usecols, dtype={"admin_code": "string"}, **kwargs)
    source = source.replace([np.inf, -np.inf], np.nan)
    source["area_id"] = source["admin_code"].astype("string").str.strip()
    source["year"] = pd.to_numeric(source["year"], errors="raise").astype(int)
    source["month"] = pd.to_numeric(source["month"], errors="raise").astype(int)
    source["period"] = pd.PeriodIndex(source["year"].astype(str) + "-" + source["month"].astype(str).str.zfill(2),
                                      freq="M")
    for column in [*TARGET_PERCENT_COLUMNS, *feature_columns]:
        source[column] = pd.to_numeric(source[column], errors="coerce")
    if source.duplicated(["area_id", "period"], keep=False).any():
        raise ValueError("raw source has duplicate area_id/month keys")
    return source


def add_targets(source: pd.DataFrame) -> pd.DataFrame:
    result = source.copy()
    for target, columns in TARGET_FORMULAS.items():
        result[target] = result.loc[:, list(columns)].sum(axis=1, min_count=len(columns))
    return result


def build_training_frame(source: pd.DataFrame, feature_columns, scope: int, train_cutoff: pd.Period) -> pd.DataFrame:
    labels = source.dropna(subset=list(TARGETS)).loc[:, ["area_id", "period", *TARGETS]].copy()
    labels = labels.rename(columns={"period": "target_period"})
    labels["feature_period"] = labels["target_period"].map(lambda period: pd.Period(period, freq="M") - int(scope))
    features = source.loc[:, ["area_id", "period", *feature_columns]].copy()
    features = features.rename(columns={"period": "feature_period"})
    train = features.merge(labels, on=["area_id", "feature_period"], how="inner", validate="one_to_one")
    train = train[train["feature_period"] < train_cutoff].copy()
    return train.sort_values(["feature_period", "area_id"]).reset_index(drop=True)
# -----------------------------------------------------------------------------------------------


def replay(train: pd.DataFrame, loaded: dict) -> tuple[pd.DataFrame, dict]:
    """Saved-model scores on the exact training rows; returns per-row replay + checks."""
    columns = loaded["feature_columns"]
    medians = train[columns].median(numeric_only=True)
    saved = loaded["metadata"]["imputation_statistics"]
    median_diff = max(abs(float(medians[c]) - float(saved[f"median:{c}"])) for c in columns)
    mismatched = [c for c in columns if float(medians[c]) != float(saved[f"median:{c}"])]
    matrix, _ = apply_feature_contract(train, loaded["contract"], columns, package_root=loaded["scope_dir"],
                                       metadata=loaded["metadata"])
    # The runtime contract must reproduce the trainer's own fillna(medians) design matrix.
    trainer_matrix = train[columns].fillna(medians)
    matrix_equal = bool(np.array_equal(matrix.to_numpy(dtype=float), trainer_matrix.to_numpy(dtype=float),
                                       equal_nan=True))
    rows = pd.DataFrame({"polygon_id": train["area_id"].astype(str).to_numpy(),
                         "feature_month": train["feature_period"].astype(str).to_numpy(),
                         "target_month": train["target_period"].astype(str).to_numpy()})
    for target in TARGETS:
        rows[f"{target}_actual"] = train[target].to_numpy(dtype=float)
        # float32 model output held exactly as float64 (as the September replay did).
        rows[f"{target}_predicted"] = loaded["models"][target].predict(matrix).astype(np.float64)
        rows[f"{target}_residual"] = rows[f"{target}_actual"] - rows[f"{target}_predicted"]
    if not np.isfinite(rows.filter(regex="_(actual|predicted|residual)$").to_numpy()).all():
        raise ValueError("non-finite replay values")
    rows["predicted_phase3plus"] = (rows["phase3_worse_predicted"] >= PHASE_THRESHOLD).astype(int)
    rows["actual_phase3plus"] = (rows["phase3_worse_actual"] >= PHASE_THRESHOLD).astype(int)
    rows["error"] = rows["predicted_phase3plus"].ne(rows["actual_phase3plus"]).astype(int)
    checks = {"rows": len(rows), "median_max_abs_diff": median_diff, "median_mismatch_columns": mismatched,
              "runtime_matrix_equals_trainer_fillna": matrix_equal,
              "feature_min": str(train["feature_period"].min()), "feature_max": str(train["feature_period"].max()),
              "target_min": str(train["target_period"].min()), "target_max": str(train["target_period"].max()),
              "errors": int(rows["error"].sum())}
    return rows, checks


def area_table(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.groupby("polygon_id").agg(sample_count=("error", "size"), error_count=("error", "sum")).reset_index()


def roster() -> set[str]:
    ids = pd.read_csv(CP / "bootstrap/assets/ipcch/roster.csv", dtype=str)["admin_code"].str.strip()
    assert not ids.duplicated().any() and len(ids) == 6227, len(ids)
    return set(ids)


def environment() -> dict:
    import sklearn
    import xgboost
    return {"python": sys.version.split()[0], "platform": platform.platform(), "pandas": pd.__version__,
            "numpy": np.__version__, "xgboost": xgboost.__version__, "sklearn": sklearn.__version__,
            "interpreter": sys.executable}


def regress_h5(args) -> int:
    started = time.time()
    bundle = Path(args.bundle)
    scope_dir = bundle / "ipcch/model_package"
    panel = Path(args.panel)
    panel_sha = sha256(panel)
    loaded = load_scope_package(scope_dir, 5)
    if panel_sha != H5_PANEL_SHA or loaded["metadata"]["source_panel_sha256"] != H5_PANEL_SHA:
        raise SystemExit(f"h5 panel sha {panel_sha} is not the h5 training panel {H5_PANEL_SHA}")
    columns = loaded["feature_columns"]
    source = add_targets(load_source(panel, columns, "round_trip"))  # h5 trainer parsing
    train = build_training_frame(source, columns, 5, TRAIN_CUTOFF)
    train = train[train["target_period"] <= TRAIN_CUTOFF].reset_index(drop=True)  # explicit h5 label cutoff
    del source; gc.collect()
    keys = pd.read_csv(bundle / "reports/ipcch_training_keys.csv", dtype=str)
    rebuilt = pd.DataFrame({"area_id": train["area_id"].astype(str), "feature_period": train["feature_period"].astype(str),
                            "target_period": train["target_period"].astype(str)})
    keys_equal = rebuilt.reset_index(drop=True).equals(keys[["area_id", "feature_period", "target_period"]])
    rows, checks = replay(train, loaded)
    # Counts vs accepted polygon_training_errors.csv (exact).
    accepted = pd.read_csv(SEPTEMBER / "ipcch/polygon_training_errors.csv", dtype={"polygon_id": str})
    counts = area_table(rows).merge(accepted, on="polygon_id", how="outer", indicator=True)
    both = counts["_merge"].eq("both")
    bad_counts = counts.loc[~both | counts["sample_count"].ne(counts["training_sample_count"])
                            | counts["error_count"].ne(counts["training_error_count"]), "polygon_id"].tolist()
    # Residuals vs accepted four-target replay (atol 1e-6).
    reference = pd.read_csv(SEPTEMBER / "reports/ipcch_four_target_training_replay.csv",
                            dtype={"polygon_id": str, "feature_month": str, "target_month": str})
    joined = rows.merge(reference, on=["polygon_id", "feature_month", "target_month"], how="outer",
                        suffixes=("", "_ref"), indicator=True, validate="one_to_one")
    unmatched = int((~joined["_merge"].eq("both")).sum())
    diffs = {}
    for target in TARGETS:
        for kind in ("actual", "predicted", "residual"):
            column = f"{target}_{kind}"
            diffs[column] = float(np.nanmax(np.abs(joined[column] - joined[f"{column}_ref"])))
    max_residual = max(diffs[c] for c in RESIDUALS)
    passed = (keys_equal and not checks["median_mismatch_columns"] and checks["runtime_matrix_equals_trainer_fillna"]
              and not bad_counts and unmatched == 0 and max_residual <= 1e-6)
    report = {"gate": "G2", "passed": bool(passed), "builder": str(HERE.relative_to(REPO)), "builder_sha256": sha256(HERE),
              "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
              "environment": environment(), "float_precision": "round_trip (h5 trainer)",
              "inputs": {"panel_sha256": panel_sha, "bundle": str(bundle),
                         "september_bundle_sha256": "see september_manual/inventory.json webapp_model_bundle.tar.gz",
                         "training_keys_sha256": sha256(bundle / "reports/ipcch_training_keys.csv"),
                         "scope_5m_model_sha256": {t: sha256(scope_dir / f"scope_5m/{t}_model.json") for t in TARGETS}},
              "training_keys_equal_saved": bool(keys_equal), "replay_checks": checks,
              "polygon_count_comparison": {"reference": "september_manual/ipcch/polygon_training_errors.csv",
                                           "reference_sha256": sha256(SEPTEMBER / "ipcch/polygon_training_errors.csv"),
                                           "polygons": int(both.sum()), "mismatched_polygons": bad_counts[:50],
                                           "mismatch_count": len(bad_counts),
                                           "total_samples": int(counts["sample_count"].sum()),
                                           "total_errors": int(counts["error_count"].sum()),
                                           "accepted_total_errors": int(accepted["training_error_count"].sum())},
              "residual_comparison": {"reference": "september_manual/reports/ipcch_four_target_training_replay.csv",
                                      "reference_sha256": sha256(SEPTEMBER / "reports/ipcch_four_target_training_replay.csv"),
                                      "atol": 1e-6, "unmatched_rows": unmatched, "max_abs_diff": diffs,
                                      "max_abs_residual_diff": max_residual},
              "wall_seconds": round(time.time() - started, 1), "peak_rss_gb": peak_rss_gb()}
    REGRESSION_REPORT.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("passed", "training_keys_equal_saved", "replay_checks",
                                             "polygon_count_comparison", "residual_comparison", "wall_seconds",
                                             "peak_rss_gb")}, indent=1))
    return 0 if passed else 1


def write_create_only(path: Path, data: bytes) -> str:
    if path.exists():
        if path.read_bytes() != data:
            raise SystemExit(f"{path} exists with different bytes; refusing to overwrite")
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    assert tmp.read_bytes() == data
    tmp.rename(path)
    return "written"


def build(args) -> int:
    started = time.time()
    gate = json.loads(REGRESSION_REPORT.read_text()) if REGRESSION_REPORT.exists() else {}
    if not gate.get("passed") or gate.get("builder_sha256") != sha256(HERE):
        raise SystemExit("G2 regression report missing, failed, or produced by another builder version")
    panel = Path(args.panel)
    panel_sha = sha256(panel)
    if panel_sha != RAW_SHA:
        raise SystemExit(f"raw panel sha {panel_sha} is not the launch training panel {RAW_SHA}")
    baseline = json.loads((CP / "bootstrap/baseline.json").read_text())
    packages = {m["horizon_months"]: m["package_id"] for m in baseline["models"] if m["system"] == "ipcch"}
    summary = {s["scope_months"]: s for s in json.loads((PACKAGE / "training_export_summary.json").read_text())["scope_summaries"]}
    columns_by_scope = {h: json.loads((PACKAGE / f"scope_{h}m/feature_columns.json").read_text()) for h in (0, 6, 12)}
    union = list(dict.fromkeys(c for h in (0, 6, 12) for c in columns_by_scope[h]))
    source = add_targets(load_source(panel, union, None))  # launch trainer: default float parsing
    ids = roster()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    report = {"builder": str(HERE.relative_to(REPO)), "builder_sha256": sha256(HERE),
              "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
              "environment": environment(), "float_precision": "pandas default (launch trainer)",
              "regression_gate": {"report": str(REGRESSION_REPORT.relative_to(REPO)), "passed": True},
              "source": {"path": str(RAW_ORIGINAL.relative_to(REPO.parent)), "sha256": panel_sha,
                         "size": panel.stat().st_size, "rows": len(source)},
              "trainer": {"path": str(TRAINER.relative_to(REPO.parent)), "sha256": sha256(TRAINER),
                          "rules": "load_source/add_targets/build_training_frame re-implemented verbatim"},
              "roster": {"path": "cloud_pipeline/bootstrap/assets/ipcch/roster.csv",
                         "sha256": sha256(CP / "bootstrap/assets/ipcch/roster.csv"), "size": len(ids)},
              "phase3_threshold": PHASE_THRESHOLD, "evidence": {}, "scopes": {}}
    for horizon in (0, 6, 12):
        loaded = load_scope_package(PACKAGE, horizon)
        columns = loaded["feature_columns"]
        train = build_training_frame(source, columns, horizon, TRAIN_CUTOFF)
        rows, checks = replay(train, loaded)
        expected = summary[horizon]
        observed = (checks["rows"], checks["feature_min"], checks["feature_max"], checks["target_min"], checks["target_max"])
        wanted = (expected["train_rows"], expected["train_min_feature_month"], expected["train_max_feature_month"],
                  expected["target_min_month"], expected["target_max_month"])
        if observed != wanted or checks["median_mismatch_columns"] or not checks["runtime_matrix_equals_trainer_fillna"]:
            raise SystemExit(f"scope_{horizon}m reconstruction differs from the saved package: {observed} vs {wanted}; "
                             f"{checks}")
        rows.to_csv(workdir / f"ipcch_{horizon}m_training_replay.csv", index=False)
        period = f"{checks['target_min']}..{checks['target_max']}"
        dropped = sorted(set(rows["polygon_id"]) - ids, key=lambda x: (len(x), x))
        kept = rows.loc[rows["polygon_id"].isin(ids)]
        identity = {"model_package_id": packages[horizon], "horizon_months": horizon, "basis": BASIS, "period": period}
        area = area_table(kept).sort_values("polygon_id", key=lambda s: s.astype(int)).reset_index(drop=True)
        residual = kept[["polygon_id", "target_month", *RESIDUALS]].sort_values(
            ["polygon_id", "target_month"], key=lambda s: s.astype(int) if s.name == "polygon_id" else s).reset_index(drop=True)
        if residual.duplicated(["polygon_id", "target_month"]).any():
            raise SystemExit(f"scope_{horizon}m: duplicate polygon/target month residual rows")
        for frame in (area, residual):
            for key, value in identity.items():
                frame[key] = value
        outputs = {f"ipcch_{horizon}m_resubstitution_area.csv": area,
                   f"ipcch_{horizon}m_resubstitution_residual.csv": residual}
        for name, frame in outputs.items():
            data = frame.to_csv(index=False, lineterminator="\n").encode()
            status = write_create_only(EVIDENCE / name, data)
            report["evidence"][name] = {"system": "ipcch", **identity, "rows": len(frame), "sha256": hashlib.sha256(data).hexdigest(),
                                        "size": len(data), "write": status}
        report["scopes"][f"scope_{horizon}m"] = {
            **checks, "model_sha256": {t: sha256(PACKAGE / f"scope_{horizon}m/{t}_model.json") for t in TARGETS},
            "metadata_sha256": sha256(PACKAGE / f"scope_{horizon}m/model_metadata.json"),
            "dropped_non_roster_ids": dropped, "dropped_rows": int(len(rows) - len(kept)),
            "kept_rows": len(kept), "kept_polygons": int(kept["polygon_id"].nunique()),
            "roster_polygons_without_rows": len(ids - set(kept["polygon_id"])),
            "kept_errors": int(kept["error"].sum()),
            "workdir_replay": str(workdir / f"ipcch_{horizon}m_training_replay.csv")}
        print(f"scope_{horizon}m: rows {len(rows)} kept {len(kept)} polygons {kept['polygon_id'].nunique()} "
              f"errors {int(kept['error'].sum())} period {period} dropped_ids {len(dropped)}", flush=True)
        del train, rows, kept; gc.collect()
    report["wall_seconds"] = round(time.time() - started, 1)
    report["peak_rss_gb"] = peak_rss_gb()
    BUILD_REPORT.write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    r = sub.add_parser("regress-h5")
    r.add_argument("--bundle", required=True, help="extracted September webapp_model_bundle root")
    r.add_argument("--panel", required=True, help="h5 training panel (sha 6ab4e447...)")
    b = sub.add_parser("build")
    b.add_argument("--panel", required=True, help="IPCCH_2026_completed.csv copy (sha ae696087...)")
    b.add_argument("--workdir", required=True, help="Linux-FS scratch directory for per-row replay CSVs")
    parsed = parser.parse_args()
    raise SystemExit(regress_h5(parsed) if parsed.action == "regress-h5" else build(parsed))
