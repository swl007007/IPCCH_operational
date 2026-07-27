# FEWSNET Local 202604 Prediction Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a truthful local-only execution path around the existing `fewsnet_partitioned_rf_pipeline` core that trains or safely reuses 0m, 6m, and 12m Random Forest packages, predicts the full `2026-04` FEWSNET area universe, and publishes three probability CSVs plus reloadable local model artifacts under `Outcome/fewsnet_partitioned_rf/`.

**Architecture:** Add an isolated `fewsnet_partitioned_rf_pipeline.local` adapter without changing the existing feature, horizon, partition, training, inference, Vertex, or production model-package mathematics. A staged local engine validates the normalized panel and audit, records a clean Git/runtime identity, trains and reloads one truthful local package per horizon, enriches predictions with raw last-observed population, validates the three scopes together, and then an ownership-claimed publisher makes accepted files visible with `run_summary.json` last.

**Tech Stack:** Python 3.12, pandas 3.0.0, NumPy 2.4.2, scikit-learn 1.8.0, joblib 1.5.3, imbalanced-learn 0.14.0, JSON Schema Draft 2020-12, pytest 9.1.1, existing FEWSNET Stage 3/core APIs, local filesystem only.

## Global Constraints

- The authoritative design is `docs/superpowers/specs/2026-07-26-fewsnet-local-202604-prediction-experiment-design.md`, committed at `179c8348121e5c9e5ac77e43860662d89dee44be`, with SHA-256 `b91c81d15b53233d5e8cf958ac1702db6b17fed4f452c54d75f9ada3168374c9`.
- At execution start, use `superpowers:using-git-worktrees`, create an isolated feature branch/worktree, and reconcile repository-local `PROGRESS.md` before editing code.
- Preserve the completed FEWSNET cloud/model-suite history already recorded in `PROGRESS.md`; add a new active-feature section rather than erasing prior acceptance evidence.
- `PROGRESS.md` is an execution ledger, not approval authority. Record each task's RED/GREEN commands, focused regression result, commit hash, blockers, exact next task, and resume command.
- Use the existing pinned dependency file `requirements-fewsnet-partitioned-rf.txt`; do not add a second dependency stack for the local path.
- Use `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` for every pytest command.
- Prefer new files under `fewsnet_partitioned_rf_pipeline/local/`. Do not modify existing core model behavior unless a separately verified defect makes that necessary.
- Before modifying any existing function, class, or method, run GitNexus upstream impact analysis and report direct callers, affected processes, and risk. Stop and warn before any HIGH or CRITICAL edit.
- Before every commit, run GitNexus `detect_changes(scope="staged", repo="IPCCH_operational")`; also inspect `git diff --cached --stat` and `git diff --cached --check`.
- The approved normalized input is `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv` with SHA-256 `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`, 1,120,728 rows, 88 columns, and matching `.audit.json`.
- The accepted feature month is exactly `2026-04`; the latest labeled target month is `2026-02`; the authoritative area universe is exactly 5,718 unique normalized `FEWSNET_admin_code` values.
- Horizon semantics are exact keyed calendar alignment: `0m -> 2026-04`, `6m -> 2026-10`, and `12m -> 2027-04`.
- Reuse the frozen feature contract at `fewsnet_partitioned_rf_pipeline/assets/feature_contracts/fewsnet_stage3_v1.json`, SHA-256 `3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b`.
- Reuse the fixed partition asset at `fewsnet_partitioned_rf_pipeline/assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv`, SHA-256 `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b`.
- Reuse `Stage3FeatureBuilder`, `align_horizon`, `select_training_window`, `select_latest_inference_frame`, `train_horizon_model`, and `PartitionedRFPredictor.predict_frame`; do not duplicate RF, SMOTE, imputation, threshold, or routing mathematics.
- The local package schema is `fewsnet-local-model-package-v1`; production `fewsnet-model-package-v1` and its digest-pinned container requirements remain unchanged.
- Local predictors must retain blank `vertex_model_resource_name` and `vertex_model_version_id`; never fabricate GCS URIs, Vertex resources, model version IDs, or container identities.
- The delivered continuous value is `probability_crisis` in `[0, 1]`; the retained binary label is exactly `int(probability_crisis >= threshold)`.
- Do not produce `phaseX_worse_*`, categorical uncertainty, decision-margin uncertainty, maps, workbooks, or future-target performance claims.
- Population is output enrichment only. Select the latest non-null raw `pop` at or before the feature month; do not use `MaxPlusImputer` or any other statistical/spatial fill for delivered population.
- The real accepted result must contain 5,716 `raw_last_observed` population rows and two `missing_raw` rows; record the two missing administrative codes in `run_summary.json`.
- The final root is `Outcome/fewsnet_partitioned_rf/`, independent of `Outcome/ipcch_unified/`. No local experiment operation may read, write, rename, remove, or overwrite `Outcome/ipcch_unified/` artifacts.
- Model package directories are versioned and create-only. An existing deterministic suite is reusable only after all three packages and existing suite reports validate against the same suite, source commit, panel digest, member inventory, checksums, dependency versions, feature contract, partition asset, and reports.
- Prediction files refuse overwrite by default. `--overwrite` applies only to the exact supplied FEWSNET output root and never grants authority over IPCCH paths.
- Publication remains WSL/Dropbox-safe, but create-only mode uses exclusive file creation and atomically claimed suite roots. `shutil.copy2` is limited to explicit overwrite of a target that is still a validated regular file. Remove an existing accepted `run_summary.json` only after explicit `--overwrite`, publish and verify the three CSVs, stamp completion, then publish the new passed summary last.
- A failed run may leave temporary staging evidence, but it must not leave a passed final summary or a partial final suite that can be mistaken for accepted output.
- The full real-source acceptance run must use the complete normalized panel and frozen RF parameters. Sampling is allowed only in checked-in tests.
- No GCP, GCS, Vertex AI Custom Job, Model Registry, Batch Prediction, alias, production pointer, or network mutation is part of this plan.
- Each implementation task follows RED -> GREEN -> focused regression -> GitNexus staged change detection -> one focused commit.

---

## File Structure

### New local adapter files

- `fewsnet_partitioned_rf_pipeline/local/__init__.py` — stable exports for the local runner and package loader.
- `fewsnet_partitioned_rf_pipeline/local/package.py` — local-only package metadata, seven-file writer, defensive loader, checksums, and pre-unpickle validation.
- `fewsnet_partitioned_rf_pipeline/local/outputs.py` — identity/population enrichment, exact local prediction columns, record/suite validation, and deterministic CSV writing.
- `fewsnet_partitioned_rf_pipeline/local/runner.py` — preflight, deterministic suite identity, three-horizon staging, existing-suite reuse, publication, and final result payload.
- `fewsnet_partitioned_rf_pipeline/cli/run_local_experiment.py` — argparse entrypoint that invokes the runner and prints one JSON result.

### New schemas

- `fewsnet_partitioned_rf_pipeline/schemas/local-model-package.schema.json` — truthful local package manifest contract.
- `fewsnet_partitioned_rf_pipeline/schemas/local-prediction-record.schema.json` — exact per-row local prediction contract.

### New tests

- `tests/fewsnet_partitioned_rf/local_test_support.py` — deterministic synthetic predictor, valid reports, normalized panel/audit fixture, and expected local rows.
- `tests/fewsnet_partitioned_rf/test_local_package.py` — package schema, inventory, checksum, dependency, source identity, and round-trip tests.
- `tests/fewsnet_partitioned_rf/test_local_outputs.py` — population provenance, output columns, probability/threshold, and cross-scope tests.
- `tests/fewsnet_partitioned_rf/test_local_runner.py` — small true three-horizon train/package/reload/predict integration and publication failure tests.
- `tests/fewsnet_partitioned_rf/test_local_cli.py` — CLI argument, JSON success, nonzero failure, overwrite forwarding, and no-Vertex tests.

### Modified repository files

- `PROGRESS.md` — active execution state and final real-source evidence while preserving prior feature history.
- `.gitignore` — ignore the complete `Outcome/fewsnet_partitioned_rf/` generated tree.
- `docs/09_fewsnet_partitioned_rf_runbook.md` — local experiment setup, command, artifact meanings, validation, rerun, and recovery.
- `docs/04_output_inventory.md` — list the new independent FEWSNET local artifacts and explicitly distinguish them from IPCCH and cloud outputs.

---

### Task 1: Add the Truthful Local Model Package Contract

**Files:**

- Create: `fewsnet_partitioned_rf_pipeline/local/__init__.py`
- Create: `fewsnet_partitioned_rf_pipeline/local/package.py`
- Create: `fewsnet_partitioned_rf_pipeline/schemas/local-model-package.schema.json`
- Create: `tests/fewsnet_partitioned_rf/local_test_support.py`
- Create: `tests/fewsnet_partitioned_rf/test_local_package.py`
- Modify: `PROGRESS.md`

**Interfaces:**

- Produces `LOCAL_PACKAGE_FILES`, exactly `model.joblib`, `feature_contract.json`, `partition_map.csv`, `threshold_report.json`, `training_report.json`, `local_model_manifest.json`, and `checksums.json`.
- Produces `LocalPackageMetadata` with exact source, suite, month, and Git identities.
- Produces `LoadedLocalModelPackage` containing the validated predictor, manifest, reports, and checksums.
- Produces `write_local_model_package(output_dir, predictor, metadata, reports) -> dict[str, object]`.
- Produces `load_local_model_package(package_dir, *, expected_suite_version=None, expected_source_git_commit=None, expected_panel_sha256=None) -> LoadedLocalModelPackage`.
- Consumes existing public validators `runtime_dependency_versions`, `assert_runtime_compatible`, `validate_horizon_training_report`, `validate_threshold_report`, `load_feature_contract`, and `PartitionMap.load`.

