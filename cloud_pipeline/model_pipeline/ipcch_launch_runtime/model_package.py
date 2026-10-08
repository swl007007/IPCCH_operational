"""Load packaged launch models and their feature contract artifacts."""

import json
from pathlib import Path

import pandas as pd


REQUIRED_TARGETS = (
    "phase2_worse",
    "phase3_worse",
    "phase4_worse",
    "phase5_worse",
)


class ModelPackageError(ValueError):
    """Raised when a launch model package cannot be loaded."""


def load_scope_package(package_root: Path, scope_months: int) -> dict:
    """Load one ``scope_{n}m`` model package from disk."""
    package_root = Path(package_root)
    scope_dir = package_root / "scope_{0}m".format(scope_months)
    required_paths = {
        "feature_columns": scope_dir / "feature_columns.json",
        "contract": scope_dir / "feature_contract.csv",
        "metadata": scope_dir / "model_metadata.json",
    }
    for target in REQUIRED_TARGETS:
        required_paths[target] = scope_dir / "{0}_model.json".format(target)

    missing = [path for path in required_paths.values() if not path.exists()]
    if missing:
        raise ModelPackageError(
            "Missing required model package file(s): {0}".format(
                ", ".join(str(path) for path in missing)
            )
        )

    feature_columns = _read_json(required_paths["feature_columns"], "feature_columns")
    if isinstance(feature_columns, dict):
        feature_columns = feature_columns.get("feature_columns")
    if not isinstance(feature_columns, list):
        raise ModelPackageError("feature_columns.json must contain a list of feature names")
    feature_columns = [str(column) for column in feature_columns]

    metadata = _read_json(required_paths["metadata"], "model metadata")
    if not isinstance(metadata, dict):
        raise ModelPackageError("model_metadata.json must contain a JSON object")

    try:
        contract = pd.read_csv(required_paths["contract"])
    except Exception as exc:
        raise ModelPackageError(
            "Failed to read feature_contract.csv: {0}".format(exc)
        ) from exc

    xgboost = _import_xgboost()
    models = {}
    for target in REQUIRED_TARGETS:
        model = xgboost.XGBRegressor()
        try:
            model.load_model(str(required_paths[target]))
        except Exception as exc:
            raise ModelPackageError(
                "Failed to load XGBoost model {0}: {1}".format(
                    required_paths[target], exc
                )
            ) from exc
        models[target] = model

    return {
        "feature_columns": feature_columns,
        "metadata": metadata,
        "contract": contract,
        "models": models,
        "scope_dir": scope_dir,
    }


def _read_json(path, label):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ModelPackageError("Invalid JSON in {0}: {1}".format(path, exc)) from exc
    except OSError as exc:
        message = "Failed to read {0} from {1}: {2}".format(label, path, exc)
        raise ModelPackageError(message) from exc


def _import_xgboost():
    try:
        import xgboost
    except ImportError as exc:
        raise ModelPackageError(
            "xgboost is required to load launch model packages"
        ) from exc
    return xgboost
