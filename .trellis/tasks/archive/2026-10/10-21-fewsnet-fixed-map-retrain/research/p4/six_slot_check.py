"""Six-slot runtime evidence for the FEWS retrain release (no evaluation, no IPCCH inference).

Run with the runtime's own modules on PYTHONPATH (the exact-lock local env, or inside the image).
FEWS: full package validation/load of the three all-history packages, then scoring of the frozen
October FEWS scope inputs (prediction SHA-256 compared with ``reference.json`` when present).
IPCCH: load of the three unchanged scope packages and their member hashes only.

usage: six_slot_check.py EVIDENCE_DIR [--write-reference]
"""

import hashlib
import importlib.metadata as metadata
import json
import platform
import sys
from pathlib import Path

import pandas as pd

import fewsnet_partitioned_rf_pipeline
import model_pipeline
from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
from model_pipeline.ipcch_launch_runtime.model_package import load_scope_package

SUITE = "full-202610-ff389b11af93-02caeb861750"
SOURCE_COMMIT = "ff389b11af93f08e748ffdf86ab8cccae09fb3ff"
PANEL_SHA256 = "02caeb8617507028943efee21a68066daded66857de0dff758062b2859fd583a"
PACKAGES = ("numpy", "pandas", "scikit-learn", "imbalanced-learn", "joblib", "scipy", "xgboost")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree(directory: Path) -> dict:
    return {p.relative_to(directory).as_posix(): sha(p.read_bytes())
            for p in sorted(directory.rglob("*")) if p.is_file()}


def main(root: Path, write_reference: bool) -> dict:
    runtime_root = Path(fewsnet_partitioned_rf_pipeline.__file__).resolve().parents[1]
    lock = runtime_root / "requirements.lock.txt"
    result = {"python": platform.python_version(), "executable": sys.executable,
              "module_roots": {"fewsnet_partitioned_rf_pipeline": str(Path(fewsnet_partitioned_rf_pipeline.__file__).parent),
                               "model_pipeline": list(model_pipeline.__path__)},
              "versions": {name: metadata.version(name) for name in PACKAGES},
              "requirements_lock_sha256": sha(lock.read_bytes()) if lock.is_file() else None,
              "fewsnet": {}, "ipcch": {}}
    for horizon in (0, 6, 12):
        loaded = load_local_model_package(root / f"fewsnet/{horizon}m", expected_suite_version=SUITE,
                                          expected_source_git_commit=SOURCE_COMMIT, expected_panel_sha256=PANEL_SHA256)
        frame = pd.read_csv(root / f"inputs/fewsnet_scope_{horizon}m_inference.csv", dtype={"admin_code": str},
                            float_precision="round_trip", low_memory=False)
        predictions = loaded.predictor.predict_frame(frame)
        text = predictions.to_csv(index=False, float_format="%.17g").encode()
        result["fewsnet"][f"{horizon}m"] = {
            "package_checksums": loaded.checksums, "threshold": float(loaded.predictor.threshold),
            "input_sha256": sha((root / f"inputs/fewsnet_scope_{horizon}m_inference.csv").read_bytes()),
            "rows": int(len(predictions)), "areas": int(predictions["admin_code"].nunique()),
            "prediction_sha256": sha(text)}
    for horizon in (0, 6, 12):
        package = load_scope_package(root / "ipcch", horizon)
        result["ipcch"][f"{horizon}m"] = {"feature_columns": len(package["feature_columns"]),
                                          "targets": sorted(package["models"]),
                                          "members": tree(Path(package["scope_dir"]))}
    result["ipcch_shared_members"] = {name: sha((root / "ipcch" / name).read_bytes())
                                      for name in ("model_package_manifest.json", "training_export_summary.json")}
    reference = root / "reference.json"
    if write_reference:
        reference.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    elif reference.is_file():
        expected = json.loads(reference.read_text())
        result["matches_reference"] = {
            "fewsnet_predictions": all(result["fewsnet"][h]["prediction_sha256"] == expected["fewsnet"][h]["prediction_sha256"]
                                       for h in result["fewsnet"]),
            "fewsnet_packages": all(result["fewsnet"][h]["package_checksums"] == expected["fewsnet"][h]["package_checksums"]
                                    for h in result["fewsnet"]),
            "ipcch_packages": result["ipcch"] == expected["ipcch"]
                              and result["ipcch_shared_members"] == expected["ipcch_shared_members"],
            "versions": result["versions"] == expected["versions"],
            "reference_sha256": sha(reference.read_bytes())}
    return result


if __name__ == "__main__":
    report = main(Path(sys.argv[1]), "--write-reference" in sys.argv[2:])
    print("SIX_SLOT_EVIDENCE " + json.dumps(report, sort_keys=True), flush=True)