- [ ] **Step 1: Create the isolated execution environment and reconcile the ledger**

From the isolated implementation worktree, create the ignored virtual environment and install the already approved pins:

```bash
uv venv --python 3.12 .venv
UV_CACHE_DIR=/tmp/ipcch-fewsnet-uv-cache \
  uv pip install --python .venv/bin/python \
  -r requirements-fewsnet-partitioned-rf.txt
```

Expected runtime acceptance:

- The exact approved pins remain authoritative, including `scikit-learn==1.8.0` and `imbalanced-learn==0.14.0`; do not change dependency pins.
- `UV_CACHE_DIR=/tmp/ipcch-fewsnet-uv-cache uv pip check --python .venv/bin/python` passes.
- `.venv/bin/python -c 'import fewsnet_partitioned_rf_pipeline.core.training as training; smote = training._load_smote_type(); print(smote.__module__, smote.__name__)'` imports the reviewed project path and returns the real `imblearn` `SMOTE` through the existing temporary compatibility bridge.
- Bare `import imblearn` is not an acceptance condition for this pinned pair; do not change the already reviewed bridge in `core.training`.
- No tracked dependency file changes.

Update `PROGRESS.md` with a new top-level active feature section containing:

```markdown
## Active Feature: FEWSNET Local 202604 Prediction Experiment

- Approved design: `docs/superpowers/specs/2026-07-26-fewsnet-local-202604-prediction-experiment-design.md`
- Implementation plan: `docs/superpowers/plans/2026-07-26-fewsnet-local-202604-prediction-experiment.md`
- Design commit: `179c8348121e5c9e5ac77e43860662d89dee44be`
- Design SHA-256: `b91c81d15b53233d5e8cf958ac1702db6b17fed4f452c54d75f9ada3168374c9`
- Branch/worktree: record the actual feature branch and absolute worktree path
- Current task: Task 1 in progress
- Cloud mutation status: none authorized or attempted
- Output mutation status: no `Outcome/fewsnet_partitioned_rf/` artifacts published yet

| Task | Status |
| --- | --- |
| 1. Truthful local model package | in progress |
| 2. Population and prediction output contract | pending |
| 3. Three-horizon staged engine | pending |
| 4. Publication, CLI, docs, and ignore rule | pending |
| 5. Full 2026-04 acceptance run | pending |
```

Preserve the previous completed FEWSNET partitioned-RF suite section below this active section.

- [ ] **Step 2: Write the failing local-package tests and shared predictor fixture**

Create `tests/fewsnet_partitioned_rf/local_test_support.py` with these stable helper interfaces:

```python
from fewsnet_partitioned_rf_pipeline.core.inference import PartitionedRFPredictor
from fewsnet_partitioned_rf_pipeline.local.package import LocalPackageMetadata


def build_package_fixture() -> tuple[
    PartitionedRFPredictor,
    LocalPackageMetadata,
    dict[str, object],
]:
    """Return a valid predictor, local metadata, and validated reports."""
```

`build_package_fixture()` must load the real frozen feature contract and partition asset, fit a deterministic two-class `RandomForestClassifier` over a finite matrix with one column per frozen feature, fit `MaxPlusImputer`, set every approved cluster to a valid pooled fallback state, leave both Vertex identity fields blank, and return reports accepted by the existing horizon-report validators.

Create `tests/fewsnet_partitioned_rf/test_local_package.py` with the core RED cases:

```python
import json

import pytest

from fewsnet_partitioned_rf_pipeline.local.package import (
    LOCAL_PACKAGE_FILES,
    load_local_model_package,
    write_local_model_package,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from tests.fewsnet_partitioned_rf.local_test_support import build_package_fixture


def test_local_model_package_schema_rejects_vertex_identity():
    payload = {
        "schema_version": "fewsnet-local-model-package-v1",
        "runtime_backend": "local_python",
        "suite_version": "local-202604-111111111111-222222222222",
        "feature_month": "2026-04",
        "target_month": "2026-04",
        "latest_label_month": "2026-02",
        "horizon_key": "0m",
        "horizon_months": 0,
        "source_panel": {
            "path": "/tmp/panel.csv",
            "sha256": "2" * 64,
            "size_bytes": 10,
            "row_count": 20,
        },
        "normalization_audit": {
            "path": "/tmp/panel.audit.json",
            "sha256": "3" * 64,
            "size_bytes": 11,
        },
        "feature_schema_sha256": "4" * 64,
        "partition_sha256": "5" * 64,
        "threshold": 0.51,
        "dependency_versions": {
            "python": "3.12.3",
            "numpy": "2.4.2",
            "pandas": "3.0.0",
            "scikit-learn": "1.8.0",
            "joblib": "1.5.3",
            "imbalanced-learn": "0.14.0",
        },
        "source_git_commit": "1" * 40,
        "training_target_month_range": {"start": "2023-03", "end": "2026-02"},
        "validation_target_month_range": {"start": "2025-09", "end": "2026-02"},
        "files": list(LOCAL_PACKAGE_FILES),
        "status": "validated",
        "vertex_model_resource_name": "projects/fake/models/fake",
    }
    with pytest.raises(ValueError, match="Additional properties"):
        validate_payload("local-model-package", payload)


def test_local_model_package_round_trip_validates_before_unpickling(tmp_path):
    predictor, metadata, reports = build_package_fixture()
    package_dir = tmp_path / "0m"

    manifest = write_local_model_package(
        package_dir,
        predictor,
        metadata,
        reports,
    )
    loaded = load_local_model_package(
        package_dir,
        expected_suite_version=metadata.suite_version,
        expected_source_git_commit=metadata.source_git_commit,
        expected_panel_sha256=metadata.panel_sha256,
    )

    assert tuple(sorted(path.name for path in package_dir.iterdir())) == tuple(
        sorted(LOCAL_PACKAGE_FILES)
    )
    assert manifest["runtime_backend"] == "local_python"
    assert loaded.manifest == manifest
    assert loaded.predictor.suite_version == metadata.suite_version
    assert loaded.predictor.vertex_model_resource_name == ""
    assert loaded.predictor.vertex_model_version_id == ""
    assert loaded.training_report == reports["training_report"]
    assert loaded.threshold_report == reports["threshold_report"]


def test_local_model_package_rejects_checksum_drift_before_joblib_load(
    tmp_path,
    monkeypatch,
):
    predictor, metadata, reports = build_package_fixture()
    package_dir = tmp_path / "0m"
    write_local_model_package(package_dir, predictor, metadata, reports)
    (package_dir / "training_report.json").write_text("{}\n", encoding="utf-8")

    called = False

    def forbidden_joblib_load(path):
        nonlocal called
        called = True
        raise AssertionError(path)

    monkeypatch.setattr("fewsnet_partitioned_rf_pipeline.local.package.joblib.load", forbidden_joblib_load)
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_local_model_package(package_dir)
    assert called is False


def test_local_model_package_rejects_runtime_and_source_identity_drift(tmp_path):
    predictor, metadata, reports = build_package_fixture()
    package_dir = tmp_path / "0m"
    write_local_model_package(package_dir, predictor, metadata, reports)

    with pytest.raises(ValueError, match="source Git commit"):
        load_local_model_package(
            package_dir,
            expected_source_git_commit="f" * 40,
        )
    with pytest.raises(ValueError, match="panel SHA-256"):
        load_local_model_package(
            package_dir,
            expected_panel_sha256="e" * 64,
        )
```

- [ ] **Step 3: Run the package tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_package.py \
  -q -p no:cacheprovider
```

Expected: collection fails because `fewsnet_partitioned_rf_pipeline.local.package` and `local-model-package.schema.json` do not exist.

- [ ] **Step 4: Add the local manifest schema and package dataclasses**

Create `fewsnet_partitioned_rf_pipeline/schemas/local-model-package.schema.json` as a Draft 2020-12 object with `additionalProperties: false` and these exact required fields:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "FEWSNET Local Model Package",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "runtime_backend",
    "suite_version",
    "feature_month",
    "target_month",
    "latest_label_month",
    "horizon_key",
    "horizon_months",
    "source_panel",
    "normalization_audit",
    "feature_schema_sha256",
    "partition_sha256",
    "threshold",
    "dependency_versions",
    "source_git_commit",
    "training_target_month_range",
    "validation_target_month_range",
    "files",
    "status"
  ],
  "properties": {
    "schema_version": {"const": "fewsnet-local-model-package-v1"},
    "runtime_backend": {"const": "local_python"},
    "suite_version": {"type": "string", "pattern": "^local-[0-9]{6}-[0-9a-f]{12}-[0-9a-f]{12}$"},
    "feature_month": {"type": "string", "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$"},
    "target_month": {"type": "string", "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$"},
    "latest_label_month": {"type": "string", "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$"},
    "horizon_key": {"enum": ["0m", "6m", "12m"]},
    "horizon_months": {"enum": [0, 6, 12]},
    "source_panel": {"$ref": "#/$defs/panelRef"},
    "normalization_audit": {"$ref": "#/$defs/fileRef"},
    "feature_schema_sha256": {"$ref": "#/$defs/sha256"},
    "partition_sha256": {"$ref": "#/$defs/sha256"},
    "threshold": {"type": "number", "minimum": 0, "maximum": 1},
    "dependency_versions": {
      "type": "object",
      "additionalProperties": false,
      "required": ["python", "numpy", "pandas", "scikit-learn", "joblib", "imbalanced-learn"],
      "properties": {
        "python": {"type": "string", "minLength": 1},
        "numpy": {"type": "string", "minLength": 1},
        "pandas": {"type": "string", "minLength": 1},
        "scikit-learn": {"type": "string", "minLength": 1},
        "joblib": {"type": "string", "minLength": 1},
        "imbalanced-learn": {"type": "string", "minLength": 1}
      }
    },
    "source_git_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    "training_target_month_range": {"$ref": "#/$defs/monthRange"},
    "validation_target_month_range": {"$ref": "#/$defs/monthRange"},
    "files": {
      "type": "array",
      "uniqueItems": true,
      "minItems": 7,
      "maxItems": 7,
      "items": {
        "enum": [
          "model.joblib",
          "feature_contract.json",
          "partition_map.csv",
          "threshold_report.json",
          "training_report.json",
          "local_model_manifest.json",
          "checksums.json"
        ]
      }
    },
    "status": {"const": "validated"}
  },
  "$defs": {
    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "fileRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["path", "sha256", "size_bytes"],
      "properties": {
        "path": {"type": "string", "minLength": 1},
        "sha256": {"$ref": "#/$defs/sha256"},
        "size_bytes": {"type": "integer", "minimum": 1}
      }
    },
    "panelRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["path", "sha256", "size_bytes", "row_count"],
      "properties": {
        "path": {"type": "string", "minLength": 1},
        "sha256": {"$ref": "#/$defs/sha256"},
        "size_bytes": {"type": "integer", "minimum": 1},
        "row_count": {"type": "integer", "minimum": 1}
      }
    },
    "monthRange": {
      "type": "object",
      "additionalProperties": false,
      "required": ["start", "end"],
      "properties": {
        "start": {"type": "string", "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$"},
        "end": {"type": "string", "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$"}
      }
    }
  }
}
```

