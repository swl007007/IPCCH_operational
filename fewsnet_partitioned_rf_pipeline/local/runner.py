"""Fail-closed local orchestration for the three FEWSNET RF horizons."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fewsnet_partitioned_rf_pipeline.config import (
    ADMIN_SOURCE_COLUMN,
    FEATURE_CONTRACT_PATH,
    HORIZON_KEYS,
    HORIZON_MONTHS,
    PARTITION_ASSET_PATH,
    PARTITION_ASSET_SHA256,
    TRAIN_WINDOW_MONTHS,
)
from fewsnet_partitioned_rf_pipeline.core.data import (
    PANEL_CHUNK_SIZE,
    inspect_panel,
    normalize_admin_code,
)
from fewsnet_partitioned_rf_pipeline.core.horizons import (
    align_horizon,
    select_latest_inference_frame,
    select_training_window,
)
from fewsnet_partitioned_rf_pipeline.core.normalization import (
    validate_normalization_audit,
)
from fewsnet_partitioned_rf_pipeline.core.partitions import PartitionMap
from fewsnet_partitioned_rf_pipeline.core.preprocessing import (
    Stage3FeatureBuilder,
    load_feature_contract,
)
from fewsnet_partitioned_rf_pipeline.core.training import train_horizon_model
from fewsnet_partitioned_rf_pipeline.core.types import FeatureContract
from fewsnet_partitioned_rf_pipeline.core.validation import (
    runtime_dependency_versions,
)
from fewsnet_partitioned_rf_pipeline.local.outputs import (
    PopulationSummary,
    build_identity_population_frame,
    enrich_local_predictions,
    validate_local_prediction_suite,
    write_local_prediction_csv,
)
from fewsnet_partitioned_rf_pipeline.local.package import (
    LoadedLocalModelPackage,
    LocalPackageMetadata,
    load_local_model_package,
    write_local_model_package,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload


EXPECTED_AREA_COUNT = 5718
FEATURE_CONTRACT_FILE_SHA256 = (
    "3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b"
)
PREDICTION_FILENAMES = {
    "0m": "fewsnet_partitioned_rf_202604_scope_0m_predictions.csv",
    "6m": "fewsnet_partitioned_rf_202604_scope_6m_predictions.csv",
    "12m": "fewsnet_partitioned_rf_202604_scope_12m_predictions.csv",
}

_ACCEPTED_FEATURE_MONTH = "2026-04"
_ACCEPTED_LATEST_LABEL_MONTH = "2026-02"
_HORIZON_ORDER = tuple(HORIZON_KEYS[months] for months in HORIZON_MONTHS)
_REPORT_FILENAMES = {
    "training_threshold_report": "training_threshold_report.json",
    "run_manifest": "run_manifest.json",
}
_RUN_ID_PATTERN = re.compile(
    r"^local-[0-9]{6}-[0-9]{8}T[0-9]{12}Z$"
)
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_IPCCH_ROOT = (_REPOSITORY_ROOT / "Outcome/ipcch_unified").resolve()
_RUN_MANIFEST_FIELDS = {
    "schema_version",
    "run_id",
    "suite_version",
    "created_at_utc",
    "runtime_backend",
    "gcp_write_performed",
    "source_git_commit",
    "dependency_versions",
    "panel",
    "normalization_audit",
    "feature_contract",
    "partition_asset",
    "latest_feature_month",
    "latest_label_month",
    "training_target_month_range",
    "validation_target_month_range",
    "horizons",
    "model_packages",
    "status",
}


@dataclass(frozen=True)
class LocalExperimentConfig:
    panel_path: Path
    normalization_audit_path: Path
    feature_month: str
    output_root: Path
    overwrite: bool = False


@dataclass(frozen=True)
class StagedLocalExperiment:
    run_id: str
    suite_version: str
    panel_sha256: str
    source_git_commit: str
    staging_root: Path
    reused_model_suite: bool
    package_dirs: dict[str, Path]
    prediction_files: dict[str, Path]
    report_files: dict[str, Path]
    run_summary_path: Path


@dataclass(frozen=True)
class _PreflightResult:
    panel_path: Path
    audit_path: Path
    output_root: Path
    panel_sha256: str
    panel_size_bytes: int
    panel_row_count: int
    audit_sha256: str
    audit_size_bytes: int
    panel_info: dict[str, object]
    feature_contract: FeatureContract
    partition_map: PartitionMap
    source_git_commit: str
    dependency_versions: dict[str, str]
    suite_version: str
    run_id: str
    started_at_utc: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolved_casefolded_parts(path: str | Path) -> tuple[str, ...]:
    resolved = Path(path).expanduser().resolve()
    return tuple(part.casefold() for part in resolved.parts)


def _paths_equal(left: str | Path, right: str | Path) -> bool:
    return _resolved_casefolded_parts(left) == _resolved_casefolded_parts(right)


def _path_is_equal_or_within(path: str | Path, root: str | Path) -> bool:
    path_parts = _resolved_casefolded_parts(path)
    root_parts = _resolved_casefolded_parts(root)
    return (
        len(path_parts) >= len(root_parts)
        and path_parts[: len(root_parts)] == root_parts
    )


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(dict(payload), stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _read_json_object(path: Path, name: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{name} must be an existing regular file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return payload


def _resolve_input_file(value: object, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a path")
    path = Path(value).expanduser().resolve()
    _reject_ipcch_path(path, name)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{name} must be an existing regular file: {path}")
    return path


def _reject_ipcch_path(path: Path, name: str) -> None:
    parts = _resolved_casefolded_parts(path)
    contains_forbidden_subtree = any(
        left == "outcome" and right == "ipcch_unified"
        for left, right in zip(parts, parts[1:], strict=False)
    )
    inside_repository_forbidden_root = _path_is_equal_or_within(
        path,
        _FORBIDDEN_IPCCH_ROOT,
    )
    if not contains_forbidden_subtree and not inside_repository_forbidden_root:
        return
    raise ValueError(
        f"{name} must not equal or fall inside Outcome/ipcch_unified: {path}"
    )


def _resolve_output_root(value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError("output_root must be a path")
    output_root = Path(value).expanduser().resolve()
    _reject_ipcch_path(output_root, "output_root")
    if output_root.exists() and not output_root.is_dir():
        raise ValueError("output_root must be a directory path")
    return output_root


def _normalize_feature_month(value: object) -> str:
    candidate = value.strip() if isinstance(value, str) else value
    try:
        missing = bool(pd.isna(candidate))
    except (TypeError, ValueError):
        missing = False
    if missing or candidate == "":
        raise ValueError("feature_month must be a valid monthly period")
    try:
        return str(pd.Period(candidate, freq="M"))
    except (TypeError, ValueError) as exc:
        raise ValueError("feature_month must be a valid monthly period") from exc


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid UTC timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must be a UTC timestamp")
    return parsed


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _run_id(feature_month: str, started_at_utc: str) -> str:
    started = _parse_utc(started_at_utc, "started_at_utc")
    return (
        f"local-{feature_month.replace('-', '')}-"
        f"{started.strftime('%Y%m%dT%H%M%S%fZ')}"
    )


def _git_command(repo_root: Path, arguments: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def resolve_clean_git_commit(repo_root: str | Path) -> str:
    """Return HEAD only when staged and unstaged tracked files are clean."""
    requested_root = Path(repo_root).expanduser().resolve()
    top_level_result = _git_command(
        requested_root,
        ["rev-parse", "--show-toplevel"],
    )
    if top_level_result.returncode != 0:
        raise ValueError("repo_root must be inside a Git worktree")
    top_level = Path(top_level_result.stdout.strip()).resolve()

    for arguments in (["diff", "--quiet"], ["diff", "--cached", "--quiet"]):
        result = _git_command(top_level, list(arguments))
        if result.returncode == 1:
            raise ValueError("repository has staged or unstaged tracked Git changes")
        if result.returncode != 0:
            raise ValueError("Git tracked-change probe failed")

    head_result = _git_command(top_level, ["rev-parse", "HEAD"])
    if head_result.returncode != 0:
        raise ValueError("Git HEAD could not be resolved")
    commit = head_result.stdout.strip()
    if _COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError("Git HEAD must be a 40-character lowercase commit")
    return commit


def _validate_feature_month_universe(
    panel_path: Path,
    feature_month: str,
    authoritative_admin_codes: tuple[str, ...],
) -> None:
    selected_counts: Counter[str] = Counter()
    try:
        chunks = pd.read_csv(
            panel_path,
            usecols=[ADMIN_SOURCE_COLUMN, "date"],
            chunksize=PANEL_CHUNK_SIZE,
            dtype={ADMIN_SOURCE_COLUMN: "string"},
            keep_default_na=False,
        )
    except ValueError as exc:
        raise ValueError(
            f"panel must contain columns {[ADMIN_SOURCE_COLUMN, 'date']}: {exc}"
        ) from exc

    selected_period = pd.Period(feature_month, freq="M")
    for chunk in chunks:
        codes = chunk[ADMIN_SOURCE_COLUMN].map(normalize_admin_code)
        if codes.eq("").any():
            raise ValueError(f"panel contains missing {ADMIN_SOURCE_COLUMN}")
        dates = pd.to_datetime(chunk["date"], errors="coerce")
        if dates.isna().any():
            raise ValueError("panel contains invalid date values")
        selected_codes = codes.loc[dates.dt.to_period("M").eq(selected_period)]
        selected_counts.update(selected_codes.tolist())

    authoritative = set(authoritative_admin_codes)
    selected = set(selected_counts)
    missing = sorted(authoritative - selected)
    if missing:
        raise ValueError(
            f"requested feature month {feature_month} is missing authoritative "
            f"admin_code values: {missing[:10]}"
        )
    unexpected = sorted(selected - authoritative)
    invalid_counts = sorted(
        code for code in authoritative_admin_codes if selected_counts[code] != 1
    )
    if unexpected or invalid_counts:
        raise ValueError(
            f"requested feature month {feature_month} must contain the exact "
            "authoritative admin_code universe once each; "
            f"unexpected={unexpected[:10]}, invalid_counts={invalid_counts[:10]}"
        )


def _preflight(config: LocalExperimentConfig) -> _PreflightResult:
    if not isinstance(config, LocalExperimentConfig):
        raise TypeError("config must be a LocalExperimentConfig")
    panel_path = _resolve_input_file(config.panel_path, "panel_path")
    audit_path = _resolve_input_file(
        config.normalization_audit_path,
        "normalization_audit_path",
    )
    if _paths_equal(panel_path, audit_path):
        raise ValueError("panel and normalization audit paths must be different")
    output_root = _resolve_output_root(config.output_root)
    feature_month = _normalize_feature_month(config.feature_month)

    audit_sha256 = _sha256(audit_path)
    audit_size_bytes = audit_path.stat().st_size
    audit_payload = validate_normalization_audit(audit_path, panel_path)
    source_panel_path = Path(audit_payload["source_panel"]["path"]).resolve()
    if _paths_equal(source_panel_path, panel_path):
        raise ValueError(
            "normalization audit source-panel path must differ from normalized panel"
        )

    panel_info = inspect_panel(panel_path)
    if panel_info["row_count"] != audit_payload["output_panel"]["row_count"]:
        raise ValueError("panel row count does not match normalization audit")
    if panel_info["latest_feature_month"] != audit_payload["latest_feature_month"]:
        raise ValueError(
            "panel latest feature month does not match normalization audit"
        )
    if panel_info["latest_label_month"] != audit_payload["latest_label_month"]:
        raise ValueError("panel latest label month does not match normalization audit")
    if panel_info["area_count"] != EXPECTED_AREA_COUNT:
        raise ValueError(
            f"panel area_count {panel_info['area_count']} does not equal "
            f"required area_count {EXPECTED_AREA_COUNT}"
        )
    if panel_info["latest_feature_month"] != feature_month:
        raise ValueError(
            f"latest feature month {panel_info['latest_feature_month']} does not "
            f"equal requested feature month {feature_month}"
        )
    if feature_month != _ACCEPTED_FEATURE_MONTH:
        raise ValueError(
            f"accepted latest feature month must be {_ACCEPTED_FEATURE_MONTH}"
        )
    if panel_info["latest_label_month"] != _ACCEPTED_LATEST_LABEL_MONTH:
        raise ValueError(
            f"latest label month must be {_ACCEPTED_LATEST_LABEL_MONTH}"
        )

    authoritative_admin_codes = tuple(panel_info["admin_codes"])
    _validate_feature_month_universe(
        panel_path,
        feature_month,
        authoritative_admin_codes,
    )

    feature_contract_sha256 = _sha256(FEATURE_CONTRACT_PATH)
    if feature_contract_sha256 != FEATURE_CONTRACT_FILE_SHA256:
        raise ValueError(
            "feature contract SHA-256 mismatch: "
            f"expected {FEATURE_CONTRACT_FILE_SHA256}, "
            f"observed {feature_contract_sha256}"
        )
    feature_contract = load_feature_contract(FEATURE_CONTRACT_PATH)
    partition_map = PartitionMap.load(
        PARTITION_ASSET_PATH,
        PARTITION_ASSET_SHA256,
    )
    source_git_commit = resolve_clean_git_commit(_REPOSITORY_ROOT)
    dependency_versions = runtime_dependency_versions()
    validated_panel = audit_payload["output_panel"]
    panel_sha256 = str(validated_panel["sha256"])
    panel_size_bytes = int(validated_panel["size_bytes"])
    if (
        panel_path.stat().st_size != panel_size_bytes
        or _sha256(panel_path) != panel_sha256
    ):
        raise ValueError("panel changed during preflight")
    if (
        audit_path.stat().st_size != audit_size_bytes
        or _sha256(audit_path) != audit_sha256
    ):
        raise ValueError("normalization audit changed during preflight")
    suite_version = (
        f"local-{feature_month.replace('-', '')}-"
        f"{source_git_commit[:12]}-{panel_sha256[:12]}"
    )
    started_at_utc = utc_now()
    run_id = _run_id(feature_month, started_at_utc)
    return _PreflightResult(
        panel_path=panel_path,
        audit_path=audit_path,
        output_root=output_root,
        panel_sha256=panel_sha256,
        panel_size_bytes=panel_size_bytes,
        panel_row_count=int(panel_info["row_count"]),
        audit_sha256=audit_sha256,
        audit_size_bytes=audit_size_bytes,
        panel_info=panel_info,
        feature_contract=feature_contract,
        partition_map=partition_map,
        source_git_commit=source_git_commit,
        dependency_versions=dependency_versions,
        suite_version=suite_version,
        run_id=run_id,
        started_at_utc=started_at_utc,
    )


def _prepare_staging_root(value: str | Path, output_root: Path) -> Path:
    staging_root = Path(value).expanduser().resolve()
    _reject_ipcch_path(staging_root, "staging_root")
    if _path_is_equal_or_within(staging_root, output_root):
        raise ValueError("staging_root must be outside output_root")
    if staging_root.exists():
        if not staging_root.is_dir() or any(staging_root.iterdir()):
            raise ValueError("staging_root must be a new or empty directory")
    else:
        staging_root.mkdir(parents=True)
    return staging_root


def _verify_preflight_inputs_unchanged(preflight: _PreflightResult) -> None:
    inputs = (
        (
            "panel",
            preflight.panel_path,
            preflight.panel_size_bytes,
            preflight.panel_sha256,
        ),
        (
            "normalization audit",
            preflight.audit_path,
            preflight.audit_size_bytes,
            preflight.audit_sha256,
        ),
    )
    for name, path, expected_size, expected_sha256 in inputs:
        try:
            observed_size = path.stat().st_size
            observed_sha256 = _sha256(path)
        except OSError as exc:
            raise ValueError(f"{name} changed after preflight") from exc
        if observed_size != expected_size or observed_sha256 != expected_sha256:
            raise ValueError(f"{name} changed after preflight")


def _panel_identity(preflight: _PreflightResult) -> dict[str, object]:
    return {
        "path": str(preflight.panel_path),
        "sha256": preflight.panel_sha256,
        "size_bytes": preflight.panel_size_bytes,
        "row_count": preflight.panel_row_count,
    }


def _audit_identity(preflight: _PreflightResult) -> dict[str, object]:
    return {
        "path": str(preflight.audit_path),
        "sha256": preflight.audit_sha256,
        "size_bytes": preflight.audit_size_bytes,
    }


def _panel_content_identity(preflight: _PreflightResult) -> dict[str, object]:
    return {
        "sha256": preflight.panel_sha256,
        "size_bytes": preflight.panel_size_bytes,
        "row_count": preflight.panel_row_count,
    }


def _audit_content_identity(preflight: _PreflightResult) -> dict[str, object]:
    return {
        "sha256": preflight.audit_sha256,
        "size_bytes": preflight.audit_size_bytes,
    }


def _package_relative_path(suite_version: str, horizon_key: str) -> str:
    return f"model_artifacts/{suite_version}/{horizon_key}"


def _report_relative_path(suite_version: str, report_key: str) -> str:
    return f"reports/{suite_version}/{_REPORT_FILENAMES[report_key]}"


def _prediction_relative_path(horizon_key: str) -> str:
    return f"predictions/202604/{PREDICTION_FILENAMES[horizon_key]}"


def _validate_loaded_package_identity(
    loaded: LoadedLocalModelPackage,
    preflight: _PreflightResult,
    horizon_key: str,
) -> None:
    horizon_months = next(
        months for months in HORIZON_MONTHS if HORIZON_KEYS[months] == horizon_key
    )
    manifest = loaded.manifest
    expected_target_month = str(
        pd.Period(_ACCEPTED_FEATURE_MONTH, freq="M") + horizon_months
    )
    expected = {
        "runtime_backend": "local_python",
        "suite_version": preflight.suite_version,
        "feature_month": _ACCEPTED_FEATURE_MONTH,
        "target_month": expected_target_month,
        "latest_label_month": _ACCEPTED_LATEST_LABEL_MONTH,
        "horizon_key": horizon_key,
        "horizon_months": horizon_months,
        "partition_sha256": PARTITION_ASSET_SHA256,
        "dependency_versions": preflight.dependency_versions,
        "source_git_commit": preflight.source_git_commit,
    }
    mismatches = [
        name for name, expected_value in expected.items()
        if manifest.get(name) != expected_value
    ]
    source_panel = manifest.get("source_panel")
    if not isinstance(source_panel, Mapping) or {
        key: source_panel.get(key) for key in _panel_content_identity(preflight)
    } != _panel_content_identity(preflight):
        mismatches.append("source_panel")
    normalization_audit = manifest.get("normalization_audit")
    if not isinstance(normalization_audit, Mapping) or {
        key: normalization_audit.get(key)
        for key in _audit_content_identity(preflight)
    } != _audit_content_identity(preflight):
        mismatches.append("normalization_audit")
    if mismatches:
        raise ValueError(
            f"local package {horizon_key} source identities differ: {mismatches}"
        )
    if loaded.predictor.horizon_key != horizon_key:
        raise ValueError(f"local package directory {horizon_key} has wrong horizon")


def _load_package_suite(
    package_root: Path,
    preflight: _PreflightResult,
) -> tuple[dict[str, Path], dict[str, LoadedLocalModelPackage]]:
    if package_root.is_symlink() or not package_root.is_dir():
        raise ValueError("existing model suite must be a regular directory")
    actual_members = {path.name for path in package_root.iterdir()}
    if actual_members != set(_HORIZON_ORDER):
        raise ValueError(
            "existing model suite must contain exactly the 0m, 6m, and 12m "
            f"package directories; observed={sorted(actual_members)}"
        )

    package_dirs: dict[str, Path] = {}
    loaded_packages: dict[str, LoadedLocalModelPackage] = {}
    for horizon_key in _HORIZON_ORDER:
        package_dir = package_root / horizon_key
        loaded = load_local_model_package(
            package_dir,
            expected_suite_version=preflight.suite_version,
            expected_source_git_commit=preflight.source_git_commit,
            expected_panel_sha256=preflight.panel_sha256,
        )
        _validate_loaded_package_identity(loaded, preflight, horizon_key)
        package_dirs[horizon_key] = package_dir
        loaded_packages[horizon_key] = loaded
    return package_dirs, loaded_packages


def _aggregate_training_report(
    suite_version: str,
    loaded_packages: Mapping[str, LoadedLocalModelPackage],
) -> dict[str, object]:
    if list(loaded_packages) != list(_HORIZON_ORDER):
        raise ValueError("loaded packages must preserve HORIZON_MONTHS order")
    reports = {
        key: loaded_packages[key].training_report for key in _HORIZON_ORDER
    }
    training_ranges = {
        json.dumps(report["training_target_month_range"], sort_keys=True)
        for report in reports.values()
    }
    validation_ranges = {
        json.dumps(report["validation_target_month_range"], sort_keys=True)
        for report in reports.values()
    }
    if len(training_ranges) != 1 or len(validation_ranges) != 1:
        raise ValueError("all horizons must use shared training and validation ranges")
    first_report = reports[_HORIZON_ORDER[0]]
    aggregate: dict[str, object] = {
        "schema_version": "fewsnet-training-report-v1",
        "suite_version": suite_version,
        "training_target_month_range": dict(
            first_report["training_target_month_range"]
        ),
        "validation_target_month_range": dict(
            first_report["validation_target_month_range"]
        ),
        "horizon_thresholds": {
            key: dict(loaded_packages[key].threshold_report)
            for key in _HORIZON_ORDER
        },
        "cluster_states": {
            key: reports[key]["cluster_states"] for key in _HORIZON_ORDER
        },
        "smote_results": {
            key: reports[key]["smote_results"] for key in _HORIZON_ORDER
        },
        "fallback_counts": {
            key: reports[key]["fallback_counts"] for key in _HORIZON_ORDER
        },
    }
    validate_payload("training-report", aggregate)
    return aggregate


def _suite_run_manifest(
    preflight: _PreflightResult,
    loaded_packages: Mapping[str, LoadedLocalModelPackage],
    aggregate_report: Mapping[str, object],
    *,
    run_id: str,
    created_at_utc: str,
) -> dict[str, object]:
    return {
        "schema_version": "fewsnet-local-suite-run-manifest-v1",
        "run_id": run_id,
        "suite_version": preflight.suite_version,
        "created_at_utc": created_at_utc,
        "runtime_backend": "local_python",
        "gcp_write_performed": False,
        "source_git_commit": preflight.source_git_commit,
        "dependency_versions": preflight.dependency_versions,
        "panel": _panel_content_identity(preflight),
        "normalization_audit": _audit_content_identity(preflight),
        "feature_contract": {
            "sha256": FEATURE_CONTRACT_FILE_SHA256,
            "feature_schema_sha256": (
                preflight.feature_contract.feature_schema_sha256
            ),
        },
        "partition_asset": {
            "sha256": PARTITION_ASSET_SHA256,
        },
        "latest_feature_month": _ACCEPTED_FEATURE_MONTH,
        "latest_label_month": _ACCEPTED_LATEST_LABEL_MONTH,
        "training_target_month_range": dict(
            aggregate_report["training_target_month_range"]
        ),
        "validation_target_month_range": dict(
            aggregate_report["validation_target_month_range"]
        ),
        "horizons": {
            horizon_key: {
                "horizon_months": loaded_packages[
                    horizon_key
                ].predictor.horizon_months,
                "target_month": loaded_packages[
                    horizon_key
                ].manifest["target_month"],
                "threshold": float(
                    loaded_packages[horizon_key].predictor.threshold
                ),
            }
            for horizon_key in _HORIZON_ORDER
        },
        "model_packages": {
            horizon_key: {
                "relative_path": _package_relative_path(
                    preflight.suite_version,
                    horizon_key,
                ),
                "member_checksums": dict(
                    loaded_packages[horizon_key].checksums
                ),
            }
            for horizon_key in _HORIZON_ORDER
        },
        "status": "validated",
    }


def _validate_existing_reports(
    report_root: Path,
    preflight: _PreflightResult,
    loaded_packages: Mapping[str, LoadedLocalModelPackage],
) -> tuple[dict[str, Path], dict[str, object]]:
    if report_root.is_symlink() or not report_root.is_dir():
        raise ValueError("existing suite reports must be a regular directory")
    actual_members = {path.name for path in report_root.iterdir()}
    expected_members = set(_REPORT_FILENAMES.values())
    if actual_members != expected_members:
        raise ValueError(
            "existing suite reports must contain exactly the training and run "
            f"reports; observed={sorted(actual_members)}"
        )

    aggregate_report = _aggregate_training_report(
        preflight.suite_version,
        loaded_packages,
    )
    training_report_path = report_root / _REPORT_FILENAMES[
        "training_threshold_report"
    ]
    observed_training_report = _read_json_object(
        training_report_path,
        "training_threshold_report.json",
    )
    validate_payload("training-report", observed_training_report)
    if observed_training_report != aggregate_report:
        raise ValueError(
            "existing training_threshold_report.json does not match packages"
        )

    run_manifest_path = report_root / _REPORT_FILENAMES["run_manifest"]
    observed_manifest = _read_json_object(
        run_manifest_path,
        "run_manifest.json",
    )
    if set(observed_manifest) != _RUN_MANIFEST_FIELDS:
        raise ValueError("existing run_manifest.json fields differ")
    if _RUN_ID_PATTERN.fullmatch(str(observed_manifest["run_id"])) is None:
        raise ValueError("existing run_manifest.json has an invalid run_id")
    created_at_utc = str(observed_manifest["created_at_utc"])
    _parse_utc(created_at_utc, "created_at_utc")
    if observed_manifest["run_id"] != _run_id(
        _ACCEPTED_FEATURE_MONTH,
        created_at_utc,
    ):
        raise ValueError(
            "existing run_manifest.json run_id does not match feature month "
            "and created_at_utc"
        )
    expected_manifest = _suite_run_manifest(
        preflight,
        loaded_packages,
        aggregate_report,
        run_id=str(observed_manifest["run_id"]),
        created_at_utc=created_at_utc,
    )
    if observed_manifest != expected_manifest:
        raise ValueError("existing run_manifest.json does not match packages")
    return {
        "training_threshold_report": training_report_path,
        "run_manifest": run_manifest_path,
    }, aggregate_report


def _write_new_reports(
    report_root: Path,
    preflight: _PreflightResult,
    loaded_packages: Mapping[str, LoadedLocalModelPackage],
) -> tuple[dict[str, Path], dict[str, object]]:
    aggregate_report = _aggregate_training_report(
        preflight.suite_version,
        loaded_packages,
    )
    training_report_path = report_root / _REPORT_FILENAMES[
        "training_threshold_report"
    ]
    run_manifest_path = report_root / _REPORT_FILENAMES["run_manifest"]
    _write_json(training_report_path, aggregate_report)
    manifest = _suite_run_manifest(
        preflight,
        loaded_packages,
        aggregate_report,
        run_id=preflight.run_id,
        created_at_utc=preflight.started_at_utc,
    )
    _write_json(run_manifest_path, manifest)
    return {
        "training_threshold_report": training_report_path,
        "run_manifest": run_manifest_path,
    }, aggregate_report


def _local_package_metadata(
    preflight: _PreflightResult,
    target_month: str,
) -> LocalPackageMetadata:
    return LocalPackageMetadata(
        suite_version=preflight.suite_version,
        feature_month=_ACCEPTED_FEATURE_MONTH,
        target_month=target_month,
        latest_label_month=_ACCEPTED_LATEST_LABEL_MONTH,
        source_git_commit=preflight.source_git_commit,
        panel_path=str(preflight.panel_path),
        panel_sha256=preflight.panel_sha256,
        panel_size_bytes=preflight.panel_size_bytes,
        panel_row_count=preflight.panel_row_count,
        normalization_audit_path=str(preflight.audit_path),
        normalization_audit_sha256=preflight.audit_sha256,
        normalization_audit_size_bytes=preflight.audit_size_bytes,
    )


def _train_new_package_suite(
    package_root: Path,
    preflight: _PreflightResult,
    feature_frame: pd.DataFrame,
) -> tuple[dict[str, Path], dict[str, LoadedLocalModelPackage]]:
    package_dirs: dict[str, Path] = {}
    loaded_packages: dict[str, LoadedLocalModelPackage] = {}
    for horizon_months in HORIZON_MONTHS:
        horizon_key = HORIZON_KEYS[horizon_months]
        aligned = align_horizon(feature_frame, horizon_months).frame
        training_frame = select_training_window(
            aligned,
            _ACCEPTED_LATEST_LABEL_MONTH,
            months=TRAIN_WINDOW_MONTHS,
        )
        training_result = train_horizon_model(
            training_frame,
            preflight.feature_contract,
            preflight.partition_map,
            horizon_key,
        )
        target_month = str(
            pd.Period(_ACCEPTED_FEATURE_MONTH, freq="M") + horizon_months
        )
        package_dir = package_root / horizon_key
        write_local_model_package(
            package_dir,
            training_result.predictor,
            _local_package_metadata(preflight, target_month),
            {
                "training_report": training_result.training_report,
                "threshold_report": training_result.threshold_report,
            },
        )
        loaded = load_local_model_package(
            package_dir,
            expected_suite_version=preflight.suite_version,
            expected_source_git_commit=preflight.source_git_commit,
            expected_panel_sha256=preflight.panel_sha256,
        )
        _validate_loaded_package_identity(loaded, preflight, horizon_key)
        package_dirs[horizon_key] = package_dir
        loaded_packages[horizon_key] = loaded
    return package_dirs, loaded_packages


def _resolve_or_train_suite(
    staging_root: Path,
    preflight: _PreflightResult,
    feature_frame: pd.DataFrame,
) -> tuple[
    bool,
    dict[str, Path],
    dict[str, LoadedLocalModelPackage],
    dict[str, Path],
    dict[str, object],
]:
    final_package_root = (
        preflight.output_root / "model_artifacts" / preflight.suite_version
    )
    final_report_root = (
        preflight.output_root / "reports" / preflight.suite_version
    )
    if final_package_root.exists() or final_report_root.exists():
        package_dirs, loaded_packages = _load_package_suite(
            final_package_root,
            preflight,
        )
        report_files, aggregate_report = _validate_existing_reports(
            final_report_root,
            preflight,
            loaded_packages,
        )
        return (
            True,
            package_dirs,
            loaded_packages,
            report_files,
            aggregate_report,
        )

    package_root = (
        staging_root / "model_artifacts" / preflight.suite_version
    )
    package_dirs, loaded_packages = _train_new_package_suite(
        package_root,
        preflight,
        feature_frame,
    )
    report_root = staging_root / "reports" / preflight.suite_version
    report_files, aggregate_report = _write_new_reports(
        report_root,
        preflight,
        loaded_packages,
    )
    return (
        False,
        package_dirs,
        loaded_packages,
        report_files,
        aggregate_report,
    )


def _population_payload(summary: PopulationSummary) -> dict[str, object]:
    return {
        "raw_last_observed_count": summary.raw_last_observed_count,
        "missing_raw_count": summary.missing_raw_count,
        "missing_admin_codes": list(summary.missing_admin_codes),
        "reference_period_counts": dict(summary.reference_period_counts),
    }


def _file_reference(path: Path, relative_path: str) -> dict[str, object]:
    return {
        "relative_path": relative_path,
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _run_summary(
    preflight: _PreflightResult,
    population_summary: PopulationSummary,
    loaded_packages: Mapping[str, LoadedLocalModelPackage],
    aggregate_report: Mapping[str, object],
    suite_validation: Mapping[str, object],
    prediction_metadata: Mapping[str, Mapping[str, object]],
    report_files: Mapping[str, Path],
) -> dict[str, object]:
    model_packages = {
        horizon_key: {
            "relative_path": _package_relative_path(
                preflight.suite_version,
                horizon_key,
            ),
            "member_checksums": dict(loaded_packages[horizon_key].checksums),
        }
        for horizon_key in _HORIZON_ORDER
    }
    horizons: dict[str, object] = {}
    horizon_summaries = suite_validation["horizon_summaries"]
    target_months = suite_validation["target_months"]
    for horizon_key in _HORIZON_ORDER:
        metrics = horizon_summaries[horizon_key]
        prediction = prediction_metadata[horizon_key]
        horizons[horizon_key] = {
            "horizon_months": loaded_packages[
                horizon_key
            ].predictor.horizon_months,
            "target_month": target_months[horizon_key],
            "threshold": metrics["threshold"],
            "row_count": metrics["row_count"],
            "positive_label_count": metrics["positive_label_count"],
            "probability_min": metrics["probability_min"],
            "probability_max": metrics["probability_max"],
            "probability_mean": metrics["probability_mean"],
            "fallback_counts": metrics["fallback_counts"],
            "model_package": model_packages[horizon_key],
            "prediction": {
                "relative_path": _prediction_relative_path(horizon_key),
                "sha256": prediction["sha256"],
                "size_bytes": prediction["size_bytes"],
                "row_count": prediction["row_count"],
            },
        }

    reports = {
        report_key: _file_reference(
            report_files[report_key],
            _report_relative_path(preflight.suite_version, report_key),
        )
        for report_key in _REPORT_FILENAMES
    }
    return {
        "schema_version": "fewsnet-local-run-summary-v1",
        "run_id": preflight.run_id,
        "suite_version": preflight.suite_version,
        "started_at_utc": preflight.started_at_utc,
        "completed_at_utc": utc_now(),
        "status": "passed",
        "runtime_backend": "local_python",
        "gcp_write_performed": False,
        "source_git_commit": preflight.source_git_commit,
        "dependency_versions": preflight.dependency_versions,
        "panel": _panel_identity(preflight),
        "normalization_audit": _audit_identity(preflight),
        "latest_feature_month": _ACCEPTED_FEATURE_MONTH,
        "latest_label_month": _ACCEPTED_LATEST_LABEL_MONTH,
        "training_target_month_range": dict(
            aggregate_report["training_target_month_range"]
        ),
        "validation_target_month_range": dict(
            aggregate_report["validation_target_month_range"]
        ),
        "population": _population_payload(population_summary),
        "horizons": horizons,
        "model_packages": model_packages,
        "reports": reports,
    }


def build_staged_local_experiment(
    config: LocalExperimentConfig,
    staging_root: str | Path,
) -> StagedLocalExperiment:
    """Train or reuse, reload, predict, validate, and stage one local suite."""
    preflight = _preflight(config)
    staged_root = _prepare_staging_root(staging_root, preflight.output_root)

    panel = pd.read_csv(
        preflight.panel_path,
        dtype={ADMIN_SOURCE_COLUMN: "string"},
        low_memory=False,
    )
    _verify_preflight_inputs_unchanged(preflight)
    feature_frame = Stage3FeatureBuilder().transform(
        panel,
        preflight.feature_contract,
    )
    identity_population, population_summary = build_identity_population_frame(
        panel,
        _ACCEPTED_FEATURE_MONTH,
    )

    (
        reused_model_suite,
        package_dirs,
        loaded_packages,
        report_files,
        aggregate_report,
    ) = _resolve_or_train_suite(
        staged_root,
        preflight,
        feature_frame,
    )

    predictions: dict[str, pd.DataFrame] = {}
    for horizon_months in HORIZON_MONTHS:
        horizon_key = HORIZON_KEYS[horizon_months]
        inference_frame = select_latest_inference_frame(
            feature_frame,
            _ACCEPTED_FEATURE_MONTH,
            horizon_months,
        )
        formal_predictions = loaded_packages[
            horizon_key
        ].predictor.predict_frame(inference_frame)
        predictions[horizon_key] = enrich_local_predictions(
            formal_predictions,
            identity_population,
            model_artifact_path=_package_relative_path(
                preflight.suite_version,
                horizon_key,
            ),
            source_input=str(preflight.panel_path),
        )

    suite_validation = validate_local_prediction_suite(
        predictions,
        expected_admin_codes=tuple(preflight.panel_info["admin_codes"]),
        feature_month=_ACCEPTED_FEATURE_MONTH,
        suite_version=preflight.suite_version,
    )

    prediction_files: dict[str, Path] = {}
    prediction_metadata: dict[str, dict[str, object]] = {}
    for horizon_key in _HORIZON_ORDER:
        prediction_path = staged_root / _prediction_relative_path(horizon_key)
        metadata = write_local_prediction_csv(
            predictions[horizon_key],
            prediction_path,
        )
        prediction_files[horizon_key] = prediction_path
        prediction_metadata[horizon_key] = metadata

    run_summary_path = staged_root / "predictions/202604/run_summary.json"
    summary = _run_summary(
        preflight,
        population_summary,
        loaded_packages,
        aggregate_report,
        suite_validation,
        prediction_metadata,
        report_files,
    )
    _write_json(run_summary_path, summary)
    return StagedLocalExperiment(
        run_id=preflight.run_id,
        suite_version=preflight.suite_version,
        panel_sha256=preflight.panel_sha256,
        source_git_commit=preflight.source_git_commit,
        staging_root=staged_root,
        reused_model_suite=reused_model_suite,
        package_dirs=package_dirs,
        prediction_files=prediction_files,
        report_files=report_files,
        run_summary_path=run_summary_path,
    )