Create these exact public types in `local/package.py`:

```python
@dataclass(frozen=True)
class LocalPackageMetadata:
    suite_version: str
    feature_month: str
    target_month: str
    latest_label_month: str
    source_git_commit: str
    panel_path: str
    panel_sha256: str
    panel_size_bytes: int
    panel_row_count: int
    normalization_audit_path: str
    normalization_audit_sha256: str
    normalization_audit_size_bytes: int


@dataclass(frozen=True)
class LoadedLocalModelPackage:
    predictor: PartitionedRFPredictor
    manifest: dict[str, object]
    training_report: dict[str, object]
    threshold_report: dict[str, object]
    checksums: dict[str, str]
```

- [ ] **Step 5: Implement defensive write/load behavior**

Implement `write_local_model_package` so it:

1. Requires a `PartitionedRFPredictor`, `LocalPackageMetadata`, and a mapping with exactly `training_report` and `threshold_report`.
2. Requires blank Vertex fields.
3. Validates reports with the existing public validators and cross-checks horizon, feature schema, partition digest, threshold, and target-month ranges.
4. Validates the predictor's partition mapping against the checksum-validated approved partition asset.
5. Refuses a non-empty output directory.
6. Uses `dataclasses.replace` to bind the deterministic `suite_version` before `joblib.dump`.
7. Writes the six content files, computes SHA-256 for each content member, then writes `checksums.json` last.
8. Validates the local manifest through `validate_payload("local-model-package", manifest)` before writing it.

Implement `load_local_model_package` so it validates, in this order, before unpickling:

```text
directory type -> exact seven regular non-symlink files -> checksums.json fields
-> every content checksum -> local manifest schema -> expected identities
-> feature contract -> approved partition bytes and mapping -> reports
-> runtime dependency compatibility -> model.joblib type and predictor invariants
```

The final predictor invariants are exact horizon, suite, threshold, feature contract, partition map, partition statuses, and blank Vertex fields.

Create `local/__init__.py` with only stable exports:

```python
from fewsnet_partitioned_rf_pipeline.local.package import (
    LoadedLocalModelPackage,
    LocalPackageMetadata,
    load_local_model_package,
    write_local_model_package,
)

__all__ = [
    "LoadedLocalModelPackage",
    "LocalPackageMetadata",
    "load_local_model_package",
    "write_local_model_package",
]
```

- [ ] **Step 6: Run GREEN and focused regression**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_package.py \
  tests/fewsnet_partitioned_rf/test_model_package.py \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  -q -p no:cacheprovider
```

Expected: PASS; production model-package tests remain unchanged and green.

- [ ] **Step 7: Record evidence, detect staged impact, and commit Task 1**

Update `PROGRESS.md` with RED/GREEN commands and set Task 1 to `component-complete`, Task 2 to `in progress`.

Stage only Task 1 files, run GitNexus staged `detect_changes`, then:

```bash
git diff --cached --check
git commit -m "feat: add FEWSNET local model package"
```

---

### Task 2: Add Population Enrichment and the Exact Local Prediction Contract

**Files:**

- Create: `fewsnet_partitioned_rf_pipeline/local/outputs.py`
- Create: `fewsnet_partitioned_rf_pipeline/schemas/local-prediction-record.schema.json`
- Create: `tests/fewsnet_partitioned_rf/test_local_outputs.py`
- Modify: `PROGRESS.md`

**Interfaces:**

- Produces `LOCAL_PREDICTION_COLUMNS`, the exact approved 22-column order.
- Produces `PopulationSummary` with provenance counts, reference-period counts, and missing admin codes.
- Produces `build_identity_population_frame(panel, feature_month) -> tuple[pd.DataFrame, PopulationSummary]`.
- Produces `enrich_local_predictions(formal_predictions, identity_population, *, model_artifact_path, source_input) -> pd.DataFrame`.
- Produces `validate_local_prediction_frame(frame, *, expected_admin_codes, feature_month, target_month, horizon_months, suite_version) -> dict[str, object]`.
- Produces `validate_local_prediction_suite(predictions, *, expected_admin_codes, feature_month, suite_version) -> dict[str, object]`.
- Produces `write_local_prediction_csv(frame, path) -> dict[str, object]`.

- [ ] **Step 1: Write failing population and output-contract tests**

Create tests that use a raw panel with four areas, where two have population observed through `2024-10` and two never have a non-null population:

```python
import numpy as np
import pandas as pd
import pytest

from fewsnet_partitioned_rf_pipeline.local.outputs import (
    LOCAL_PREDICTION_COLUMNS,
    build_identity_population_frame,
    enrich_local_predictions,
    validate_local_prediction_frame,
    validate_local_prediction_suite,
)


SUITE_VERSION = "local-202604-111111111111-222222222222"


def population_panel_fixture() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for area_index, admin_code in enumerate(("0", "1", "2", "3")):
        for period in pd.PeriodIndex(("2024-09", "2024-10", "2026-04"), freq="M"):
            rows.append(
                {
                    "FEWSNET_admin_code": admin_code,
                    "ADMIN0": f"country-{area_index // 2}",
                    "ADMIN1": f"admin1-{area_index // 2}",
                    "ADMIN2": f"admin2-{area_index}",
                    "ADMIN3": f"admin3-{area_index}",
                    "ISO3": "SSD",
                    "lat": 5.0 + area_index,
                    "lon": 25.0 + area_index,
                    "date": period.to_timestamp().strftime("%Y-%m-%d"),
                    "pop": (
                        float(1000 + area_index * 100)
                        if area_index < 2 and period <= pd.Period("2024-10", freq="M")
                        else None
                    ),
                }
            )
    return pd.DataFrame(rows)


def formal_prediction_fixture(horizon_months: int) -> pd.DataFrame:
    target_month = str(pd.Period("2026-04", freq="M") + horizon_months)
    probabilities = np.asarray((0.20, 0.60, 0.80, 0.40))
    threshold = 0.50
    return pd.DataFrame(
        {
            "admin_code": ("0", "1", "2", "3"),
            "feature_month": ("2026-04",) * 4,
            "target_month": (target_month,) * 4,
            "horizon_months": (horizon_months,) * 4,
            "probability_crisis": probabilities,
            "predicted_crisis": (probabilities >= threshold).astype(int),
            "threshold": (threshold,) * 4,
            "cluster_id": pd.array((5, 5, 1, None), dtype="Int64"),
            "prediction_source": (
                "partition_model",
                "partition_model",
                "pooled_small_partition",
                "pooled_unmapped",
            ),
            "suite_version": (SUITE_VERSION,) * 4,
            "vertex_model_resource_name": ("",) * 4,
            "vertex_model_version_id": ("",) * 4,
        }
    )


def enriched_prediction_fixture(horizon_months: int) -> pd.DataFrame:
    identity, _ = build_identity_population_frame(
        population_panel_fixture(),
        "2026-04",
    )
    horizon_key = {0: "0m", 6: "6m", 12: "12m"}[horizon_months]
    return enrich_local_predictions(
        formal_prediction_fixture(horizon_months),
        identity,
        model_artifact_path=f"model_artifacts/{SUITE_VERSION}/{horizon_key}",
        source_input="/tmp/panel.csv",
    )


def test_population_uses_latest_raw_observation_and_never_model_imputation():
    panel = population_panel_fixture()
    identity, summary = build_identity_population_frame(panel, "2026-04")

    by_admin = identity.set_index("admin_code")
    assert by_admin.loc["0", "population"] == 1000.0
    assert by_admin.loc["0", "population_reference_period"] == "2024-10"
    assert by_admin.loc["0", "population_source"] == "raw_last_observed"
    assert pd.isna(by_admin.loc["2", "population"])
    assert pd.isna(by_admin.loc["2", "population_reference_period"])
    assert by_admin.loc["2", "population_source"] == "missing_raw"
    assert summary.raw_last_observed_count == 2
    assert summary.missing_raw_count == 2
    assert summary.missing_admin_codes == ("2", "3")


def test_enriched_predictions_have_exact_local_columns_and_no_ipcch_fields():
    formal = formal_prediction_fixture(horizon_months=6)
    identity, _ = build_identity_population_frame(population_panel_fixture(), "2026-04")
    enriched = enrich_local_predictions(
        formal,
        identity,
        model_artifact_path="model_artifacts/local-suite/6m",
        source_input="/tmp/panel.csv",
    )

    assert enriched.columns.tolist() == list(LOCAL_PREDICTION_COLUMNS)
    assert not any(name.startswith("phase") for name in enriched.columns)
    assert "prediction_uncertainty" not in enriched.columns
    assert "vertex_model_resource_name" not in enriched.columns
    assert "vertex_model_version_id" not in enriched.columns


def test_prediction_validation_enforces_probability_threshold_and_row_order():
    frame = enriched_prediction_fixture(horizon_months=0)
    summary = validate_local_prediction_frame(
        frame,
        expected_admin_codes=("0", "1", "2", "3"),
        feature_month="2026-04",
        target_month="2026-04",
        horizon_months=0,
        suite_version=SUITE_VERSION,
    )
    assert summary["row_count"] == 4
    assert summary["probability_min"] >= 0.0
    assert summary["probability_max"] <= 1.0

    invalid = frame.copy()
    invalid.loc[0, "predicted_crisis"] = 1 - invalid.loc[0, "predicted_crisis"]
    with pytest.raises(ValueError, match="threshold-to-label"):
        validate_local_prediction_frame(
            invalid,
            expected_admin_codes=("0", "1", "2", "3"),
            feature_month="2026-04",
            target_month="2026-04",
            horizon_months=0,
            suite_version=SUITE_VERSION,
        )


def test_three_scope_validation_requires_identical_identity_and_target_semantics():
    predictions = {
        "0m": enriched_prediction_fixture(horizon_months=0),
        "6m": enriched_prediction_fixture(horizon_months=6),
        "12m": enriched_prediction_fixture(horizon_months=12),
    }
    suite = validate_local_prediction_suite(
        predictions,
        expected_admin_codes=("0", "1", "2", "3"),
        feature_month="2026-04",
        suite_version=SUITE_VERSION,
    )
    assert suite["target_months"] == {
        "0m": "2026-04",
        "6m": "2026-10",
        "12m": "2027-04",
    }

    predictions["12m"] = predictions["12m"].iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="identical admin_code row order"):
        validate_local_prediction_suite(
            predictions,
            expected_admin_codes=("0", "1", "2", "3"),
            feature_month="2026-04",
            suite_version=SUITE_VERSION,
        )
```

Add these exact negative cases:

```python
def validate_0m(frame: pd.DataFrame) -> dict[str, object]:
    return validate_local_prediction_frame(
        frame,
        expected_admin_codes=("0", "1", "2", "3"),
        feature_month="2026-04",
        target_month="2026-04",
        horizon_months=0,
        suite_version=SUITE_VERSION,
    )


def test_prediction_validation_rejects_duplicate_or_missing_area():
    frame = enriched_prediction_fixture(0)
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate admin_code"):
        validate_0m(duplicate)
    with pytest.raises(ValueError, match="expected admin_code row order"):
        validate_0m(frame.iloc[:-1].copy())


def test_prediction_validation_rejects_nonfinite_probability_and_threshold_drift():
    frame = enriched_prediction_fixture(0)
    nonfinite = frame.copy()
    nonfinite.loc[0, "probability_crisis"] = np.inf
    with pytest.raises(ValueError, match="finite"):
        validate_0m(nonfinite)
    threshold_drift = frame.copy()
    threshold_drift.loc[0, "threshold"] = 0.70
    with pytest.raises(ValueError, match="one constant threshold"):
        validate_0m(threshold_drift)


def test_prediction_validation_rejects_invalid_source_and_population_pairing():
    frame = enriched_prediction_fixture(0)
    invalid_source = frame.copy()
    invalid_source.loc[0, "cluster_id"] = pd.NA
    invalid_source.loc[0, "prediction_source"] = "partition_model"
    with pytest.raises(ValueError, match="cluster/source"):
        validate_0m(invalid_source)
    invalid_population = frame.copy()
    invalid_population.loc[2, "population"] = 123.0
    with pytest.raises(ValueError, match="population provenance"):
        validate_0m(invalid_population)


def test_prediction_validation_rejects_prohibited_extra_field():
    frame = enriched_prediction_fixture(0)
    frame["phase3_worse_probability"] = 0.25
    with pytest.raises(ValueError, match="exact columns"):
        validate_0m(frame)
```

- [ ] **Step 2: Run output tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_outputs.py \
  -q -p no:cacheprovider
```

Expected: collection fails because `local.outputs` and its schema do not exist.

- [ ] **Step 3: Add the exact local prediction schema**

Create `local-prediction-record.schema.json` with `additionalProperties: false` and these exact required fields in code-level order:

```python
LOCAL_PREDICTION_COLUMNS = (
    "admin_code",
    "ADMIN0",
    "ADMIN1",
    "ADMIN2",
    "ADMIN3",
    "ISO3",
    "lat",
    "lon",
    "population",
    "population_reference_period",
    "population_source",
    "probability_crisis",
    "predicted_crisis",
    "threshold",
    "cluster_id",
    "prediction_source",
    "feature_month",
    "target_month",
    "horizon_months",
    "suite_version",
    "model_artifact_path",
    "source_input",
)
```

Schema rules:

- `admin_code`, `suite_version`, `model_artifact_path`, and `source_input` are non-empty strings.
- `ADMIN0` through `ADMIN3` and `ISO3` are string or null because lower administrative levels can be absent.
- `lat` and `lon` are finite JSON numbers; semantic bounds are checked in Python as `[-90, 90]` and `[-180, 180]`.
- `population` is a nonnegative number or null.
- `population_reference_period` is `YYYY-MM` or null.
- `population_source` is `raw_last_observed` or `missing_raw`.
- `probability_crisis` and `threshold` are numbers in `[0, 1]`.
- `predicted_crisis` is integer 0 or 1.
- `cluster_id` is integer 0 through 16 or null.
- `prediction_source` uses the existing five-value fallback vocabulary.
- `feature_month` and `target_month` are `YYYY-MM`.
- `horizon_months` is 0, 6, or 12.

- [ ] **Step 4: Implement population selection and identity enrichment**

Implement:

```python
@dataclass(frozen=True)
class PopulationSummary:
    raw_last_observed_count: int
    missing_raw_count: int
    missing_admin_codes: tuple[str, ...]
    reference_period_counts: dict[str, int]
```

`build_identity_population_frame` must:

1. Require raw columns `FEWSNET_admin_code`, `ADMIN0`, `ADMIN1`, `ADMIN2`, `ADMIN3`, `ISO3`, `lat`, `lon`, `pop`, and `date`.
2. Normalize admin codes with `normalize_admin_code` and parse `date` to monthly periods.
3. Require exactly one row per admin code in the requested feature month.
4. Use that feature-month row for administrative names, ISO3, latitude, and longitude.
5. Coerce non-null raw population to finite nonnegative numeric values; reject invalid non-null text or infinities.
6. From rows at or before the feature month, stable-sort by admin code and month, take the last non-null raw population per admin, and never call a model imputer.
7. Emit `raw_last_observed` plus the exact source period when found; otherwise emit null value/period plus `missing_raw`.
8. Return rows sorted by normalized `admin_code` and a deterministic `PopulationSummary`.

`enrich_local_predictions` must require the existing exact `FORMAL_PREDICTION_COLUMNS`, verify that both Vertex fields are blank, remove those two fields, one-to-one join identity/population on `admin_code`, add `model_artifact_path` and `source_input`, and return only `LOCAL_PREDICTION_COLUMNS`.

- [ ] **Step 5: Implement frame, suite, and CSV validation**

`validate_local_prediction_frame` must enforce:

- Exact columns and exact expected admin-code row order.
- One row per admin and no blanks.
- One exact feature month, target month, horizon, and suite version.
- Finite bounded probability and threshold; one constant threshold per file.
- Exact threshold-to-label equality using vectorized comparison.
- Cluster/source rules: null cluster requires `pooled_unmapped`; `partition_model` requires non-null cluster; pooled partition fallback states require non-null cluster.
- Population provenance consistency.
- Per-record JSON Schema validation after converting pandas nulls to JSON `null`.

Return a summary containing row count, probability min/max/mean, threshold, positive-label count, fallback counts, population counts, and missing admin codes.

`validate_local_prediction_suite` must call the frame validator in `0m`, `6m`, `12m` order; require identical identity, coordinates, population values/provenance, source input, area set, and row order; and return per-horizon summaries plus exact target months.

`write_local_prediction_csv` must refuse an existing path, create its parent, write UTF-8 with `lineterminator="\n"`, read the file back with stable dtypes, and return path, SHA-256, size, row count, and columns.

- [ ] **Step 6: Run GREEN and regression tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_outputs.py \
  tests/fewsnet_partitioned_rf/test_training_inference.py \
  tests/fewsnet_partitioned_rf/test_horizons.py \
  -q -p no:cacheprovider
```

Expected: PASS and existing formal predictor output remains unchanged.

- [ ] **Step 7: Record evidence, detect staged impact, and commit Task 2**

Update `PROGRESS.md`, run staged GitNexus change detection, then:

```bash
git diff --cached --check
git commit -m "feat: define FEWSNET local prediction outputs"
```

---

### Task 3: Build the Three-Horizon Staged Local Engine

**Files:**

- Create: `fewsnet_partitioned_rf_pipeline/local/runner.py`
- Create: `tests/fewsnet_partitioned_rf/test_local_runner.py`
- Extend with new helper functions only: `tests/fewsnet_partitioned_rf/local_test_support.py`
- Modify: `PROGRESS.md`

**Interfaces:**

- Produces `LocalExperimentConfig` with panel, audit, feature month, output root, and overwrite flag.
- Produces `StagedLocalExperiment` describing all staged or reused package, report, prediction, and summary paths.
- Produces `resolve_clean_git_commit(repo_root) -> str`.
- Produces `build_staged_local_experiment(config, staging_root) -> StagedLocalExperiment`.
- Consumes Tasks 1 and 2 plus existing public FEWSNET core APIs.

- [ ] **Step 1: Extend the fixture helper for a true three-horizon panel**

Add new helper functions without changing the already reviewed package-fixture behavior:

```python
def write_normalized_local_panel_fixture(
    root: Path,
) -> tuple[Path, Path, pd.DataFrame]:
    root.mkdir(parents=True, exist_ok=False)
    contract = load_feature_contract(FEATURE_CONTRACT_PATH)
    source_columns = list(contract.required_source_columns)
    periods = pd.period_range("2022-03", "2026-04", freq="M")
    rows: list[dict[str, object]] = []
    admin_rows = (
        ("0", 9.551002, 29.130297, "Country A", "A1", "A2", "A3"),
        ("1", 9.786447, 28.414507, "Country A", "A1", "B2", "B3"),
        ("2", 7.799214, 32.853080, "Country B", "C1", "C2", "C3"),
        ("3", 8.417933, 26.895620, "Country B", "C1", "D2", "D3"),
    )
    for area_index, values in enumerate(admin_rows):
        admin_code, lat, lon, admin0, admin1, admin2, admin3 = values
        for month_index, period in enumerate(periods):
            row = {
                name: float((column_index % 13) + 1) + month_index / 1000
                for column_index, name in enumerate(source_columns)
            }
            has_label = period <= pd.Period("2026-02", freq="M")
            row.update(
                {
                    "FEWSNET_admin_code": admin_code,
                    "ISO": "SS",
                    "lat": lat,
                    "lon": lon,
                    "month": period.month,
                    "fews_ipc": float(2 + ((month_index + area_index) % 2)),
                    "fews_ipc_crisis": (
                        float((month_index + area_index) % 2) if has_label else None
                    ),
                    "date": period.to_timestamp().strftime("%Y-%m-%d"),
                    "pop": (
                        float(1000 + area_index * 100)
                        if area_index < 2 and period <= pd.Period("2024-10", freq="M")
                        else None
                    ),
                }
            )
            row.update(
                {
                    "ADMIN0": admin0,
                    "ADMIN1": admin1,
                    "ADMIN2": admin2,
                    "ADMIN3": admin3,
                    "ISO3": "SSD",
                }
            )
            rows.append(row)
    raw_frame = pd.DataFrame(rows)
    raw_path = root / "panel.raw.csv"
    normalized_path = root / "panel.normalized-v1.csv"
    audit_path = root / "panel.normalized-v1.audit.json"
    raw_frame.to_csv(raw_path, index=False, lineterminator="\n")
    normalize_panel(raw_path, normalized_path, audit_path)
    return normalized_path, audit_path, raw_frame
```

When constructing `raw_frame`, order columns as all raw identity columns followed by every frozen required source column not already present, so normalization preserves identity fields while the feature builder sees its exact contract.

- [ ] **Step 2: Write the failing staged-engine integration tests**

Create these principal tests:

```python
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import fewsnet_partitioned_rf_pipeline.local.runner as runner
from fewsnet_partitioned_rf_pipeline.core.normalization import normalize_panel
from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
from tests.fewsnet_partitioned_rf.local_test_support import (
    write_normalized_local_panel_fixture,
)


def seed_existing_suite(
    staged: runner.StagedLocalExperiment,
    output_root: Path,
) -> None:
    package_parent = staged.package_dirs["0m"].parent
    final_package_parent = output_root / "model_artifacts" / staged.suite_version
    shutil.copytree(package_parent, final_package_parent)

    report_parent = staged.report_files["run_manifest"].parent
    final_report_parent = output_root / "reports" / staged.suite_version
    shutil.copytree(report_parent, final_report_parent)


def test_staged_engine_trains_reloads_and_predicts_all_three_horizons(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    monkeypatch.setattr(runner, "utc_now", lambda: "2026-07-26T12:00:00Z")

    staged = runner.build_staged_local_experiment(
        runner.LocalExperimentConfig(
            panel_path=panel,
            normalization_audit_path=audit,
            feature_month="2026-04",
            output_root=tmp_path / "final",
            overwrite=False,
        ),
        tmp_path / "staging",
    )

    assert staged.suite_version == "local-202604-111111111111-" + staged.panel_sha256[:12]
    assert staged.reused_model_suite is False
    assert set(staged.package_dirs) == {"0m", "6m", "12m"}
    assert set(staged.prediction_files) == {"0m", "6m", "12m"}
    expected_targets = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}

    for horizon_key, package_dir in staged.package_dirs.items():
        loaded = load_local_model_package(
            package_dir,
            expected_suite_version=staged.suite_version,
            expected_source_git_commit="1" * 40,
            expected_panel_sha256=staged.panel_sha256,
        )
        assert loaded.predictor.horizon_key == horizon_key

        prediction = pd.read_csv(staged.prediction_files[horizon_key])
        assert len(prediction) == 4
        assert prediction["target_month"].unique().tolist() == [expected_targets[horizon_key]]
        assert prediction["probability_crisis"].between(0, 1).all()

    summary = json.loads(staged.run_summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["gcp_write_performed"] is False
    assert summary["population"]["raw_last_observed_count"] == 2
    assert summary["population"]["missing_raw_count"] == 2


def test_staged_engine_fails_closed_when_one_horizon_training_fails(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    original = runner.train_horizon_model

    def fail_6m(aligned_frame, feature_contract, partition_map, horizon_key):
        if horizon_key == "6m":
            raise RuntimeError("synthetic 6m failure")
        return original(aligned_frame, feature_contract, partition_map, horizon_key)

    monkeypatch.setattr(runner, "train_horizon_model", fail_6m)
    with pytest.raises(RuntimeError, match="synthetic 6m failure"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "staging",
        )
    assert not (tmp_path / "staging/predictions/202604/run_summary.json").exists()


def test_staged_engine_reuses_only_a_fully_valid_existing_suite(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    config = runner.LocalExperimentConfig(
        panel_path=panel,
        normalization_audit_path=audit,
        feature_month="2026-04",
        output_root=tmp_path / "final",
        overwrite=True,
    )
    first = runner.build_staged_local_experiment(config, tmp_path / "stage-one")
    seed_existing_suite(first, config.output_root)

    def forbidden_training(*args, **kwargs):
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(runner, "train_horizon_model", forbidden_training)
    second = runner.build_staged_local_experiment(config, tmp_path / "stage-two")
    assert second.reused_model_suite is True

    checksums = config.output_root / "model_artifacts" / second.suite_version / "6m" / "checksums.json"
    checksums.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        runner.build_staged_local_experiment(config, tmp_path / "stage-three")


def test_staged_engine_rejects_panel_audit_drift_and_nonlatest_month(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    panel.write_bytes(panel.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="normalization audit does not match panel"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "stage-audit-drift",
        )

    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source-two")
    with pytest.raises(ValueError, match="latest feature month"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-03",
                output_root=tmp_path / "final-two",
            ),
            tmp_path / "stage-old-month",
        )


def test_staged_engine_rejects_area_count_and_unsafe_ipcch_root(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    with pytest.raises(ValueError, match="area_count.*5718"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "stage-area-count",
        )

    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    forbidden_root = Path.cwd() / "Outcome/ipcch_unified/local-fewsnet-test"
    with pytest.raises(ValueError, match="Outcome/ipcch_unified"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=forbidden_root,
            ),
            tmp_path / "stage-unsafe-root",
        )


def test_clean_git_probe_rejects_tracked_changes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "initial"],
        cwd=repo,
        check=True,
    )
    assert len(runner.resolve_clean_git_commit(repo)) == 40
    tracked.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tracked Git changes"):
        runner.resolve_clean_git_commit(repo)


def test_staged_engine_rejects_feature_or_partition_checksum_drift(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    monkeypatch.setattr(runner, "FEATURE_CONTRACT_FILE_SHA256", "f" * 64)
    with pytest.raises(ValueError, match="feature contract SHA-256"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(panel, audit, "2026-04", tmp_path / "final"),
            tmp_path / "stage-feature-drift",
        )

    monkeypatch.setattr(
        runner,
        "FEATURE_CONTRACT_FILE_SHA256",
        "3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b",
    )
    monkeypatch.setattr(runner, "PARTITION_ASSET_SHA256", "e" * 64)
    with pytest.raises(ValueError, match="partition asset SHA-256"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(panel, audit, "2026-04", tmp_path / "final-two"),
            tmp_path / "stage-partition-drift",
        )
```

Add the missing-area case:

```python
def test_staged_engine_rejects_missing_feature_month_area(tmp_path, monkeypatch):
    _, _, raw = write_normalized_local_panel_fixture(tmp_path / "complete-source")
    feature_periods = pd.to_datetime(raw["date"]).dt.to_period("M")
    missing_latest = raw.loc[
        ~(
            raw["FEWSNET_admin_code"].astype(str).eq("3")
            & feature_periods.eq(pd.Period("2026-04", freq="M"))
        )
    ].copy()
    source = tmp_path / "missing-source"
    source.mkdir()
    raw_path = source / "panel.raw.csv"
    panel_path = source / "panel.normalized-v1.csv"
    audit_path = source / "panel.normalized-v1.audit.json"
    missing_latest.to_csv(raw_path, index=False, lineterminator="\n")
    normalize_panel(raw_path, panel_path, audit_path)

    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    with pytest.raises(ValueError, match="missing authoritative admin_code"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel_path,
                normalization_audit_path=audit_path,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "stage-missing-area",
        )
```

- [ ] **Step 3: Run the staged-engine tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_runner.py \
  -q -p no:cacheprovider
```

Expected: collection fails because `local.runner` does not exist.

- [ ] **Step 4: Implement configuration, preflight, and deterministic identities**

Create:

```python
EXPECTED_AREA_COUNT = 5718
FEATURE_CONTRACT_FILE_SHA256 = (
    "3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b"
)


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
```

`package_dirs` and `prediction_files` have exactly `0m`, `6m`, and `12m` keys. `report_files` has exactly `training_threshold_report` and `run_manifest` keys.

`resolve_clean_git_commit` must run `git rev-parse --show-toplevel`, `git diff --quiet`, `git diff --cached --quiet`, and `git rev-parse HEAD` without a shell. It accepts ignored outputs but rejects staged or unstaged tracked changes. Return exactly 40 lowercase hexadecimal characters.

Preflight must complete before training or final publication:

1. Resolve paths, require separate existing panel and audit, and reject any output root equal to or inside repository `Outcome/ipcch_unified`.
2. Validate the normalization audit against the panel bytes.
3. Require the audit source-panel path to differ from the normalized panel path.
4. Run `inspect_panel` and require row count/audit consistency, exactly 5,718 areas in production, `latest_feature_month == requested feature_month == 2026-04`, and `latest_label_month == 2026-02` for the accepted source.
5. Chunk-read only `FEWSNET_admin_code` and `date`, normalize both, and require the requested feature month to contain exactly the full authoritative admin universe once each before any model training.
6. Load the fixed feature contract and partition map through their checksum-bound public loaders.
7. Record the clean Git commit and runtime dependency versions.
8. Compute `suite_version = f"local-{YYYYMM}-{git_commit[:12]}-{panel_sha256[:12]}"`.
9. Compute a separately timestamped run ID `local-{YYYYMM}-{YYYYMMDDTHHMMSSffffffZ}`; tests control the clock through a module-level `utc_now()` helper.

- [ ] **Step 5: Implement the train/package/reload/predict loop**

`build_staged_local_experiment` must:

1. Load the normalized panel once with `FEWSNET_admin_code` as string and `low_memory=False`.
2. Transform it once with the frozen `Stage3FeatureBuilder` contract.
3. Build identity/population enrichment once from the raw panel.
4. Check `output_root/model_artifacts/{suite_version}`. If any part exists, require all three exact packages and suite reports to validate; load them and set `reused_model_suite=True`. Never repair or overwrite a partial/mismatched suite.
5. Otherwise, for horizons in `HORIZON_MONTHS` order:
   - align keyed targets with `align_horizon`;
   - select the exact 36-target-month window ending at the common latest label month;
   - call `train_horizon_model`;
   - write the local package under staging;
   - reload it through `load_local_model_package` with expected suite, commit, and panel digest;
   - use only the reloaded predictor for accepted prediction generation.
6. Select the complete requested inference frame with `select_latest_inference_frame`, predict, enrich, validate, and write each CSV using these exact names:

```python
PREDICTION_FILENAMES = {
    "0m": "fewsnet_partitioned_rf_202604_scope_0m_predictions.csv",
    "6m": "fewsnet_partitioned_rf_202604_scope_6m_predictions.csv",
    "12m": "fewsnet_partitioned_rf_202604_scope_12m_predictions.csv",
}
```

7. Use the relative `model_artifact_path` value `model_artifacts/{suite_version}/{horizon_key}` and the resolved normalized panel path as `source_input`.
8. Validate all three scopes together before creating any passed summary.

- [ ] **Step 6: Write staged reports and summary last**

For a newly trained suite, write under staging:

```text
reports/{suite_version}/training_threshold_report.json
reports/{suite_version}/run_manifest.json
```

The aggregate training report must use the existing `fewsnet-training-report-v1` schema and preserve the same training/validation range across all three horizons.

The local suite run manifest must record run ID, suite version, runtime backend, source commit/dependencies, panel/audit identities, feature/partition digests, horizon package member checksums, training/validation windows, and `gcp_write_performed: false`.

Write staged `predictions/202604/run_summary.json` only after all package reloads, CSV writes, and suite validation pass. It must contain:

```text
schema_version, run_id, suite_version, started_at_utc, completed_at_utc, status
runtime_backend, gcp_write_performed, source_git_commit, dependency_versions
panel, normalization_audit, latest_feature_month, latest_label_month
training_target_month_range, validation_target_month_range
population, horizons, model_packages, reports
```

Each horizon summary records target month, threshold, row count, positive count, probability min/max/mean, fallback counts, package path/member checksums, and prediction path/SHA-256/size.

Use these exact nested keys so publication and the independent verifier consume one stable contract:

```python
run_summary["panel"] = {
    "path": str(resolved_panel_path),
    "sha256": panel_sha256,
    "size_bytes": panel_size_bytes,
    "row_count": panel_row_count,
}
run_summary["normalization_audit"] = {
    "path": str(resolved_audit_path),
    "sha256": audit_sha256,
    "size_bytes": audit_size_bytes,
}
run_summary["horizons"][horizon_key]["prediction"] = {
    "relative_path": prediction_relative_path,
    "sha256": prediction_sha256,
    "size_bytes": prediction_size_bytes,
    "row_count": prediction_row_count,
}
run_summary["model_packages"][horizon_key] = {
    "relative_path": package_relative_path,
    "member_checksums": package_member_checksums,
}
run_summary["reports"] = {
    "training_threshold_report": {
        "relative_path": training_report_relative_path,
        "sha256": training_report_sha256,
        "size_bytes": training_report_size_bytes,
    },
    "run_manifest": {
        "relative_path": run_manifest_relative_path,
        "sha256": run_manifest_sha256,
        "size_bytes": run_manifest_size_bytes,
    },
}
```

- [ ] **Step 7: Run GREEN and focused integration regression**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_runner.py \
  tests/fewsnet_partitioned_rf/test_local_package.py \
  tests/fewsnet_partitioned_rf/test_local_outputs.py \
  tests/fewsnet_partitioned_rf/test_training_job.py \
  -q -p no:cacheprovider
```

Expected: PASS; the small integration performs real core training for all three horizons without GCP credentials or network access.

- [ ] **Step 8: Record evidence, detect staged impact, and commit Task 3**

Update `PROGRESS.md`, run staged GitNexus change detection, then:

```bash
git diff --cached --check
git commit -m "feat: run FEWSNET three-horizon local experiment"
```

---

### Task 4: Add Copy-Based Publication, CLI, Ignore Rule, and Operator Documentation

**Files:**

- Add new functions and result type: `fewsnet_partitioned_rf_pipeline/local/runner.py`
- Modify exports: `fewsnet_partitioned_rf_pipeline/local/__init__.py`
- Create: `fewsnet_partitioned_rf_pipeline/cli/run_local_experiment.py`
- Create: `tests/fewsnet_partitioned_rf/test_local_cli.py`
- Add publication cases: `tests/fewsnet_partitioned_rf/test_local_runner.py`
- Modify: `.gitignore`
- Modify: `docs/09_fewsnet_partitioned_rf_runbook.md`
- Modify: `docs/04_output_inventory.md`
- Modify: `PROGRESS.md`

**Interfaces:**

- Produces `LocalExperimentResult` and `to_payload()` for JSON output.
- Produces `publish_staged_local_experiment(staged, config) -> LocalExperimentResult`.
- Produces `run_local_experiment(config) -> LocalExperimentResult`.
- Produces CLI `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write failing publication and CLI tests**

Add publication cases:

```python
import json
from pathlib import Path

import pytest

import fewsnet_partitioned_rf_pipeline.local.runner as runner
from tests.fewsnet_partitioned_rf.local_test_support import (
    write_normalized_local_panel_fixture,
)


def local_config(
    output_root: Path,
    *,
    overwrite: bool = False,
) -> runner.LocalExperimentConfig:
    source = output_root.parent / "synthetic-source"
    return runner.LocalExperimentConfig(
        panel_path=source / "panel.normalized-v1.csv",
        normalization_audit_path=source / "panel.normalized-v1.audit.json",
        feature_month="2026-04",
        output_root=output_root,
        overwrite=overwrite,
    )


def staged_fixture(
    tmp_path: Path,
    monkeypatch,
    *,
    overwrite: bool = False,
) -> tuple[runner.StagedLocalExperiment, runner.LocalExperimentConfig]:
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(runner, "resolve_clean_git_commit", lambda root: "1" * 40)
    config = runner.LocalExperimentConfig(
        panel_path=panel,
        normalization_audit_path=audit,
        feature_month="2026-04",
        output_root=tmp_path / "Outcome/fewsnet_partitioned_rf",
        overwrite=overwrite,
    )
    staged = runner.build_staged_local_experiment(config, tmp_path / "staging")
    return staged, config


def test_publication_copies_three_csvs_and_writes_summary_last(
    tmp_path,
    monkeypatch,
):
    staged, config = staged_fixture(tmp_path, monkeypatch)
    copied: list[str] = []
    original_copy = runner.shutil.copy2

    def recording_copy(source, destination):
        copied.append(Path(destination).name)
        return original_copy(source, destination)

    monkeypatch.setattr(runner.shutil, "copy2", recording_copy)
    result = runner.publish_staged_local_experiment(staged, config)

    assert copied[-1] == "run_summary.json"
    assert result.run_summary_path.exists()
    assert json.loads(result.run_summary_path.read_text())["status"] == "passed"


def test_publication_refuses_prediction_overwrite_before_expensive_build(
    tmp_path,
    monkeypatch,
):
    output_root = tmp_path / "Outcome/fewsnet_partitioned_rf"
    prediction_dir = output_root / "predictions/202604"
    prediction_dir.mkdir(parents=True)
    (prediction_dir / "fewsnet_partitioned_rf_202604_scope_0m_predictions.csv").write_text(
        "sentinel\n",
        encoding="utf-8",
    )

    def forbidden_builder(*args, **kwargs):
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(runner, "build_staged_local_experiment", forbidden_builder)
    with pytest.raises(FileExistsError, match="--overwrite"):
        runner.run_local_experiment(local_config(output_root, overwrite=False))


def test_overwrite_failure_never_leaves_passed_summary(tmp_path, monkeypatch):
    staged, config = staged_fixture(tmp_path, monkeypatch, overwrite=True)
    final_summary = config.output_root / "predictions/202604/run_summary.json"
    final_summary.parent.mkdir(parents=True, exist_ok=True)
    final_summary.write_text('{"status":"passed"}\n', encoding="utf-8")
    original_copy = runner.shutil.copy2

    def fail_on_6m(source, destination):
        if "scope_6m" in str(destination):
            raise OSError("synthetic copy failure")
        return original_copy(source, destination)

    monkeypatch.setattr(runner.shutil, "copy2", fail_on_6m)
    with pytest.raises(OSError, match="synthetic copy failure"):
        runner.publish_staged_local_experiment(staged, config)
    assert not final_summary.exists()


def test_publication_never_touches_ipcch_unified(tmp_path, monkeypatch):
    ipcch = tmp_path / "Outcome/ipcch_unified/predictions/sentinel.txt"
    ipcch.parent.mkdir(parents=True)
    ipcch.write_text("keep", encoding="utf-8")
    staged, config = staged_fixture(tmp_path, monkeypatch)
    runner.publish_staged_local_experiment(staged, config)
    assert ipcch.read_text(encoding="utf-8") == "keep"
```

Create CLI tests with this concrete success/failure surface:

```python
import json
from pathlib import Path

import pytest

from fewsnet_partitioned_rf_pipeline.cli import run_local_experiment as cli
from fewsnet_partitioned_rf_pipeline.local.runner import LocalExperimentResult


def result_fixture(tmp_path: Path) -> LocalExperimentResult:
    root = tmp_path / "Outcome/fewsnet_partitioned_rf"
    return LocalExperimentResult(
        run_id="local-202604-20260726T120000000000Z",
        suite_version="local-202604-111111111111-222222222222",
        output_root=root,
        run_summary_path=root / "predictions/202604/run_summary.json",
        prediction_paths={
            key: root / f"predictions/202604/{key}.csv"
            for key in ("0m", "6m", "12m")
        },
        model_package_paths={
            key: root / f"model_artifacts/local-suite/{key}"
            for key in ("0m", "6m", "12m")
        },
        report_paths={
            "training_threshold_report": root / "reports/local-suite/training_threshold_report.json",
            "run_manifest": root / "reports/local-suite/run_manifest.json",
        },
    )


def test_cli_prints_json_success_and_forwards_overwrite(tmp_path, monkeypatch, capsys):
    captured_config = None

    def fake_run(config):
        nonlocal captured_config
        captured_config = config
        return result_fixture(tmp_path)

    monkeypatch.setattr(cli, "run_local_experiment", fake_run)
    code = cli.main(
        [
            "--panel", str(tmp_path / "panel.csv"),
            "--normalization-audit", str(tmp_path / "panel.audit.json"),
            "--feature-month", "2026-04",
            "--overwrite",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "passed"
    assert captured_config.output_root == Path("Outcome/fewsnet_partitioned_rf")
    assert captured_config.overwrite is True


def test_cli_returns_json_failure_and_has_no_cloud_arguments(tmp_path, monkeypatch, capsys):
    def fail(config):
        raise RuntimeError(f"synthetic failure: {config.feature_month}")

    monkeypatch.setattr(cli, "run_local_experiment", fail)
    code = cli.main(
        [
            "--panel", str(tmp_path / "panel.csv"),
            "--normalization-audit", str(tmp_path / "panel.audit.json"),
            "--feature-month", "2026-04",
        ]
    )
    payload = json.loads(capsys.readouterr().err)
    assert code == 1
    assert payload == {
        "error_type": "RuntimeError",
        "message": "synthetic failure: 2026-04",
        "status": "failed",
    }
    help_text = cli.build_parser().format_help().lower()
    for forbidden in ("gcs", "vertex", "registry", "endpoint", "batch", "shapefile"):
        assert forbidden not in help_text


def test_cli_requires_panel_audit_and_feature_month():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--panel", "panel.csv", "--normalization-audit", "audit.json"])
```

These tests also cover the following parser contract:

- Required `--panel`, `--normalization-audit`, and `--feature-month` parsing.
- Default `--output-root Outcome/fewsnet_partitioned_rf`.
- `--overwrite` forwarding.
- One JSON object on stdout and exit code 0 on success.
- One JSON error object on stderr and nonzero exit on runtime failure.
- Parser and help text contain no GCS, Vertex, registry, endpoint, batch, or shapefile arguments.

- [ ] **Step 2: Run publication and CLI tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_runner.py \
  tests/fewsnet_partitioned_rf/test_local_cli.py \
  -q -p no:cacheprovider
```

Expected: FAIL because publication functions, result type, and CLI are absent.

- [ ] **Step 3: Implement copy-based publication and final verification**

Add:

```python
@dataclass(frozen=True)
class LocalExperimentResult:
    run_id: str
    suite_version: str
    output_root: Path
    run_summary_path: Path
    prediction_paths: dict[str, Path]
    model_package_paths: dict[str, Path]
    report_paths: dict[str, Path]

    def to_payload(self) -> dict[str, object]:
        return {
            "status": "passed",
            "run_id": self.run_id,
            "suite_version": self.suite_version,
            "output_root": str(self.output_root),
            "run_summary_path": str(self.run_summary_path),
            "prediction_paths": {
                key: str(path) for key, path in self.prediction_paths.items()
            },
            "model_package_paths": {
                key: str(path) for key, path in self.model_package_paths.items()
            },
            "report_paths": {
                key: str(path) for key, path in self.report_paths.items()
            },
        }
```

`publish_staged_local_experiment` must:

1. Re-run the safe-output-root guard.
2. For a new model suite, atomically claim the package root and then the report root in that deterministic order before copying any members. Copy each staged package below the claimed package root, then reload every final package and compare expected identities/checksums. Cleanup may remove only roots successfully claimed by this publisher.
3. For a reused suite, do not copy or modify packages; validate them again from final paths.
4. Publish suite reports create-only. If already present for a reused suite, require byte-identical expected files and valid references; never overwrite a differing report.
5. Before prediction publication, reject any existing non-regular prediction or summary target in all modes. If a regular exact target exists and `overwrite` is false, fail early; the authoritative create-only write must still use exclusive creation so a target inserted after preflight is preserved.
6. With explicit overwrite, unlink the existing final `run_summary.json` before copying any CSV, so a partial replacement cannot retain `status: passed`.
7. Publish the three CSVs in `0m`, `6m`, `12m` order. Use exclusive creation by default; under explicit overwrite, `shutil.copy2` may replace only a target revalidated as a regular file. Track a create-only target for cleanup only after its exclusive copy succeeds. After each publication, verify SHA-256, size, row count, columns, and frame contract against the staged summary.
8. After final packages, reports, and predictions are published and verified, stamp `completed_at_utc` and publish canonical `run_summary.json` last using the same exclusive-versus-explicit-overwrite rule. Reopen it, require `status == "passed"`, and verify all recorded final package/report/prediction checksums.
9. Return `LocalExperimentResult` only after final verification.

`run_local_experiment` must perform the no-overwrite check before expensive panel loading, create a temporary sibling staging directory with `tempfile.TemporaryDirectory`, call the staged engine, publish, and return the result.

- [ ] **Step 4: Implement the local CLI**

Create `run_local_experiment.py` with this parser contract:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train and run the local FEWSNET partitioned-RF experiment."
    )
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--normalization-audit", required=True, type=Path)
    parser.add_argument("--feature-month", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("Outcome/fewsnet_partitioned_rf"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser
```

`main` constructs `LocalExperimentConfig`, invokes `run_local_experiment`, and prints `json.dumps(result.to_payload(), sort_keys=True)`. On exception, print a JSON object with `status: failed`, exception type, and message to stderr and return 1. Do not catch `SystemExit` from argparse.

Update `local/__init__.py` to export `LocalExperimentConfig`, `LocalExperimentResult`, and `run_local_experiment` in addition to Task 1 exports.

- [ ] **Step 5: Add the ignore rule and operator documentation**

Append to `.gitignore`:

```gitignore
# Generated FEWSNET local partitioned-RF experiments
Outcome/fewsnet_partitioned_rf/
```

In `docs/09_fewsnet_partitioned_rf_runbook.md`, add a local experiment section with:

- Purpose and explicit non-Vertex boundary.
- Python/venv setup.
- Exact full command with quoted Dropbox paths.
- Artifact tree and the meaning of local package versus production package.
- Probability/threshold semantics and absence of phase/categorical uncertainty.
- Raw last-observed population rule and expected `5716 + 2` provenance split.
- Default no-overwrite behavior and explicit rerun command using `--overwrite`.
- Failure recovery: trust only a passed summary with matching checksums; do not manually patch CSVs.
- A warning that future target months are forecast horizons, not observed evaluation labels.

In `docs/04_output_inventory.md`, add a separate FEWSNET local row/tree and state that it is neither an IPCCH release artifact nor a GCS/Vertex production suite.

- [ ] **Step 6: Run GREEN, CLI smoke, and full FEWSNET regression**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_local_runner.py \
  tests/fewsnet_partitioned_rf/test_local_cli.py \
  tests/fewsnet_partitioned_rf/test_local_package.py \
  tests/fewsnet_partitioned_rf/test_local_outputs.py \
  -q -p no:cacheprovider

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf \
  -q -p no:cacheprovider

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_local_experiment --help
```

Expected: all tests PASS or pre-existing live-GCP cases SKIP; CLI help shows only local arguments.

- [ ] **Step 7: Record evidence, detect staged impact, and commit Task 4**

Update `PROGRESS.md`, run staged GitNexus change detection, then:

```bash
git diff --cached --check
git commit -m "feat: publish FEWSNET local experiment artifacts"
```

At this point the tracked worktree must be clean before the real run because the runtime records the exact source commit and rejects dirty tracked files.

---

### Task 5: Run and Verify the Full Real-Source 2026-04 Experiment

**Files:**

- Generate, ignored: `Outcome/fewsnet_partitioned_rf/predictions/202604/*`
- Generate, ignored: `Outcome/fewsnet_partitioned_rf/model_artifacts/{suite_version}/{0m,6m,12m}/*`
- Generate, ignored: `Outcome/fewsnet_partitioned_rf/reports/{suite_version}/*`
- Modify after acceptance: `PROGRESS.md`

**Interfaces:**

- Consumes the clean Task 4 implementation commit and the complete approved normalized panel/audit.
- Produces the three accepted prediction CSVs, three reloadable local packages, two suite reports, and passed `run_summary.json`.
- Produces durable verification evidence in `PROGRESS.md`; generated outputs remain ignored and uncommitted.

- [ ] **Step 1: Establish the clean-run and IPCCH-preservation baselines**

Run:

```bash
git status --short
git rev-parse HEAD

find Outcome/ipcch_unified -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > /tmp/ipcch-unified-before-fewsnet-local.sha256
```

Expected: tracked status is empty. Save the exact implementation commit in `PROGRESS.md` only after the run, because editing the ledger before execution would intentionally trip the clean-Git gate.

If `Outcome/fewsnet_partitioned_rf/predictions/202604/` already contains accepted output, first validate and preserve it. Do not use `--overwrite` unless the user has explicitly approved replacement of that exact FEWSNET output root.

- [ ] **Step 2: Run the full local experiment**

Run without sampling or RF parameter changes:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_local_experiment \
  --panel "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv" \
  --normalization-audit "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json" \
  --feature-month 2026-04 \
  --output-root Outcome/fewsnet_partitioned_rf \
  | tee /tmp/fewsnet-local-202604-cli-result.json
```

Expected: exit 0 and one JSON success result naming the deterministic suite version and passed summary. This run may be long; monitor process activity without interrupting an active training step.

- [ ] **Step 3: Verify prediction, population, package, and summary contracts**

Run this independent verifier:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fewsnet_partitioned_rf_pipeline.local.outputs import LOCAL_PREDICTION_COLUMNS
from fewsnet_partitioned_rf_pipeline.local.package import (
    LOCAL_PACKAGE_FILES,
    load_local_model_package,
)

root = Path("Outcome/fewsnet_partitioned_rf")
summary_path = root / "predictions/202604/run_summary.json"
summary = json.loads(summary_path.read_text(encoding="utf-8"))
assert summary["status"] == "passed"
assert summary["runtime_backend"] == "local_python"
assert summary["gcp_write_performed"] is False
assert summary["latest_feature_month"] == "2026-04"
assert summary["latest_label_month"] == "2026-02"
assert summary["panel"]["row_count"] == 1120728
assert summary["panel"]["sha256"] == "510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d"
assert summary["population"]["raw_last_observed_count"] == 5716
assert summary["population"]["missing_raw_count"] == 2
assert len(summary["population"]["missing_admin_codes"]) == 2

expected_targets = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}
canonical_admins = None
for horizon_key, target_month in expected_targets.items():
    prediction_ref = summary["horizons"][horizon_key]["prediction"]
    prediction_path = root / prediction_ref["relative_path"]
    data = prediction_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == prediction_ref["sha256"]
    assert len(data) == prediction_ref["size_bytes"]
    frame = pd.read_csv(prediction_path, dtype={"admin_code": "string"})
    assert frame.columns.tolist() == list(LOCAL_PREDICTION_COLUMNS)
    assert len(frame) == 5718
    assert frame["admin_code"].nunique() == 5718
    assert frame["feature_month"].unique().tolist() == ["2026-04"]
    assert frame["target_month"].unique().tolist() == [target_month]
    assert np.isfinite(frame["probability_crisis"]).all()
    assert frame["probability_crisis"].between(0, 1).all()
    assert (
        frame["predicted_crisis"].to_numpy()
        == (frame["probability_crisis"] >= frame["threshold"]).astype(int).to_numpy()
    ).all()
    assert frame["population_source"].value_counts().to_dict() == {
        "raw_last_observed": 5716,
        "missing_raw": 2,
    }
    assert not any(column.startswith("phase") for column in frame.columns)
    assert "prediction_uncertainty" not in frame.columns
    admins = frame["admin_code"].astype(str).tolist()
    if canonical_admins is None:
        canonical_admins = admins
    else:
        assert admins == canonical_admins

    package_path = root / summary["model_packages"][horizon_key]["relative_path"]
    assert tuple(sorted(path.name for path in package_path.iterdir())) == tuple(
        sorted(LOCAL_PACKAGE_FILES)
    )
    loaded = load_local_model_package(
        package_path,
        expected_suite_version=summary["suite_version"],
        expected_source_git_commit=summary["source_git_commit"],
        expected_panel_sha256=summary["panel"]["sha256"],
    )
    assert loaded.predictor.horizon_key == horizon_key
    assert loaded.predictor.vertex_model_resource_name == ""
    assert loaded.predictor.vertex_model_version_id == ""

print(json.dumps({
    "status": "verified",
    "run_id": summary["run_id"],
    "suite_version": summary["suite_version"],
    "missing_population_admin_codes": summary["population"]["missing_admin_codes"],
}, indent=2, sort_keys=True))
PY
```

Expected: prints `status: verified` with the accepted run and suite identities.

- [ ] **Step 4: Prove IPCCH isolation and repository cleanliness**

Run:

```bash
find Outcome/ipcch_unified -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > /tmp/ipcch-unified-after-fewsnet-local.sha256

cmp \
  /tmp/ipcch-unified-before-fewsnet-local.sha256 \
  /tmp/ipcch-unified-after-fewsnet-local.sha256

git status --short --ignored Outcome/fewsnet_partitioned_rf
git status --short
```

Expected: `cmp` exits 0; the generated FEWSNET tree appears only as ignored; tracked status remains empty before the ledger update.

- [ ] **Step 5: Run final regression and static checks**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf \
  -q -p no:cacheprovider

git diff --check
```

Expected: all local and existing FEWSNET tests pass or live-cloud tests skip; no whitespace errors.

- [ ] **Step 6: Record final evidence and commit only the ledger**

Update `PROGRESS.md` with:

- Implementation commit used by the clean run.
- Run ID and deterministic suite version.
- Exact CLI command and exit status.
- Summary, prediction, package, and report paths/checksums.
- Row counts and target months.
- Learned threshold per horizon.
- Fallback counts per horizon.
- Population provenance `5716 raw_last_observed + 2 missing_raw` and the two missing admin codes.
- Independent verifier output.
- IPCCH before/after checksum comparison result.
- Full test result.
- Current state `integration-complete locally`; no cloud mutation attempted.

Set all five tasks to `integration-complete` or `component-complete` as appropriate and set the next step to user review of the local artifacts, not Vertex deployment.

Stage only `PROGRESS.md`, run GitNexus staged `detect_changes`, then:

```bash
git diff --cached --check
git commit -m "docs: record FEWSNET local 202604 acceptance"
```

Generated model packages, reports, and predictions remain local ignored artifacts and are not committed.

---

## Completion Gate

The plan is complete only when all of the following are simultaneously true:

- The full normalized source and matching audit validated.
- Three horizon packages use `fewsnet-local-model-package-v1`, reload successfully, and contain no fabricated Vertex identity.
- Three prediction CSVs contain exactly 5,718 areas in identical order.
- Target months are `2026-04`, `2026-10`, and `2027-04` for 0m, 6m, and 12m.
- Every probability is finite in `[0, 1]` and every binary label matches its learned threshold.
- Population provenance is exactly 5,716 raw last-observed rows plus two missing-raw rows.
- No phase-specific or categorical uncertainty fields exist.
- Final `run_summary.json` is passed, written last, and binds every package/report/CSV checksum.
- `Outcome/ipcch_unified/` is byte-identical before and after the experiment.
- No GCP or Vertex mutation occurred.
- Focused and full FEWSNET test suites pass.
