# FEWSNET Partitioned RF Model Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GCS-first FEWSNET Stage 3 partitioned Random Forest pipeline that first creates an audited, versioned normalized bootstrap panel, then trains 0m, 6m, and 12m models, registers three versioned Vertex AI Models, runs Batch Prediction for the latest valid feature month, and promotes one internally consistent production suite.

**Architecture:** Add a fully isolated `fewsnet_partitioned_rf_pipeline` package with platform-independent normalization/data/model code and narrow Vertex AI adapters. A one-time administrative command writes a new cleaned CSV plus immutable audit without overwriting the raw panel; snapshot staging verifies and uploads both. One digest-pinned image runs both the three-horizon Custom Job trainer and the custom prediction server; the orchestrator registers exact candidate versions, validates three Batch Prediction jobs, then moves production aliases and writes the authoritative GCS suite pointer last.

**Tech Stack:** Python 3.11, pandas, NumPy, scikit-learn RandomForestClassifier, imbalanced-learn SMOTE, joblib, GeoPandas/GeoParquet, FastAPI/Uvicorn, google-cloud-storage, google-cloud-aiplatform `1.161.0`, JSON Schema, pytest, GCS, Vertex AI Custom Jobs, Vertex AI Model Registry, Vertex AI Batch Prediction.

## Global Constraints

- The authoritative design is `docs/superpowers/specs/2026-07-20-partitioned-rf-model-suite-design.md`, including the user-approved bootstrap-normalization amendment; its current checksum is recorded in `PROGRESS.md`. Do not change it during implementation unless the user separately approves another design revision.
- At execution start, use `superpowers:using-git-worktrees`, create a `features/*` branch, and create or reconcile repository-local `PROGRESS.md` before code edits.
- Ensure this plan file is present unchanged in the execution worktree and include it in the first task commit; it remains the task authority throughout execution.
- `PROGRESS.md` is an execution ledger, not approval authority. Record each task's RED/GREEN commands, commit hash, blockers, exact next task, and resume command.
- Preserve the existing IPCCH pipeline. Prefer new files under `fewsnet_partitioned_rf_pipeline/`; modifying any existing function, class, or method requires GitNexus upstream impact analysis before editing.
- Before every commit, run GitNexus `detect_changes(scope="staged")`. If the operational LadybugDB replay error persists, record the failure in `PROGRESS.md`, verify staged paths with Git, and do not include unrelated files.
- Preserve the user's existing unstaged `AGENTS.md`, `CLAUDE.md`, and `.claude/` changes.
- Runtime inputs must be immutable `gs://` objects with generation/checksum evidence. Local Dropbox paths are bootstrap inputs only.
- Never overwrite the raw assembled FEWSNET CSV. Bootstrap normalization writes an explicitly versioned cleaned CSV and audit JSON to different paths.
- Automatic duplicate collapse is allowed only when rows sharing normalized `FEWSNET_admin_code + month` are equal across every column except `Tair_zscore` and `Rainf_zscore`; every other conflict fails closed.
- Deduplicate after stable admin/date sorting and before reproducing the notebook's global 12-row climate rolling means and within-admin sample z-scores. `inspect_panel`, feature preparation, and horizon alignment retain their duplicate-key hard gates.
- Snapshot staging accepts only a normalized panel plus a matching immutable normalization audit. The audit's output checksum/row count must equal the staged panel.
- Snapshot identity is the canonical content digest of the normalized panel, normalization audit, normalized boundaries, admin universe, and schema-relevant metadata; do not use the panel checksum alone for no-op/revision decisions.
- Deployment/source validation and snapshot discovery are preflight. Formal `run_id`/`suite_version` identity and required `error.json`/`run_manifest.json` evidence begin only after successful discovery selects exact-generation snapshot evidence. Earlier failures return/log a structured preflight error and exit nonzero without inventing run or snapshot identity.
- Runtime must not import or invoke the external `Food_Crisis_Cluster` checkout. The external checkout is allowed only for one-time asset copying and parity-fixture generation.
- Use target `fews_ipc_crisis` and horizons exactly `0`, `6`, and `12` months. Horizon means keyed `feature_month=t -> target_month=t+h`; do not reuse the legacy 1/4/8/12 schedule or create horizon by positional row shifting.
- Use one common latest labeled target month and a 36-target-month window for all horizons. Hold out the latest six target months for threshold selection.
- Search thresholds `0.05` through `0.95` inclusive at `0.01` increments, maximize class-1 F1, break ties toward the higher threshold, and use `0.50` only with a recorded fallback reason.
- RF parameters are fixed: `n_estimators=100`, `max_depth=None`, `random_state=5`, `n_jobs=1`.
- Train one pooled RF per horizon. A partition uses pooled fallback when it is unmapped, has fewer than 50 samples, has one class, or lacks a trained partition model.
- Apply SMOTE only inside eligible partition training subsets, with `k_neighbors=min(5, minority_count-1)`. Never expose validation or inference rows to SMOTE.
- Fit the `max_plus` imputer with multiplier `100.0` only on the permitted fit slice. Refit it on the full 36-month window for the final model.
- Preserve the fixed 17-cluster partition asset checksum `4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b` and baseline coverage of 5,365 areas.
- Freeze the ordered feature contract. New source columns never enter automatically. Retain approved reference predictors including `FEWSNET_admin_code`, `lat`, `lon`, and `month`.
- One Vertex AI Custom Job trains all three horizons from one snapshot and one image digest.
- Register three stable parent models: `fewsnet-partitioned-rf-0m`, `fewsnet-partitioned-rf-6m`, and `fewsnet-partitioned-rf-12m`.
- Use `google-cloud-aiplatform==1.161.0`. Vertex assigns numeric Model Version IDs; preserve the immutable suite identity with a deterministic suite-specific version alias plus authoritative manifests, and always retain the exact numeric `@version_id` resource name returned by the service.
- The first upload for a stable parent necessarily receives Vertex's `default` alias. It must still have no `production` alias; later versions use `is_default_version=False` so `default` is not moved.
- Batch Prediction must reference exact candidate version resource names. Do not create an online Endpoint.
- Runtime inference covers exactly the snapshot's latest valid feature month; all earlier rows are training/history inputs only.
- The production suite pointer is authoritative across horizons and must be written last. Any failed horizon blocks all promotion; partial alias changes must be rolled back.
- Serialize only the alias/pointer publication stage with a 900-second generation-safe GCS promotion lease so concurrent rollback cannot clobber another successful suite.
- Re-read the authoritative pointer and repeat the same-month changed-digest revision authorization inside that promotion lease before any alias mutation.
- Real Vertex training and Batch submission retries must reconcile deterministic operation identity after an ambiguous commit-then-raise response: reuse exactly one matching created job, submit only when none exists, and fail closed on multiple or mismatched matches.
- Mark versions `abandoned` only when they are definitively not live production. `PromotionIndeterminate`, or evidence failure after `RELEASED`, preserves lifecycle labels and surfaces an indeterminate/evidence-warning outcome without destructive recovery.
- Immutable writes are retry-safe: on a generation conflict, accept an existing object only when its bytes/checksum exactly match the intended object; otherwise fail closed.
- The four primary v1 deliverable families are one three-model suite, three per-area CSVs, one aggregate training/threshold report, and one run/suite manifest. Do not add maps, workbooks, pooled benchmark reports, or future-target metrics.
- Use `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` for tests.
- Each task follows RED -> GREEN -> focused regression -> commit. Do not combine task commits.

---

## File Structure

### New runtime and packaging files

- `requirements-fewsnet-partitioned-rf.txt` — dependencies for the dedicated shared FEWSNET image.
- `docker/Dockerfile.fewsnet-partitioned-rf` — one digest-pinned training/prediction image.
- `fewsnet_partitioned_rf_pipeline/__init__.py` — package marker and schema version.
- `fewsnet_partitioned_rf_pipeline/config.py` — frozen model constants, horizons, names, timeouts, and path builders.

### New core files

- `fewsnet_partitioned_rf_pipeline/core/types.py` — shared dataclasses and literal status types.
- `fewsnet_partitioned_rf_pipeline/core/normalization.py` — narrow duplicate resolution, notebook-order climate derivation recomputation, and audit validation.
- `fewsnet_partitioned_rf_pipeline/core/data.py` — panel/spatial identity normalization, snapshot inspection, and loading.
- `fewsnet_partitioned_rf_pipeline/core/preprocessing.py` — reference-compatible feature construction, feature contract enforcement, and `MaxPlusImputer`.
- `fewsnet_partitioned_rf_pipeline/core/horizons.py` — keyed feature-target alignment and temporal splits.
- `fewsnet_partitioned_rf_pipeline/core/partitions.py` — fixed-map validation, coverage, routing, and fallback states.
- `fewsnet_partitioned_rf_pipeline/core/thresholds.py` — deterministic global threshold search.
- `fewsnet_partitioned_rf_pipeline/core/training.py` — pooled/partition RF fitting, SMOTE, and three-horizon training.
- `fewsnet_partitioned_rf_pipeline/core/inference.py` — `PartitionedRFPredictor` and formal prediction rows.
- `fewsnet_partitioned_rf_pipeline/core/package.py` — joblib package write/load, checksums, and dependency metadata.
- `fewsnet_partitioned_rf_pipeline/core/validation.py` — package, Batch output, and suite release gates.

### New Vertex and CLI files

- `fewsnet_partitioned_rf_pipeline/vertex/storage.py` — binary/text local fake and GCS artifact-store adapters.
- `fewsnet_partitioned_rf_pipeline/vertex/training_job.py` — Vertex Custom Job spec/submission adapter.
- `fewsnet_partitioned_rf_pipeline/vertex/predictor_server.py` — Vertex custom-container HTTP server.
- `fewsnet_partitioned_rf_pipeline/vertex/registry.py` — stable parent model and new-version registration adapter.
- `fewsnet_partitioned_rf_pipeline/vertex/batch_prediction.py` — exact-version Batch Prediction jobs and raw-output normalization.
- `fewsnet_partitioned_rf_pipeline/vertex/promotion.py` — version alias movement, rollback, and final GCS publication.
- `fewsnet_partitioned_rf_pipeline/cli/stage_snapshot.py` — optional initial local-to-GCS snapshot bootstrap.
- `fewsnet_partitioned_rf_pipeline/cli/normalize_panel.py` — local versioned panel normalization and audit entrypoint.
- `fewsnet_partitioned_rf_pipeline/cli/train.py` — in-container three-horizon training worker.
- `fewsnet_partitioned_rf_pipeline/cli/infer.py` — Batch input preparation and normalized output validation.
- `fewsnet_partitioned_rf_pipeline/cli/run_latest.py` — Cloud Run-compatible end-to-end orchestrator.

### New immutable assets and schemas

- `fewsnet_partitioned_rf_pipeline/assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv`
- `fewsnet_partitioned_rf_pipeline/assets/partitions/partition_manifest.json`
- `fewsnet_partitioned_rf_pipeline/assets/feature_contracts/fewsnet_stage3_v1.json`
- `fewsnet_partitioned_rf_pipeline/schemas/source-snapshot.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/panel-normalization.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/deployment.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/model-package.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/training-report.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/prediction-record.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/run-manifest.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/suite-manifest.schema.json`
- `fewsnet_partitioned_rf_pipeline/schemas/__init__.py`

### New tests, fixtures, tools, and documentation

- `tests/fewsnet_partitioned_rf/` — focused unit, contract, integration, and optional live GCP tests.
- `tests/fewsnet_partitioned_rf/test_panel_normalization.py` — deduplication, audit, parity, and real-source acceptance coverage.
- `tests/fixtures/fewsnet_partitioned_rf/` — small panels, manifests, Batch JSONL, and frozen parity fixture.
- `tools/build_fewsnet_stage3_parity_fixture.py` — one-time developer tool that calls the external reference checkout and writes a checked-in fixture.
- `docs/09_fewsnet_partitioned_rf_runbook.md` — staging, training, registry, Batch, rollback, and recovery runbook.

---

### Task 1: Establish the isolated runtime package and immutable partition asset

**Files:**
- Create: `requirements-fewsnet-partitioned-rf.txt`
- Create: `fewsnet_partitioned_rf_pipeline/__init__.py`
- Create: `fewsnet_partitioned_rf_pipeline/config.py`
- Create: `fewsnet_partitioned_rf_pipeline/assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv`
- Create: `fewsnet_partitioned_rf_pipeline/assets/partitions/partition_manifest.json`
- Create: `tests/fewsnet_partitioned_rf/__init__.py`
- Create: `tests/fewsnet_partitioned_rf/test_runtime_foundation.py`
- Add unchanged to the execution branch: `docs/superpowers/plans/2026-07-20-fewsnet-partitioned-rf-model-suite.md`
- Create or update during execution: `PROGRESS.md`

**Interfaces:**
- Produces `HORIZON_MONTHS`, `HORIZON_KEYS`, `RF_PARAMS`, `PARTITION_MIN_SAMPLES`, `THRESHOLD_GRID`, `PARENT_MODEL_IDS`, `PARTITION_ASSET_PATH`, `PARTITION_ASSET_SHA256`, and `PROMOTION_LEASE_SECONDS` from `config.py`.
- Produces a byte-identical fixed partition CSV and auditable JSON manifest consumed by Tasks 8, 10, and 12.

- [ ] **Step 1: Create the execution ledger and write the failing foundation test**

Create `PROGRESS.md` with the approved spec/plan paths, active worktree/branch, all task statuses set to `pending`, and Task 1 as `in progress`.

Create `tests/fewsnet_partitioned_rf/test_runtime_foundation.py`:

```python
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARTITION = ROOT / (
    "fewsnet_partitioned_rf_pipeline/assets/partitions/"
    "cluster_mapping_k40_nc17_general_refined_contig3.csv"
)


def test_dedicated_requirements_pin_model_serialization_stack():
    requirements = (ROOT / "requirements-fewsnet-partitioned-rf.txt").read_text()
    for requirement in (
        "scikit-learn==1.8.0",
        "joblib==1.5.3",
        "imbalanced-learn==0.14.0",
        "fastapi==0.116.1",
        "uvicorn==0.35.0",
        "geopandas==1.1.1",
        "pyarrow==20.0.0",
        "google-cloud-aiplatform==1.161.0",
        "google-cloud-storage==3.13.0",
        "jsonschema==4.26.0",
        "pytest==9.1.1",
    ):
        assert requirement in requirements
    assert "-r requirements-cloud.txt" not in requirements


def test_fixed_partition_asset_has_approved_identity():
    digest = hashlib.sha256(PARTITION.read_bytes()).hexdigest()
    assert digest == "4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b"
    manifest = json.loads(PARTITION.with_name("partition_manifest.json").read_text())
    assert manifest["mapped_area_count"] == 5365
    assert manifest["cluster_ids"] == list(range(17))
    assert manifest["sha256"] == digest
```

- [ ] **Step 2: Run the foundation test to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/fewsnet_partitioned_rf/test_runtime_foundation.py \
  -q -p no:cacheprovider
```

Expected: FAIL because the dedicated requirements, package, and partition assets do not exist.

- [ ] **Step 3: Add the dedicated dependency file and frozen constants**

Create `requirements-fewsnet-partitioned-rf.txt`:

```text
pandas==3.0.0
numpy==2.4.2
scikit-learn==1.8.0
joblib==1.5.3
imbalanced-learn==0.14.0
geopandas==1.1.1
pyarrow==20.0.0
fastapi==0.116.1
uvicorn==0.35.0
httpx==0.28.1
google-cloud-aiplatform==1.161.0
google-cloud-storage==3.13.0
jsonschema==4.26.0
pytest==9.1.1
```

Create `fewsnet_partitioned_rf_pipeline/__init__.py`:

```python
"""Operational FEWSNET fixed-partition Random Forest suite."""

SCHEMA_VERSION = "fewsnet-partitioned-rf-v1"
```

Create `fewsnet_partitioned_rf_pipeline/config.py`:

```python
from pathlib import Path

HORIZON_MONTHS = (0, 6, 12)
HORIZON_KEYS = {0: "0m", 6: "6m", 12: "12m"}
TARGET_COLUMN = "fews_ipc_crisis"
ADMIN_SOURCE_COLUMN = "FEWSNET_admin_code"
ADMIN_CANONICAL_COLUMN = "admin_code"
TRAIN_WINDOW_MONTHS = 36
THRESHOLD_VALIDATION_MONTHS = 6
THRESHOLD_GRID = tuple(round(value / 100, 2) for value in range(5, 96))
PARTITION_MIN_SAMPLES = 50
SMOTE_MAX_NEIGHBORS = 5
PROMOTION_LEASE_SECONDS = 900
RF_PARAMS = {
    "n_estimators": 100,
    "max_depth": None,
    "random_state": 5,
    "n_jobs": 1,
}
PARENT_MODEL_IDS = {
    "0m": "fewsnet-partitioned-rf-0m",
    "6m": "fewsnet-partitioned-rf-6m",
    "12m": "fewsnet-partitioned-rf-12m",
}
PACKAGE_ROOT = Path(__file__).resolve().parent
PARTITION_ASSET_PATH = PACKAGE_ROOT / (
    "assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv"
)
PARTITION_ASSET_SHA256 = (
    "4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b"
)
FEATURE_CONTRACT_PATH = PACKAGE_ROOT / (
    "assets/feature_contracts/fewsnet_stage3_v1.json"
)
```

- [ ] **Step 4: Copy and describe the approved partition asset**

Run the exact copy:

```bash
mkdir -p fewsnet_partitioned_rf_pipeline/assets/partitions
cp -a \
  "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/Food_Crisis_Cluster/paper_reproducibility_package/stage3_results/georf_fs1/refined/cluster_mapping_k40_nc17_general_refined_contig3.csv" \
  "fewsnet_partitioned_rf_pipeline/assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv"
```

Create `partition_manifest.json`:

```json
{
  "schema_version": "fewsnet-partition-map-v1",
  "source_repository": "Food_Crisis_Cluster",
  "source_git_commit": "1ecf180669568bbf9eb2129683108162902a415a",
  "source_relative_path": "paper_reproducibility_package/stage3_results/georf_fs1/refined/cluster_mapping_k40_nc17_general_refined_contig3.csv",
  "sha256": "4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b",
  "mapped_area_count": 5365,
  "cluster_count": 17,
  "cluster_ids": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
}
```

- [ ] **Step 5: Create the implementation virtual environment and verify GREEN**

Run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-fewsnet-partitioned-rf.txt
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_runtime_foundation.py \
  -q -p no:cacheprovider
```

Expected: `2 passed`.

- [ ] **Step 6: Commit Task 1**

```bash
git add \
  docs/superpowers/plans/2026-07-20-fewsnet-partitioned-rf-model-suite.md \
  requirements-fewsnet-partitioned-rf.txt \
  fewsnet_partitioned_rf_pipeline \
  tests/fewsnet_partitioned_rf \
  PROGRESS.md
git commit -m "feat: establish FEWSNET partitioned RF runtime"
```

---

### Task 2: Define shared types and machine-readable contracts

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/__init__.py`
- Create: `fewsnet_partitioned_rf_pipeline/core/types.py`
- Create: `fewsnet_partitioned_rf_pipeline/schemas/__init__.py`
- Create: the original seven JSON schemas listed in File Structure; Task 6 adds the approved `panel-normalization` schema and extends the source-snapshot contract.
- Create: `tests/fixtures/fewsnet_partitioned_rf/source_snapshot_valid.json`
- Create: `tests/fixtures/fewsnet_partitioned_rf/deployment_valid.json`
- Create: `tests/fewsnet_partitioned_rf/test_contracts.py`

**Interfaces:**
- Produces `ObjectRef`, `SnapshotManifest`, `FeatureContract`, `PartitionStatus`, `ThresholdResult`, `RegisteredModelVersion`, `BatchJobRef`, and `RunPhase`.
- Produces `validate_payload(schema_name: str, payload: dict) -> None` for every later manifest/report writer and `validate_deployment(payload: dict) -> None` for cross-field image-digest validation.

- [ ] **Step 1: Write failing contract and dataclass tests**

Create `tests/fewsnet_partitioned_rf/test_contracts.py` with assertions that:

```python
import json
from pathlib import Path

import pytest

from fewsnet_partitioned_rf_pipeline.core.types import ObjectRef, RunPhase
from fewsnet_partitioned_rf_pipeline.schemas import validate_deployment, validate_payload


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/fewsnet_partitioned_rf"


def test_source_snapshot_fixture_validates():
    payload = json.loads((FIXTURES / "source_snapshot_valid.json").read_text())
    validate_payload("source-snapshot", payload)


def test_source_snapshot_requires_immutable_object_generation():
    payload = json.loads((FIXTURES / "source_snapshot_valid.json").read_text())
    payload["panel"].pop("generation")
    with pytest.raises(ValueError, match="generation"):
        validate_payload("source-snapshot", payload)


def test_shared_types_freeze_object_identity_and_run_phases():
    ref = ObjectRef("gs://bucket/object", "7", "a" * 64, 12)
    assert ref.generation == "7"
    assert RunPhase.RELEASED.value == "RELEASED"


def test_deployment_requires_digest_pinned_image_and_matching_digest():
    payload = json.loads((FIXTURES / "deployment_valid.json").read_text())
    validate_deployment(payload)
    payload["container_image_digest"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="container_image_digest"):
        validate_deployment(payload)
```

- [ ] **Step 2: Run contract tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  -q -p no:cacheprovider
```

Expected: import/fixture failures.

- [ ] **Step 3: Implement the shared dataclasses and status vocabulary**

Create `core/types.py` with these exact public types:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


@dataclass(frozen=True)
class ObjectRef:
    uri: str
    generation: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_id: str
    created_at_utc: str
    snapshot_content_sha256: str
    panel: ObjectRef
    boundaries: ObjectRef
    admin_universe: ObjectRef
    row_count: int
    area_count: int
    spatial_feature_count: int
    crs: str
    latest_feature_month: str
    latest_label_month: str
    source_identity: dict[str, str]
    admin_code_mapping: dict[str, str]


@dataclass(frozen=True)
class FeatureContract:
    schema_version: str
    transformation_version: str
    feature_columns: tuple[str, ...]
    feature_dtypes: tuple[str, ...]
    required_source_columns: tuple[str, ...]
    iso_mapping: dict[str, int]
    source_columns_sha256: str
    feature_schema_sha256: str


PartitionStatus = Literal[
    "partition_model",
    "pooled_unmapped",
    "pooled_small_partition",
    "pooled_single_class",
    "pooled_missing_partition_model",
]


@dataclass(frozen=True)
class ThresholdResult:
    threshold: float
    precision: float | None
    recall: float | None
    f1: float | None
    support: int
    positive_cases: int
    fallback_reason: str | None


@dataclass(frozen=True)
class RegisteredModelVersion:
    horizon_key: str
    parent_model_resource_name: str
    version_resource_name: str
    version_id: str
    suite_version_alias: str
    artifact_uri: str


@dataclass(frozen=True)
class BatchJobRef:
    horizon_key: str
    job_resource_name: str
    model_version_resource_name: str
    input_uri: str
    destination_prefix: str
    gcs_output_directory: str | None = None


class RunPhase(str, Enum):
    DISCOVERED = "DISCOVERED"
    INPUT_VALIDATED = "INPUT_VALIDATED"
    TRAINING = "TRAINING"
    PACKAGED = "PACKAGED"
    REGISTERED_CANDIDATE = "REGISTERED_CANDIDATE"
    BATCH_PREDICTING = "BATCH_PREDICTING"
    OUTPUT_VALIDATED = "OUTPUT_VALIDATED"
    PROMOTING = "PROMOTING"
    RELEASED = "RELEASED"
    NOOP = "NOOP"
    FAILED = "FAILED"
```

- [ ] **Step 4: Add schema loading and exact schema requirements**

Create `schemas/__init__.py`:

```python
import json
from importlib.resources import files

from jsonschema import Draft202012Validator


def load_schema(name: str) -> dict:
    resource = files(__package__).joinpath(f"{name}.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_payload(name: str, payload: dict) -> None:
    errors = sorted(
        Draft202012Validator(load_schema(name)).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"{name} contract failed at {path}: {first.message}")


def validate_deployment(payload: dict) -> None:
    validate_payload("deployment", payload)
    digest = payload["container_image_digest"]
    if not payload["container_image_uri"].endswith(f"@{digest}"):
        raise ValueError(
            "container_image_digest must equal the digest suffix of container_image_uri"
        )
```

Create Draft 2020-12 schemas with `additionalProperties: false` at every fixed object level and these required fields:

- `source-snapshot`: `schema_version`, `snapshot_id`, `created_at_utc`, `snapshot_content_sha256`, `panel`, `boundaries`, `admin_universe`, `row_count`, `area_count`, `spatial_feature_count`, `crs`, `latest_feature_month`, `latest_label_month`, `source_identity`, `admin_code_mapping`; each object ref requires `uri`, `generation`, `sha256`, `size_bytes`. `source_identity` requires `panel_bootstrap_path`, `boundaries_bootstrap_path`, `panel_source_type`, and `boundaries_source_type`; `admin_code_mapping` requires `panel`, `boundaries`, and `canonical`.
- `deployment`: `schema_version`, `project_id`, `region`, `object_store_root_uri`, `orchestrator_service_account`, `training_service_account`, `batch_prediction_service_account`, `container_image_uri`, `container_image_digest`, `source_git_commit`, `parent_model_ids`, `training_machine_type`, `batch_machine_type`, `training_timeout_seconds`, `batch_timeout_seconds`, `max_retries`. The schema requires a 40-character lowercase-hex source commit, requires `container_image_uri` to end in `@sha256:` followed by 64 lowercase hexadecimal characters, and requires `container_image_digest` to match `^sha256:[0-9a-f]{64}$`; `validate_deployment` then compares the two image values exactly because JSON Schema cannot express that cross-field equality.
- `model-package`: package identity, snapshot identity, horizon, target month, feature/partition checksums, threshold, dependency versions, image digest, files, and status.
- `training-report`: suite version, training/validation month ranges, per-horizon thresholds, cluster states, SMOTE results, and fallback counts.
- `prediction-record`: the twelve formal CSV fields from the design, with `cluster_id` as null or integer `0..16`, probability bounds, binary class, `YYYY-MM` month patterns, and enumerated `prediction_source`.
- `run-manifest`: `run_id`, `suite_version`, `phase`, `status`, snapshot/model/Batch references, hard gates, timestamps, retry attempts, and optional failure; candidate-only smoke completion uses phase `OUTPUT_VALIDATED` and status `candidate_validated` without adding a production state.
- `suite-manifest`: the exact three horizon model versions, exact three prediction objects, input/image/partition identities, alias state, and release timestamp.

Add valid fixtures using `gs://bucket/...` URIs, 64-character checksums, generations as strings, and project `food-crisis-modeling` in region `us-central1`.

- [ ] **Step 5: Verify all schemas and types**

Run the Step 2 command.

Expected: `4 passed`.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core \
  fewsnet_partitioned_rf_pipeline/schemas \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  tests/fixtures/fewsnet_partitioned_rf \
  PROGRESS.md
git commit -m "feat: define FEWSNET suite contracts"
```

---

### Task 3: Add binary-safe local and GCS artifact storage

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/vertex/__init__.py`
- Create: `fewsnet_partitioned_rf_pipeline/vertex/storage.py`
- Create: `tests/fewsnet_partitioned_rf/test_storage.py`

**Interfaces:**
- Produces `ArtifactStore` protocol with `put_bytes`, `read_bytes(uri, generation=None)`, `put_text`, `read_text(uri, generation=None)`, `upload_file`, `download_file`, `get_ref`, and `list`; callers that make release/discovery decisions always read the exact generation returned by `get_ref`/`list`.
- Produces `LocalArtifactStore(root)` for deterministic tests and `GCSArtifactStore.from_default()` for runtime.
- Produces `put_immutable_or_verify(store, uri, data) -> ObjectRef`, `upload_file_immutable_or_verify(store, path, uri) -> ObjectRef`, and `put_mutable_or_verify(store, uri, data, expected_generation) -> ObjectRef`, used by snapshot, package, report, and release writers to make exact retries safe without loading large panel/package files into memory.

- [ ] **Step 1: Write RED tests for binary round trips and generation conflicts**

```python
from pathlib import Path

import pytest

from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    GenerationConflict,
    LocalArtifactStore,
    put_immutable_or_verify,
    put_mutable_or_verify,
    upload_file_immutable_or_verify,
)


def test_local_store_round_trips_binary_and_records_sha256(tmp_path):
    store = LocalArtifactStore(tmp_path)
    ref = store.put_bytes("gs://bucket/models/model.joblib", b"\x00model", if_generation_match=0)
    assert ref.generation == "1"
    assert ref.size_bytes == 6
    assert store.read_bytes(ref.uri) == b"\x00model"
    assert store.get_ref(ref.uri) == ref


def test_local_store_rejects_immutable_overwrite(tmp_path):
    store = LocalArtifactStore(tmp_path)
    store.put_text("gs://bucket/object.json", "{}", if_generation_match=0)
    with pytest.raises(GenerationConflict):
        store.put_text("gs://bucket/object.json", "{\"x\":1}", if_generation_match=0)


def test_local_store_upload_download_preserves_file_bytes(tmp_path):
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    source.write_bytes(b"artifact")
    store = LocalArtifactStore(tmp_path / "objects")
    ref = store.upload_file(source, "gs://bucket/artifact.bin", if_generation_match=0)
    store.download_file(ref.uri, target, generation=ref.generation)
    assert target.read_bytes() == b"artifact"


def test_immutable_retry_accepts_identical_bytes_but_rejects_drift(tmp_path):
    store = LocalArtifactStore(tmp_path)
    first = put_immutable_or_verify(store, "gs://bucket/object", b"same")
    assert put_immutable_or_verify(store, "gs://bucket/object", b"same") == first
    with pytest.raises(GenerationConflict, match="different bytes"):
        put_immutable_or_verify(store, "gs://bucket/object", b"changed")


def test_immutable_file_retry_compares_sha256_and_size(tmp_path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"large-artifact")
    store = LocalArtifactStore(tmp_path / "objects")
    first = upload_file_immutable_or_verify(store, path, "gs://bucket/large.bin")
    assert upload_file_immutable_or_verify(store, path, first.uri) == first


def test_mutable_retry_accepts_already_committed_intended_bytes(tmp_path):
    store = LocalArtifactStore(tmp_path)
    first = put_mutable_or_verify(store, "gs://bucket/current.json", b"old", 0)
    updated = put_mutable_or_verify(
        store, first.uri, b"new", expected_generation=first.generation
    )
    assert put_mutable_or_verify(
        store, first.uri, b"new", expected_generation=first.generation
    ) == updated
```

- [ ] **Step 2: Run storage tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_storage.py \
  -q -p no:cacheprovider
```

Expected: module import failure.

- [ ] **Step 3: Implement the local store and protocol**

Implement `storage.py` around `ObjectRef` with SHA-256 computed from bytes. The immutable write check is:

```python
def _check_generation(current: int, expected: str | int | None, uri: str) -> None:
    if expected is not None and int(expected) != current:
        raise GenerationConflict(
            f"generation precondition failed for {uri}: expected {expected}, current {current}"
        )
```

`LocalArtifactStore` maps `gs://bucket/object` to `root/bucket/object`, stores generation counters in memory, and writes bytes with `Path.write_bytes`. `put_text` delegates to `put_bytes(content.encode("utf-8"))`.

Implement retry-safe immutable creation exactly as:

```python
def put_immutable_or_verify(store, uri: str, data: bytes) -> ObjectRef:
    intended_sha256 = hashlib.sha256(data).hexdigest()
    try:
        return store.put_bytes(uri, data, if_generation_match=0)
    except GenerationConflict:
        existing = store.get_ref(uri)
        if existing.sha256 != intended_sha256 or existing.size_bytes != len(data):
            raise GenerationConflict(f"immutable object already exists with different bytes: {uri}")
        return existing


def upload_file_immutable_or_verify(store, path: Path, uri: str) -> ObjectRef:
    intended_sha256 = sha256_file(path)
    intended_size = path.stat().st_size
    try:
        return store.upload_file(path, uri, if_generation_match=0)
    except GenerationConflict:
        existing = store.get_ref(uri)
        if existing.sha256 != intended_sha256 or existing.size_bytes != intended_size:
            raise GenerationConflict(f"immutable object already exists with different bytes: {uri}")
        return existing


def put_mutable_or_verify(
    store, uri: str, data: bytes, expected_generation: str | int
) -> ObjectRef:
    intended_sha256 = hashlib.sha256(data).hexdigest()
    try:
        return store.put_bytes(uri, data, if_generation_match=expected_generation)
    except GenerationConflict:
        existing = store.get_ref(uri)
        if existing.sha256 != intended_sha256 or existing.size_bytes != len(data):
            raise
        return existing
```

- [ ] **Step 4: Implement the GCS adapter**

`GCSArtifactStore` must use:

```python
blob.upload_from_string(data, if_generation_match=expected)
blob.upload_from_filename(str(path), if_generation_match=expected)
blob.download_as_bytes(if_generation_match=int(generation) if generation else None)
blob.download_to_filename(str(path), if_generation_match=int(generation) if generation else None)
blob.reload()
```

Before each upload, compute SHA-256 locally and store it as blob custom metadata key `sha256`; `get_ref` reloads the blob and requires that metadata plus generation and size. Convert `PreconditionFailed` to `GenerationConflict`, return `ObjectRef` with stringified `blob.generation`, and never accept non-`gs://` URIs. Missing SHA-256 metadata on an object that is being considered for retry reuse is a hard failure rather than an implicit match.

- [ ] **Step 5: Verify storage GREEN**

Run the Step 2 command.

Expected: `6 passed`.

- [ ] **Step 6: Commit Task 3**

```bash
git add \
  fewsnet_partitioned_rf_pipeline/vertex \
  tests/fewsnet_partitioned_rf/test_storage.py \
  PROGRESS.md
git commit -m "feat: add FEWSNET artifact storage"
```

---

### Task 4: Stage and validate immutable FEWSNET input snapshots

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/data.py`
- Create: `fewsnet_partitioned_rf_pipeline/cli/__init__.py`
- Create: `fewsnet_partitioned_rf_pipeline/cli/stage_snapshot.py`
- Create: `tests/fewsnet_partitioned_rf/test_snapshot_staging.py`

**Interfaces:**
- Produces `normalize_admin_code(value) -> str`.
- Produces `inspect_panel(path: Path) -> dict`, `normalize_boundaries(path: Path, output_parquet: Path) -> dict`, and `stage_snapshot(...) -> SnapshotManifest`.
- `stage_snapshot` writes panel, GeoParquet, admin universe, and manifest under `inputs/snapshots/{snapshot_id}/`, with the manifest written last.
- `snapshot_content_sha256` is a canonical SHA-256 over the three content checksums plus row/area/CRS/month/mapping metadata; it excludes GCS generations and `created_at_utc` so byte-identical restaging remains a no-op.
- Task 6 preserves `inspect_panel`'s duplicate hard gate and extends the final snapshot interface to require a matching normalization-audit object, bumping the snapshot schema to v2.

- [ ] **Step 1: Write failing snapshot tests**

Use a four-row CSV with two areas and two months, plus a two-feature GeoDataFrame. Assert:

```python
def test_stage_snapshot_writes_manifest_last_and_preserves_area_identity(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")

    manifest = stage_snapshot(
        panel_path=panel,
        boundaries_path=boundaries,
        destination_root="gs://bucket/fewsnet_partitioned_rf",
        store=store,
        created_at_utc="2026-07-20T00:00:00Z",
    )

    assert manifest.row_count == 4
    assert manifest.area_count == 2
    assert manifest.spatial_feature_count == 2
    assert manifest.latest_feature_month == "2026-04"
    assert manifest.latest_label_month == "2026-03"
    assert len(manifest.snapshot_content_sha256) == 64
    assert manifest.admin_code_mapping == {
        "panel": "FEWSNET_admin_code",
        "boundaries": "admin_code",
        "canonical": "admin_code",
    }
    assert store.write_order[-1].endswith("source_manifest.json")
```

Add failures for duplicate `FEWSNET_admin_code + date`, panel/spatial area-set mismatch, missing `admin_code`, and a CRS other than EPSG:4326.

- [ ] **Step 2: Run snapshot tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_snapshot_staging.py \
  -q -p no:cacheprovider
```

Expected: missing module/functions.

- [ ] **Step 3: Implement streaming panel inspection**

`inspect_panel` reads only `FEWSNET_admin_code`, `date`, and `fews_ipc_crisis` in chunks. It must normalize dates to monthly periods, reject duplicate area-period keys across chunks, compute row/area counts, and derive latest months:

```python
latest_feature = max(periods)
latest_label = max(period for period, labeled in labeled_periods if labeled)
```

`normalize_admin_code` strips whitespace and converts integer-like values such as `"12.0"` to `"12"` without changing non-numeric identifiers.

- [ ] **Step 4: Implement spatial normalization and immutable upload**

Use `geopandas.read_file`, require exactly one non-null geometry per unique normalized `admin_code`, require `str(gdf.crs).upper() == "EPSG:4326"`, sort by `admin_code`, and write GeoParquet. Write `admin_universe.csv` with one `admin_code` column.

After writing the normalized GeoParquet and `admin_universe.csv`, compute their SHA-256 values locally. Canonically JSON-encode this payload with sorted keys and compact separators, then hash it:

```python
identity_payload = {
    "schema_version": "fewsnet-source-snapshot-v1",
    "panel_sha256": panel_sha256,
    "boundaries_sha256": boundaries_sha256,
    "admin_universe_sha256": admin_universe_sha256,
    "row_count": panel_info["row_count"],
    "area_count": panel_info["area_count"],
    "spatial_feature_count": boundary_info["feature_count"],
    "crs": "EPSG:4326",
    "latest_feature_month": panel_info["latest_feature_month"],
    "latest_label_month": panel_info["latest_label_month"],
    "admin_code_mapping": {
        "panel": "FEWSNET_admin_code",
        "boundaries": "admin_code",
        "canonical": "admin_code",
    },
}
snapshot_content_sha256 = hashlib.sha256(
    json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
```

Build `snapshot_id` as:

```python
latest_feature = panel_info["latest_feature_month"]
snapshot_id = (
    f"fewsnet-{latest_feature.replace('-', '')}-"
    f"{snapshot_content_sha256[:8]}"
)
```

Set `source_identity` keys exactly to `panel_bootstrap_path`, `boundaries_bootstrap_path`, `panel_source_type="assembled_fewsnet_csv"`, and `boundaries_source_type="fewsnet_admin_boundaries_v3"`. Upload the panel, GeoParquet, and admin-universe files with `upload_file_immutable_or_verify`, construct the schema-valid manifest, and upload the small `source_manifest.json` bytes last with `put_immutable_or_verify`.

- [ ] **Step 5: Add the administrative CLI**

`stage_snapshot.py` accepts exactly:

```text
--panel
--boundaries
--destination-root
--created-at-utc
```

It creates `GCSArtifactStore.from_default()`, calls `stage_snapshot`, prints the manifest URI as JSON, and returns nonzero on validation or generation conflict.

- [ ] **Step 6: Verify snapshot GREEN and CLI help**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_snapshot_staging.py \
  -q -p no:cacheprovider
.venv/bin/python -m fewsnet_partitioned_rf_pipeline.cli.stage_snapshot --help
```

Expected: focused tests pass and CLI prints `usage:`.

- [ ] **Step 7: Commit Task 4**

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/data.py \
  fewsnet_partitioned_rf_pipeline/cli \
  tests/fewsnet_partitioned_rf/test_snapshot_staging.py \
  PROGRESS.md
git commit -m "feat: stage immutable FEWSNET snapshots"
```

---

### Task 5: Build the frozen Stage 3 feature contract and leak-free feature frame

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/preprocessing.py`
- Create: `fewsnet_partitioned_rf_pipeline/assets/feature_contracts/fewsnet_stage3_v1.json`
- Create: `tests/fewsnet_partitioned_rf/test_preprocessing.py`

**Interfaces:**
- Produces `Stage3FeatureBuilder.fit(panel) -> FeatureContract` and `transform(panel, contract) -> pandas.DataFrame`.
- Output retains `admin_code`, `feature_month`, `fews_ipc_crisis`, and every ordered predictor from the contract.
- Horizon is not encoded through dynamic `*_lag{horizon}m` columns; Tasks 7 and 10 express horizon only through keyed target alignment.
- The generated contract records `feature_schema_sha256` from ordered `(name, dtype)` pairs; the checked-in contract itself is the frozen approved feature order used by every horizon.

- [ ] **Step 1: Write RED tests for feature identity, calendar lags, and frozen columns**

Tests must assert:

```python
def test_feature_builder_preserves_approved_reference_predictors_and_calendar_lags():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)
    frame = builder.transform(panel, contract)

    for name in (
        "FEWSNET_admin_code",
        "lat",
        "lon",
        "month",
        "fews_ha",
        "fews_ipc_crisis_lag_4",
        "fews_ipc_lag_12",
        "WFP_Price_m4",
        "WFP_Price_m12",
        "nightlight_m12",
        "EVI_l12",
    ):
        assert name in contract.feature_columns
    assert "fews_ipc_crisis" not in contract.feature_columns
    assert "fews_ipc" not in contract.feature_columns
    assert "fews_proj_med" not in contract.feature_columns


def test_transform_rejects_new_or_missing_contract_features():
    panel = raw_panel_fixture()
    contract = Stage3FeatureBuilder().fit(panel)
    broken = panel.drop(columns=["lat"])
    with pytest.raises(ValueError, match="lat"):
        Stage3FeatureBuilder().transform(broken, contract)
```

Use a fixture with a missing calendar month and assert a 4-month lag is keyed by calendar month rather than the fourth previous row. Add tests that duplicate names in `contract.feature_columns` fail, positive/negative infinity are converted to `NaN` for Task 9, and no scaler/standardizer is applied.

- [ ] **Step 2: Run preprocessing tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_preprocessing.py \
  -q -p no:cacheprovider
```

Expected: missing builder.

- [ ] **Step 3: Implement deterministic source normalization**

Use these exact dropped raw columns:

```python
DROP_SOURCE_COLUMNS = {
    "unit_name", "ADMIN0", "ADMIN1", "ADMIN2", "ADMIN3", "ISO3",
    "fews_ipc_adjusted", "fews_proj_med_adjusted", "fews_proj_near",
    "fews_proj_near_ha", "fews_proj_med", "fews_proj_med_ha",
}
```

Normalize AEZ booleans, build a sorted `ISO -> integer` mapping, retain numeric `FEWSNET_admin_code`, create sorted year and month dummy columns, and create calendar-keyed lags by shifting the right-side period before a one-to-one merge:

```python
def add_calendar_lag(frame, value_column, months, output_column):
    right = frame[["admin_code", "feature_month", value_column]].copy()
    right["feature_month"] = right["feature_month"] + months
    right = right.rename(columns={value_column: output_column})
    return frame.merge(
        right,
        on=["admin_code", "feature_month"],
        how="left",
        validate="one_to_one",
    )
```

Create `fews_ipc_crisis_lag_{4,8,12}`, `fews_ipc_lag_{4,8,12}`, then drop contemporaneous raw `fews_ipc`. Create `WFP_Price_m4`, `WFP_Price_m12`, `nightlight_m12`, and `EVI_l1` through `EVI_l12`. This deliberately preserves the approved reference behavior: the reference feature-engineering helpers return inside their loops, so only `WFP_Price`, `nightlight`, and `EVI` receive those derived columns; do not silently generate analogous columns for the remaining configured variables. Rolling sums must reindex each area to a complete monthly PeriodIndex before `shift(1).rolling(window, min_periods=window).sum()`.

- [ ] **Step 4: Freeze the contract and reject automatic feature drift**

`fit` is an administrative contract-generation operation only. It records ordered feature columns, all feature dtypes as `float64`, required raw columns, sorted ISO mapping, source column checksum, feature schema checksum, and transformation version `stage3-direct-alignment-v1`. Before computing checksums, encode `ISO` and drop it, build then exclude `AEZ_group`, `ISO_encoded`, and `AEZ_country_group` exactly as the reference path does, and create the approved year/month dummy columns in sorted numeric order. Runtime training/inference always loads the checked-in contract and calls `transform`; it never refits the allowlist or ISO mapping from a new snapshot. `transform` rejects duplicate contract names, reindexes to exactly `contract.feature_columns`, raises for missing required raw inputs, unseen ISO values, unseen year/month dummy categories, or non-coercible predictors, ignores undeclared extra source columns, verifies the contract checksums, converts infinity to `NaN`, and leaves missing values for Task 9's imputer. No scaler is fitted or serialized.

Generate the initial contract from the approved panel:

```bash
.venv/bin/python -m fewsnet_partitioned_rf_pipeline.core.preprocessing \
  --panel "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.csv" \
  --output fewsnet_partitioned_rf_pipeline/assets/feature_contracts/fewsnet_stage3_v1.json
```

The command must print the feature count and verify the required/excluded names asserted in Step 1 before writing.

- [ ] **Step 5: Verify preprocessing GREEN**

Run the Step 2 command and then validate the generated JSON with `python3 -m json.tool`.

Expected: focused tests pass and the contract JSON parses.

- [ ] **Step 6: Commit Task 5**

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/preprocessing.py \
  fewsnet_partitioned_rf_pipeline/assets/feature_contracts \
  tests/fewsnet_partitioned_rf/test_preprocessing.py \
  PROGRESS.md
git commit -m "feat: freeze FEWSNET Stage 3 features"
```

---

### Task 6: Normalize the bootstrap panel and bind its audit into snapshots

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/normalization.py`
- Create: `fewsnet_partitioned_rf_pipeline/cli/normalize_panel.py`
- Create: `fewsnet_partitioned_rf_pipeline/schemas/panel-normalization.schema.json`
- Create: `tests/fewsnet_partitioned_rf/test_panel_normalization.py`
- Create: `tests/fixtures/fewsnet_partitioned_rf/panel_normalization_valid.json`
- Modify: `fewsnet_partitioned_rf_pipeline/core/types.py`
- Modify: `fewsnet_partitioned_rf_pipeline/core/data.py`
- Modify: `fewsnet_partitioned_rf_pipeline/cli/stage_snapshot.py`
- Modify: `fewsnet_partitioned_rf_pipeline/schemas/source-snapshot.schema.json`
- Modify: `tests/fixtures/fewsnet_partitioned_rf/source_snapshot_valid.json`
- Modify: `tests/fewsnet_partitioned_rf/test_contracts.py`
- Modify: `tests/fewsnet_partitioned_rf/test_snapshot_staging.py`
- Update: `PROGRESS.md`
- Generate outside Git without overwriting the raw source:
  `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv`
- Generate outside Git:
  `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json`

**Interfaces:**
- Approved real-source contract: 1,120,730 raw rows become 1,120,728 normalized rows across 5,718 areas by collapsing exactly two compatible duplicate groups for admin `2996` (`2025-10` and `2026-02`).
- Produces `PanelNormalizationResult(output_panel_path, audit_path, raw_row_count, normalized_row_count, duplicate_group_count, removed_row_count, latest_feature_month, latest_label_month, output_sha256)`.
- Produces `normalize_panel(raw_panel_path, output_panel_path, audit_path) -> PanelNormalizationResult` and `validate_normalization_audit(audit_path, panel_path) -> dict`.
- Extends `SnapshotManifest` with required `normalization_audit: ObjectRef` and bumps the snapshot contract to `fewsnet-source-snapshot-v2`.
- Extends `stage_snapshot(..., normalization_audit_path: Path)` so the normalized panel, matching audit, boundaries, and admin universe are immutable snapshot members; `source_manifest.json` remains the final write.
- Preserves `inspect_panel` as a hard duplicate-key gate. No recurring training, inference, feature, or horizon function is allowed to deduplicate rows.

- [ ] **Step 1: Write RED normalization and audit-contract tests**

Create `tests/fewsnet_partitioned_rf/test_panel_normalization.py` with a
notebook-order reference helper and these exact behaviors:

```python
import hashlib
import json

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from fewsnet_partitioned_rf_pipeline.core.normalization import (
    normalize_panel,
    validate_normalization_audit,
)


def _reference_notebook_zscore(frame, source_column):
    rolling = pd.to_numeric(frame[source_column]).rolling(
        window=12,
        min_periods=1,
    ).mean()
    grouped = rolling.groupby(frame["FEWSNET_admin_code"], sort=False)
    return (rolling - grouped.transform("mean")) / grouped.transform(
        "std",
        ddof=1,
    )


def test_normalizer_collapses_derived_only_duplicates_before_climate_recompute(tmp_path):
    raw = write_normalization_fixture(
        tmp_path,
        duplicate_key=(2996, "2025-10-01"),
        duplicate_changes={"Tair_zscore": -99.0, "Rainf_zscore": 99.0},
    )
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    result = normalize_panel(raw, output, audit)
    normalized = pd.read_csv(output)
    payload = validate_normalization_audit(audit, output)

    assert result.raw_row_count == len(normalized) + 1
    assert result.duplicate_group_count == 1
    assert result.removed_row_count == 1
    assert payload["comparison_excluded_columns"] == [
        "Tair_zscore",
        "Rainf_zscore",
    ]
    assert payload["duplicate_groups"][0]["disposition"] == (
        "collapsed_identical_or_derived_only"
    )
    assert normalized.columns.tolist() == pd.read_csv(raw, nrows=0).columns.tolist()
    normalized_keys = normalized.assign(
        feature_month=pd.to_datetime(normalized["date"]).dt.to_period("M")
    )
    assert not normalized_keys.duplicated(
        ["FEWSNET_admin_code", "feature_month"]
    ).any()
    assert_series_equal(
        normalized["Tair_zscore"],
        _reference_notebook_zscore(normalized, "Tair_f_tavg_mean"),
        check_names=False,
        rtol=1e-12,
        atol=1e-12,
    )
    assert_series_equal(
        normalized["Rainf_zscore"],
        _reference_notebook_zscore(normalized, "Rainf_f_tavg_mean"),
        check_names=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_normalizer_rejects_any_non_derived_duplicate_conflict(tmp_path):
    raw = write_normalization_fixture(
        tmp_path,
        duplicate_key=(2996, "2025-10-01"),
        duplicate_changes={"lat": 123.0},
    )
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    with pytest.raises(ValueError, match="2996.*2025-10.*lat"):
        normalize_panel(raw, output, audit)
    assert not output.exists()
    assert not audit.exists()


def test_normalizer_never_overwrites_or_aliases_the_raw_source(tmp_path):
    raw = write_normalization_fixture(tmp_path)
    raw_before = raw.read_bytes()
    audit = tmp_path / "panel.audit.json"

    with pytest.raises(ValueError, match="different from raw"):
        normalize_panel(raw, raw, audit)
    assert raw.read_bytes() == raw_before


def test_audit_validation_rejects_panel_byte_or_row_count_drift(tmp_path):
    raw = write_normalization_fixture(tmp_path)
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"
    normalize_panel(raw, output, audit)
    output.write_bytes(output.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="checksum|size|row_count"):
        validate_normalization_audit(audit, output)
```

The fixture must include at least 13 stably sorted rows across two admin codes,
the six required climate/admin/date columns, one exact duplicate case, one
derived-only-different case, missing climate values, and the original 88-column
ordering behavior. Add schema tests for the checked-in
`panel_normalization_valid.json` and for rejection when a required audit field
is absent.

- [ ] **Step 2: Run normalization tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_panel_normalization.py \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  -q -p no:cacheprovider
```

Expected: collection/import or missing-schema failures; no production file is
edited.

- [ ] **Step 3: Implement deterministic, fail-closed panel normalization**

Create `core/normalization.py` with these constants and public result:

```python
NORMALIZATION_SCHEMA_VERSION = "fewsnet-panel-normalization-v1"
NORMALIZATION_VERSION = "deduplicate-before-global-rolling-zscore-v1"
ADMIN_COLUMN = "FEWSNET_admin_code"
DATE_COLUMN = "date"
COMPARISON_EXCLUDED_COLUMNS = ("Tair_zscore", "Rainf_zscore")
CLIMATE_DERIVATIONS = {
    "Tair_f_tavg_mean": "Tair_zscore",
    "Rainf_f_tavg_mean": "Rainf_zscore",
}
ROLLING_WINDOW = 12
ROLLING_MIN_PERIODS = 1
ZSCORE_DDOF = 1


@dataclass(frozen=True)
class PanelNormalizationResult:
    output_panel_path: Path
    audit_path: Path
    raw_row_count: int
    normalized_row_count: int
    duplicate_group_count: int
    removed_row_count: int
    latest_feature_month: str
    latest_label_month: str
    output_sha256: str
```

`normalize_panel` must:

1. Resolve all three paths and reject an output/audit path equal to the raw
   path or to each other. Reject pre-existing output/audit files; versioned
   bootstrap artifacts are immutable.
2. Read the raw CSV once with source column order intact and require unique
   column names plus `FEWSNET_admin_code`, `date`, `fews_ipc_crisis`, both
   climate base columns, and both z-score columns.
3. Add internal original row numbers, parse `date`, create normalized
   `admin_code + monthly Period` keys with Task 4's `normalize_admin_code`, and
   stably sort by source `FEWSNET_admin_code`, parsed `date`, then original row
   number using `kind="mergesort"`.
4. For each duplicate normalized key, compare every source column except the
   two z-scores, treating missing values as equal. Report the exact key and
   conflicting column names and raise before any write if a conflict exists.
5. Keep the first stably sorted row from every safe duplicate group. Record all
   one-based source data-row numbers and which excluded z-score columns differed.
6. Recompute each z-score with the notebook's global rolling order:

```python
for source_name, output_name in CLIMATE_DERIVATIONS.items():
    rolling = pd.to_numeric(cleaned[source_name], errors="coerce").rolling(
        window=ROLLING_WINDOW,
        min_periods=ROLLING_MIN_PERIODS,
    ).mean()
    grouped = rolling.groupby(cleaned["_normalized_admin_code"], sort=False)
    cleaned[output_name] = (
        rolling - grouped.transform("mean")
    ) / grouped.transform("std", ddof=ZSCORE_DDOF)
```

7. Remove internal columns, restore the exact raw source-column order, and
   write the cleaned CSV only after every conflict gate passes. Do not persist
   temporary `_m12` columns.
8. Compute raw/output SHA-256 and sizes, then write a schema-valid audit JSON
   only after the CSV is complete. The audit contains exactly these top-level
   fields: `schema_version`, `normalization_version`, `source_panel`,
   `output_panel`, `key_columns`, `sort_columns`,
   `comparison_excluded_columns`, `climate_derivation`,
   `latest_feature_month`, `latest_label_month`,
   `duplicate_group_count`, `duplicate_row_count`, `removed_row_count`,
   `conflict_group_count`, and `duplicate_groups`.

`source_panel` and `output_panel` each require `path`, `sha256`, `size_bytes`,
`row_count`, and `column_count`. `climate_derivation` records the two source to
output mappings, `rolling_order="global_after_stable_admin_date_sort"`, window
`12`, minimum periods `1`, grouping column `FEWSNET_admin_code`, and `std_ddof=1`.
Every `duplicate_groups` entry requires `admin_code`, `feature_month`,
`source_row_numbers`, `group_size`, `differing_excluded_columns`, and
`disposition="collapsed_identical_or_derived_only"`. Successful audits require
`conflict_group_count=0` and
`removed_row_count == duplicate_row_count - duplicate_group_count`.

`validate_normalization_audit` validates the JSON Schema, then recomputes the
supplied panel's SHA-256, size, CSV row count, and column count and compares all
four values to `output_panel`. It also enforces the version constants and audit
count invariants.

- [ ] **Step 4: Add the local normalization CLI and verify core GREEN**

Create `cli/normalize_panel.py` with required arguments:

```text
--input-panel
--output-panel
--audit-output
```

It calls `normalize_panel`, prints one sorted JSON object with both output paths,
checksums, raw/normalized row counts, duplicate-group count, and removed-row
count, and returns nonzero with a JSON error on any validation or filesystem
failure.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_panel_normalization.py \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  -q -p no:cacheprovider
.venv/bin/python -m fewsnet_partitioned_rf_pipeline.cli.normalize_panel --help
```

Expected: focused normalization/contract tests pass and CLI prints `usage:`.

- [ ] **Step 5: Run GitNexus impact before changing existing snapshot symbols**

Run upstream impact with `repo="IPCCH_operational"` and the feature worktree
for each existing production symbol that Task 6 changes:

```text
impact(target="SnapshotManifest", direction="upstream", file_path="fewsnet_partitioned_rf_pipeline/core/types.py")
impact(target="_snapshot_semantic_payload", direction="upstream", file_path="fewsnet_partitioned_rf_pipeline/core/data.py")
impact(target="_manifest_from_payload", direction="upstream", file_path="fewsnet_partitioned_rf_pipeline/core/data.py")
impact(target="_validate_exact_artifact_references", direction="upstream", file_path="fewsnet_partitioned_rf_pipeline/core/data.py")
impact(target="stage_snapshot", direction="upstream", file_path="fewsnet_partitioned_rf_pipeline/core/data.py")
impact(target="_parser", direction="upstream", file_path="fewsnet_partitioned_rf_pipeline/cli/stage_snapshot.py")
impact(target="main", direction="upstream", file_path="fewsnet_partitioned_rf_pipeline/cli/stage_snapshot.py")
```

Record direct callers, affected processes, and risk in `PROGRESS.md`. If any
result is HIGH or CRITICAL, warn the user and stop before editing.

- [ ] **Step 6: Write RED snapshot-audit integration tests**

Extend contract/staging tests to require:

```python
def test_source_snapshot_requires_normalization_audit_object():
    payload = load_source_snapshot_fixture()
    payload.pop("normalization_audit")
    with pytest.raises(ValueError, match="normalization_audit"):
        validate_payload("source-snapshot", payload)


def test_stage_snapshot_uploads_verified_normalization_audit_before_manifest(tmp_path):
    normalized_panel, audit = write_matching_normalized_fixture(tmp_path)
    manifest = stage_snapshot(
        panel_path=normalized_panel,
        normalization_audit_path=audit,
        boundaries_path=_write_boundary_fixture(tmp_path),
        destination_root="gs://bucket/fewsnet_partitioned_rf",
        store=RecordingLocalArtifactStore(tmp_path / "store"),
        created_at_utc="2026-07-20T00:00:00Z",
    )
    assert manifest.normalization_audit.sha256 == hashlib.sha256(
        audit.read_bytes()
    ).hexdigest()
    assert manifest.panel.uri.endswith("assembled_fewsnet.normalized.csv")
    assert manifest.normalization_audit.uri.endswith(
        "panel_normalization_audit.json"
    )


def test_stage_snapshot_rejects_audit_for_different_panel(tmp_path):
    normalized_panel, audit = write_matching_normalized_fixture(tmp_path)
    normalized_panel.write_bytes(normalized_panel.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="normalization.*checksum|size"):
        stage_snapshot(
            panel_path=normalized_panel,
            normalization_audit_path=audit,
            boundaries_path=_write_boundary_fixture(tmp_path),
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )
```

Retain and explicitly re-run the existing test that passes a duplicate panel
to `stage_snapshot`; it must still fail through `inspect_panel`.

- [ ] **Step 7: Extend snapshot identity, schema, staging, and CLI**

Make these exact contract changes:

- Add `normalization_audit: ObjectRef` immediately after `panel` in
  `SnapshotManifest`.
- Change `SNAPSHOT_SCHEMA_VERSION` and the source schema constant to
  `fewsnet-source-snapshot-v2`.
- Require `normalization_audit` in `source-snapshot.schema.json` using the same
  immutable object-ref definition as other snapshot members.
- Add the audit object excluding only `generation` to
  `_snapshot_semantic_payload`.
- Construct the new field in `_manifest_from_payload`.
- Verify exact generation/checksum bytes for
  `("panel", "normalization_audit", "boundaries", "admin_universe")`.
- Require `normalization_audit_path` in `stage_snapshot`, call
  `validate_normalization_audit` before `inspect_panel`, upload the normalized
  CSV as `assembled_fewsnet.normalized.csv`, upload the audit as
  `panel_normalization_audit.json`, and write both refs into the manifest.
- Add `normalization_audit_sha256` and `normalization_version` to the canonical
  snapshot identity payload so any audit drift changes the snapshot ID.
- Set `source_identity.panel_source_type` to
  `assembled_fewsnet_normalized_v1_csv`; keep `panel_bootstrap_path` as the
  normalized CSV path because the audit is authoritative for the raw path and
  checksum.
- Add required CLI argument `--normalization-audit` and pass it unchanged to
  `stage_snapshot`.

Update the source fixture, schema tests, staging fixtures, immutable-retry
tests, semantic no-op tests, exact-reference tests, expected write count/order,
and identity hash helper for the fourth snapshot artifact. The manifest must
still be written last.

- [ ] **Step 8: Verify all Task 6 tests and the full local regression**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_panel_normalization.py \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  tests/fewsnet_partitioned_rf/test_snapshot_staging.py \
  tests/fewsnet_partitioned_rf/test_preprocessing.py \
  -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests -q -p no:cacheprovider
```

Expected: all focused tests pass; the full suite remains green; Task 4 and Task
5 duplicate hard gates remain intact.

- [ ] **Step 9: Generate the approved real cleaned panel and audit**

First record the raw checksum, then run the local-only normalizer:

```bash
RAW_PANEL="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.csv"
NORMALIZED_PANEL="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv"
NORMALIZATION_AUDIT="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json"

sha256sum "$RAW_PANEL"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.normalize_panel \
  --input-panel "$RAW_PANEL" \
  --output-panel "$NORMALIZED_PANEL" \
  --audit-output "$NORMALIZATION_AUDIT"
sha256sum "$RAW_PANEL"
```

The two raw checksums must be identical. The CLI/audit must report exactly:

```text
raw_row_count = 1120730
normalized_row_count = 1120728
duplicate_group_count = 2
duplicate_row_count = 4
removed_row_count = 2
conflict_group_count = 0
duplicate keys = 2996/2025-10 and 2996/2026-02
latest feature month = 2026-04
latest label month = 2026-02
```

If the versioned output files already exist, do not delete or overwrite them.
Validate their bytes/audit and either reuse an exact valid pair or choose a new
explicit normalization version after user approval.

- [ ] **Step 10: Prove real normalized-panel staging with no GCP write**

Use the real shapefile and `LocalArtifactStore` only:

```bash
export LOCAL_STORE="$(mktemp -d /tmp/fewsnet-normalized-v1-local-store.XXXXXX)"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import os
from pathlib import Path

from fewsnet_partitioned_rf_pipeline.core.data import inspect_panel, stage_snapshot
from fewsnet_partitioned_rf_pipeline.vertex.storage import LocalArtifactStore

panel = Path("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv")
audit = Path("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json")
boundaries = Path("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/Outcome/FEWSNET_IPC/FEWS NET Admin Boundaries/FEWS_Admin_LZ_v3.shp")

info = inspect_panel(panel)
assert info["row_count"] == 1_120_728
assert info["area_count"] == 5_718
assert info["latest_feature_month"] == "2026-04"
assert info["latest_label_month"] == "2026-02"

manifest = stage_snapshot(
    panel_path=panel,
    normalization_audit_path=audit,
    boundaries_path=boundaries,
    destination_root="gs://local-only/fewsnet_partitioned_rf",
    store=LocalArtifactStore(Path(os.environ["LOCAL_STORE"])),
    created_at_utc="2026-07-20T00:00:00Z",
)
assert manifest.row_count == 1_120_728
assert manifest.area_count == 5_718
assert manifest.normalization_audit.sha256
print(manifest.snapshot_id, manifest.snapshot_content_sha256)
PY
```

Record the raw, normalized, and audit SHA-256 values plus the resulting local
snapshot ID in `PROGRESS.md`. Do not instantiate `GCSArtifactStore`, submit a
Vertex job, register a model, or mutate any cloud resource in Task 6.

- [ ] **Step 11: Run pre-commit gates and commit Task 6**

Run focused/full tests again, `git diff --check`, and GitNexus
`detect_changes(scope="staged", repo="IPCCH_operational", worktree="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-partitioned-rf-suite")`.
Confirm staged paths contain only Task 6 production/tests/schema/fixture files
and `PROGRESS.md`; the external normalized CSV/audit are evidence and are not
added to Git.

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/normalization.py \
  fewsnet_partitioned_rf_pipeline/cli/normalize_panel.py \
  fewsnet_partitioned_rf_pipeline/core/types.py \
  fewsnet_partitioned_rf_pipeline/core/data.py \
  fewsnet_partitioned_rf_pipeline/cli/stage_snapshot.py \
  fewsnet_partitioned_rf_pipeline/schemas/panel-normalization.schema.json \
  fewsnet_partitioned_rf_pipeline/schemas/source-snapshot.schema.json \
  tests/fewsnet_partitioned_rf/test_panel_normalization.py \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  tests/fewsnet_partitioned_rf/test_snapshot_staging.py \
  tests/fixtures/fewsnet_partitioned_rf/panel_normalization_valid.json \
  tests/fixtures/fewsnet_partitioned_rf/source_snapshot_valid.json \
  PROGRESS.md
git commit -m "feat: normalize FEWSNET bootstrap panel"
```

---

### Task 7: Implement keyed horizon alignment and temporal windows

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/horizons.py`
- Create: `tests/fewsnet_partitioned_rf/test_horizons.py`

**Interfaces:**
- Produces `AlignmentResult(frame: pandas.DataFrame, dropped_rows_by_reason: dict[str, int])` and `align_horizon(feature_frame, horizon_months) -> AlignmentResult`.
- Produces `select_training_window(aligned, latest_label_month, months=36)` and `split_threshold_window(training, validation_months=6)`.
- Produces `select_latest_inference_frame(feature_frame, latest_feature_month, horizon_months) -> pandas.DataFrame`, with one row per authoritative area and `target_month = feature_month + horizon_months`.

- [ ] **Step 1: Write exact RED date-window tests**

```python
def test_horizon_alignment_uses_keyed_feature_and_target_months():
    result = align_horizon(feature_frame_fixture(), horizon_months=6)
    row = result.frame.loc[result.frame["admin_code"] == "A"].iloc[-1]
    assert str(row["feature_month"]) == "2025-08"
    assert str(row["target_month"]) == "2026-02"


def test_current_36_month_and_six_month_windows_are_exact():
    training = select_training_window(
        aligned_fixture(), latest_label_month="2026-02", months=36
    )
    fit, validation = split_threshold_window(training, validation_months=6)
    assert str(training["target_month"].min()) == "2023-03"
    assert str(training["target_month"].max()) == "2026-02"
    assert str(fit["target_month"].max()) == "2025-08"
    assert str(validation["target_month"].min()) == "2025-09"


def test_latest_inference_frame_uses_only_2026_04_for_all_horizons():
    frame = feature_frame_fixture()
    for horizon, target in ((0, "2026-04"), (6, "2026-10"), (12, "2027-04")):
        latest = select_latest_inference_frame(frame, "2026-04", horizon)
        assert set(latest["feature_month"].astype(str)) == {"2026-04"}
        assert set(latest["target_month"].astype(str)) == {target}
        assert latest["admin_code"].is_unique
```

Add duplicate area-month rejection and missing target-row drop-count tests.

- [ ] **Step 2: Run horizon tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_horizons.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement direct keyed alignment**

Create target keys by renaming the target frame's `feature_month` to `target_month`; create feature-side `target_month = feature_month + horizon_months`; merge on `admin_code + target_month` with `validate="one_to_one"`. Return dropped-row counts by reason and never use `groupby.shift(horizon_months)` for the target.

- [ ] **Step 4: Implement inclusive calendar windows**

Use:

```python
end = pd.Period(latest_label_month, freq="M")
start = end - (months - 1)
mask = aligned["target_month"].between(start, end)
```

For threshold validation, take the final six distinct target periods, not a percentage of rows.

`select_latest_inference_frame` filters by the manifest's exact `latest_feature_month`, requires its admin-code set to equal the snapshot admin universe, rejects duplicate or missing areas, and adds the keyed target month without requiring a future label row.

Define the result before `align_horizon`:

```python
@dataclass(frozen=True)
class AlignmentResult:
    frame: pd.DataFrame
    dropped_rows_by_reason: dict[str, int]
```

- [ ] **Step 5: Verify GREEN and commit**

Run Step 2, expect all tests pass, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/horizons.py \
  tests/fewsnet_partitioned_rf/test_horizons.py \
  PROGRESS.md
git commit -m "feat: align FEWSNET forecast horizons"
```

---

### Task 8: Validate and route the fixed partition map

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/partitions.py`
- Create: `tests/fewsnet_partitioned_rf/test_partitions.py`

**Interfaces:**
- Produces `PartitionMap.load(path, expected_sha256)`, `route(admin_codes)`, `coverage(admin_codes)`, and `assert_release_coverage(...)`.
- `route` returns nullable cluster IDs and preserves input order.

- [ ] **Step 1: Write RED partition tests**

Test the real asset checksum, unique admin codes, clusters `0..16`, 5,365 rows, unmapped route behavior, duplicate-map rejection, and the two-percentage-point release gate.

```python
def test_real_partition_asset_matches_approved_contract():
    mapping = PartitionMap.load(PARTITION_ASSET_PATH, PARTITION_ASSET_SHA256)
    assert mapping.mapped_area_count == 5365
    assert mapping.cluster_ids == tuple(range(17))


def test_router_preserves_unmapped_rows_for_pooled_fallback():
    mapping = PartitionMap.from_frame(pd.DataFrame({"admin_code": ["A"], "cluster_id": [4]}))
    assert mapping.route(["A", "B"]).tolist() == [4, None]
```

- [ ] **Step 2: Run tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_partitions.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement immutable map loading and coverage**

Normalize source `FEWSNET_admin_code` to canonical strings, require integer clusters, require no duplicate IDs, and compute SHA-256 before parsing. `assert_release_coverage` raises when:

```python
baseline_pct - current_pct > max_drop_percentage_points
```

Use baseline `5365 / 5718 * 100` and default maximum drop `2.0`.

- [ ] **Step 4: Verify GREEN and commit**

Run Step 2, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/partitions.py \
  tests/fewsnet_partitioned_rf/test_partitions.py \
  PROGRESS.md
git commit -m "feat: add fixed FEWSNET partition routing"
```

---

### Task 9: Implement fit-slice-only max-plus imputation and threshold selection

**Files:**
- Modify: `fewsnet_partitioned_rf_pipeline/core/preprocessing.py`
- Create: `fewsnet_partitioned_rf_pipeline/core/thresholds.py`
- Create: `tests/fewsnet_partitioned_rf/test_imputer_thresholds.py`

**Interfaces:**
- Produces sklearn-style `MaxPlusImputer.fit`, `transform`, and `fit_transform`.
- Produces `select_max_f1_threshold(y_true, y_probability) -> ThresholdResult` using the Task 2 dataclass and its exact field names.

- [ ] **Step 1: Write RED tests for imputer leakage and threshold ties**

```python
def test_max_plus_imputer_uses_fit_rows_only():
    imputer = MaxPlusImputer(multiplier=100.0).fit([[1.0], [2.0], [None]])
    transformed = imputer.transform([[1000.0], [None]])
    assert transformed[:, 0].tolist() == [1000.0, 200.0]


def test_threshold_search_chooses_higher_threshold_on_f1_tie():
    result = select_max_f1_threshold(
        y_true=np.array([0, 1]),
        y_probability=np.array([0.10, 0.90]),
    )
    assert result.threshold == 0.90
    assert result.f1 == 1.0


def test_threshold_falls_back_when_validation_has_no_positive_cases():
    result = select_max_f1_threshold(np.array([0, 0]), np.array([0.2, 0.8]))
    assert result.threshold == 0.50
    assert result.fallback_reason == "no_validation_positive_cases"
```

- [ ] **Step 2: Run tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_imputer_thresholds.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Port the exact `max_plus` rule**

For each numeric column, replace infinity with NaN, record min/max, and set:

```python
impute_value = 100.0 if max_value == 0 else max_value * 100.0
```

All-missing columns use `0.0`. `transform` rejects a different feature count and returns `float64` NumPy arrays.

- [ ] **Step 4: Implement deterministic threshold search**

Filter to finite probabilities, use `THRESHOLD_GRID`, compute precision, recall, and F1 with `zero_division=0`, and choose `max(results, key=lambda row: (row.f1, row.threshold))`. Return `ThresholdResult` with fallback reasons exactly `no_validation_observations`, `no_validation_positive_cases`, or `no_finite_validation_f1`; every fallback uses threshold `0.50` and `None` metrics.

- [ ] **Step 5: Verify GREEN and commit**

Run Step 2, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/preprocessing.py \
  fewsnet_partitioned_rf_pipeline/core/thresholds.py \
  tests/fewsnet_partitioned_rf/test_imputer_thresholds.py \
  PROGRESS.md
git commit -m "feat: add FEWSNET imputation and thresholds"
```

---

### Task 10: Train partitioned RF models and produce formal local predictions

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/training.py`
- Create: `fewsnet_partitioned_rf_pipeline/core/inference.py`
- Create: `tests/fewsnet_partitioned_rf/test_training_inference.py`

**Interfaces:**
- Produces `train_horizon_model(aligned_frame, feature_contract, partition_map, horizon_key) -> HorizonTrainingResult`.
- Produces serializable `PartitionedRFPredictor.predict_frame(frame) -> pandas.DataFrame`.
- Produces `train_partition_models(X, y, cluster_ids, min_samples=50) -> PartitionModels` and `predict_partition_probabilities(partition_models, pooled_model, X, cluster_ids) -> numpy.ndarray` for Task 11 parity.

- [ ] **Step 1: Write RED tests for all partition states and probability routing**

Build a synthetic dataset with:

- cluster 0: at least 50 rows and two classes -> partition RF;
- cluster 1: fewer than 50 rows -> `pooled_small_partition`;
- cluster 2: at least 50 rows but one class -> `pooled_single_class`;
- one unmapped area -> `pooled_unmapped` at prediction.

Assert output columns, row order, `probability_crisis` bounds, thresholded class, exact `prediction_source` values, and byte-for-byte repeatability of probabilities from two fixed-seed fits. Patch/mock `SMOTE.fit_resample` in a separate test and assert it receives only the 30-month fit slice, never threshold-validation rows.

- [ ] **Step 2: Run tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_training_inference.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement pooled and partition training**

Use `RandomForestClassifier(**RF_PARAMS)`. For eligible partitions:

```python
minority_count = int(np.bincount(y_partition.astype(int), minlength=2).min())
if minority_count >= 2:
    k_neighbors = min(SMOTE_MAX_NEIGHBORS, minority_count - 1)
    X_partition, y_partition = SMOTE(
        random_state=RF_PARAMS["random_state"],
        k_neighbors=k_neighbors,
    ).fit_resample(X_partition, y_partition)
```

When `minority_count < 2`, train on original rows and record `smote_status="skipped_minority_lt_2"`. Catch SMOTE errors, train on the original partition rows, and record `smote_status="failed"` plus the exception class/message in training metadata; successful resampling records original/resampled class counts.

Define the shared result structures in `training.py`:

```python
@dataclass(frozen=True)
class PartitionModels:
    pooled_model: RandomForestClassifier
    partition_models: dict[int, RandomForestClassifier | None]
    partition_status: dict[int, PartitionStatus]
    partition_metadata: dict[int, dict]


@dataclass(frozen=True)
class HorizonTrainingResult:
    predictor: "PartitionedRFPredictor"
    training_report: dict
    threshold_report: dict
```

`train_partition_models` trains the pooled model on every supplied row, excludes nullable/unmapped cluster IDs only from the partition loop, and emits an explicit status for every mapped cluster present in the fixed map. `predict_partition_probabilities` handles unmapped and absent models with pooled fallback and preserves row order.

- [ ] **Step 4: Implement temporary threshold models and final refit**

`train_horizon_model` must:

1. Split the 36-month aligned frame into 30-month fit and six-month validation rows.
2. Fit a temporary imputer and temporary pooled/partition models on fit rows.
3. Route validation probabilities and select the threshold.
4. Fit a new imputer and final pooled/partition models on all 36 months.
5. Return the final predictor plus training and threshold reports.

The function rejects a frame outside one inclusive 36-target-month window, a missing horizon key, a missing contract feature, or a mismatch between `partition_map` coverage and the recorded fixed checksum.

- [ ] **Step 5: Implement robust class-1 probability and formal rows**

Handle single-column `predict_proba` results by inspecting `model.classes_`. `predict_frame` returns exactly:

```text
admin_code, feature_month, target_month, horizon_months,
probability_crisis, predicted_crisis, threshold, cluster_id,
prediction_source, suite_version, vertex_model_resource_name,
vertex_model_version_id
```

The final three identity columns may initially be empty strings and are filled after registration.

- [ ] **Step 6: Verify GREEN and commit**

Run Step 2, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/training.py \
  fewsnet_partitioned_rf_pipeline/core/inference.py \
  tests/fewsnet_partitioned_rf/test_training_inference.py \
  PROGRESS.md
git commit -m "feat: train partitioned FEWSNET RF models"
```

---

### Task 11: Freeze reference Stage 3 parity evidence

**Files:**
- Create: `tools/build_fewsnet_stage3_parity_fixture.py`
- Create: `tests/fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json`
- Create: `tests/fewsnet_partitioned_rf/test_reference_parity.py`

**Interfaces:**
- The generator is developer-only and accepts `--reference-root` plus `--output`.
- Runtime tests consume only the checked-in JSON fixture and never import the external repository.

- [ ] **Step 1: Write the parity test before the fixture exists**

```python
import json
from pathlib import Path

import numpy as np

from fewsnet_partitioned_rf_pipeline.core.training import train_partition_models
from fewsnet_partitioned_rf_pipeline.core.inference import predict_partition_probabilities


def test_partition_training_matches_frozen_reference_fixture():
    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json").read_text()
    )
    models = train_partition_models(
        np.asarray(payload["X_train"], dtype=float),
        np.asarray(payload["y_train"], dtype=int),
        np.asarray(payload["groups_train"], dtype=int),
        min_samples=int(payload["min_samples"]),
    )
    probability = predict_partition_probabilities(
        models.partition_models,
        models.pooled_model,
        np.asarray(payload["X_test"], dtype=float),
        np.asarray(payload["groups_test"], dtype=int),
    )
    assert np.allclose(probability, payload["expected_probability"], atol=1e-12)
    assert models.partition_status == {
        int(key): value for key, value in payload["expected_partition_status"].items()
    }
    assert (probability >= payload["threshold"]).astype(int).tolist() == payload[
        "expected_class"
    ]
```

- [ ] **Step 2: Verify RED because the fixture/generator is absent**

Run the focused parity test.

- [ ] **Step 3: Implement the generator with a synthetic deterministic matrix**

The generator inserts the reference root into `sys.path`, imports `train_pooled_model`, `train_partitioned_model`, and `predict_partitioned_probability` from `scripts.compare_partitioned_vs_pooled_rf_k40_nc4`, trains with `min_samples=5`, and writes input arrays, expected probabilities, expected partition/fallback status, a fixed threshold, expected classes, model-presence flags, source commit, and RF parameters as JSON.

- [ ] **Step 4: Generate the fixture from the approved reference checkout**

```bash
.venv/bin/python tools/build_fewsnet_stage3_parity_fixture.py \
  --reference-root "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/2.source_code/Step5_Geo_RF_trial/Food_Crisis_Cluster" \
  --output tests/fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json
```

Require the generator to verify reference commit `1ecf180669568bbf9eb2129683108162902a415a` before writing.

- [ ] **Step 5: Verify GREEN and commit**

Run the parity test and Task 10 tests together, then:

```bash
git add \
  tools/build_fewsnet_stage3_parity_fixture.py \
  tests/fixtures/fewsnet_partitioned_rf/stage3_reference_parity.json \
  tests/fewsnet_partitioned_rf/test_reference_parity.py \
  PROGRESS.md
git commit -m "test: freeze Stage 3 RF parity fixture"
```

---

### Task 12: Write and validate Vertex-compatible model packages

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/core/package.py`
- Create: `fewsnet_partitioned_rf_pipeline/core/validation.py`
- Modify: `fewsnet_partitioned_rf_pipeline/schemas/model-package.schema.json`
- Modify: `tests/fewsnet_partitioned_rf/test_contracts.py`
- Create: `tests/fewsnet_partitioned_rf/test_model_package.py`

**Interfaces:**
- Produces `write_model_package(output_dir, predictor, metadata, reports) -> dict`.
- Produces `load_model_package(package_dir, expected_image_digest=None, expected_source_git_commit=None) -> PartitionedRFPredictor`.
- `metadata` supplies the digest-pinned shared `container_image_uri`, matching `container_image_digest`, while `reports["training_report"]` supplies the horizon training and validation target-month ranges copied into the manifest.

- [ ] **Step 1: Write RED package round-trip and tamper tests**

Update the existing model-package contract fixture for the three newly required manifest fields. Assert the exact seven package files, prediction equivalence before/after joblib round trip, dependency metadata, and the design-required manifest fields `container_image_uri`, `training_target_month_range`, and `validation_target_month_range`. Assert rejection when any required manifest field is absent, when the image URI does not end with `@{container_image_digest}`, when manifest month ranges disagree with `training_report.json`, after altering `threshold_report.json` without updating `checksums.json`, and when the current Python/model-stack versions differ from the manifest.

- [ ] **Step 2: Run package tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_model_package.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement deterministic package writing**

Write `model.joblib` with:

```python
joblib.dump(predictor, model_path, compress=3, protocol=5)
```

Write feature contract, fixed partition CSV, threshold report, training report, and model manifest. The manifest copies `training_target_month_range` and `validation_target_month_range` from the horizon training report and records both the shared `container_image_uri` and its digest; reject a URI whose suffix is not `@{container_image_digest}`. Compute SHA-256 after all six content files exist, then write `checksums.json` last. Record runtime versions with `importlib.metadata.version`.

- [ ] **Step 4: Implement defensive loading**

Require all seven files, validate the expanded model-package JSON schema, verify every checksum, verify feature and partition checksums against the manifest, require `container_image_uri` to end with `@{container_image_digest}`, and require the manifest training/validation target-month ranges to equal those in `training_report.json`. Optionally verify the image digest and source Git commit, and compare exact runtime versions for Python major/minor, NumPy, pandas, scikit-learn, joblib, and imbalanced-learn before loading `model.joblib`. Reject an object that is not `PartitionedRFPredictor`.

Use this compatibility helper so the predictor container fails before unpickling under a drifted stack:

```python
def assert_runtime_compatible(expected: dict[str, str]) -> None:
    observed = runtime_dependency_versions()
    for name in ("python", "numpy", "pandas", "scikit-learn", "joblib", "imbalanced-learn"):
        if observed[name] != expected[name]:
            raise PackageValidationError(
                f"runtime dependency mismatch for {name}: "
                f"expected {expected[name]}, observed {observed[name]}"
            )
```

- [ ] **Step 5: Verify GREEN and commit**

Run Step 2, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/package.py \
  fewsnet_partitioned_rf_pipeline/core/validation.py \
  fewsnet_partitioned_rf_pipeline/schemas/model-package.schema.json \
  tests/fewsnet_partitioned_rf/test_contracts.py \
  tests/fewsnet_partitioned_rf/test_model_package.py \
  PROGRESS.md
git commit -m "feat: package Vertex-compatible FEWSNET models"
```

---

### Task 13: Build the three-horizon training worker and Vertex Custom Job spec

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/cli/train.py`
- Create: `fewsnet_partitioned_rf_pipeline/vertex/training_job.py`
- Create: `tests/fewsnet_partitioned_rf/test_training_job.py`

**Interfaces:**
- `cli.train` localizes one snapshot, trains all three horizons, uploads three packages, and writes `training_job_result.json` last.
- `build_training_custom_job_spec(config) -> dict` creates exactly one worker pool and command `python3 -m fewsnet_partitioned_rf_pipeline.cli.train`.

- [ ] **Step 1: Write RED worker and job-spec tests**

Assert one synthetic snapshot produces package prefixes `models/0m`, `models/6m`, `models/12m`, and that the job spec uses one digest-pinned image, one service account, `n2-highmem-8`, and `21600s` timeout.

- [ ] **Step 2: Run tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_training_job.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement the in-container training worker**

The CLI accepts:

```text
--snapshot-manifest-uri
--suite-version
--run-root-uri
--model-root-uri
--container-image-uri
--container-image-digest
--source-git-commit
```

The orchestrator supplies `--model-root-uri={object_store_root_uri}/suites/{suite_version}/models` and `--run-root-uri={object_store_root_uri}/runs/{run_id}`. The worker requires `--source-git-commit` to equal image environment `FEWSNET_SOURCE_GIT_COMMIT`, downloads every snapshot object at the manifest's exact generation to `tempfile.TemporaryDirectory`, verifies local SHA-256/size against its `ObjectRef`, validates row/area/month contracts, loads `FEATURE_CONTRACT_PATH` without refitting it, builds the shared feature frame, trains horizons in `HORIZON_MONTHS` order, writes/uploads packages with immutable preconditions, writes identical aggregate report bytes to `runs/{run_id}/training_threshold_report.json` and `suites/{suite_version}/training_threshold_report.json`, and writes `training_job_result.json` last.

Every package/report file upload uses `upload_file_immutable_or_verify`, while small JSON result bytes use `put_immutable_or_verify`; a retry of the same suite/run may reuse byte-identical partial artifacts but must fail if any pre-existing byte differs. `training_job_result.json` records the snapshot content digest, three package URIs/checksums, aggregate report URI/checksum, source Git commit, and exact image digest.

- [ ] **Step 4: Implement the Custom Job request builder**

Use the same digest validation pattern as the existing IPCCH client, but do not import it. The request contains one worker pool, command and arguments above, environment identifiers, output directory, `training_service_account`, and configurable machine/timeout values. Persist the submitted Custom Job resource and normalized request under `runs/{run_id}/training/custom_job.json` before polling it. The backend exposes submit/get/cancel; exceeding `training_timeout_seconds` cancels the exact job and waits for a terminal cancelled/failed state before the orchestrator decides whether the transient failure is retryable.

- [ ] **Step 5: Verify GREEN and commit**

Run Step 2 plus package tests, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/cli/train.py \
  fewsnet_partitioned_rf_pipeline/vertex/training_job.py \
  tests/fewsnet_partitioned_rf/test_training_job.py \
  PROGRESS.md
git commit -m "feat: add FEWSNET Vertex training job"
```

---

### Task 14: Serve registered packages with a shared custom prediction container

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/vertex/predictor_server.py`
- Create: `docker/Dockerfile.fewsnet-partitioned-rf`
- Create: `tests/fewsnet_partitioned_rf/test_predictor_server.py`
- Create: `tests/fewsnet_partitioned_rf/test_runtime_image.py`

**Interfaces:**
- Produces `create_app(environ=None, store=None) -> FastAPI`.
- Container default command starts Uvicorn; Vertex training overrides the command with Task 13's trainer.

- [ ] **Step 1: Write RED health/predict tests**

Use `fastapi.testclient.TestClient` and a temporary package. Assert health returns 503 after any package/checksum/dependency/image-digest load failure, 200 after successful load, predict preserves instance order, missing features return 400, and horizon input is rejected.

- [ ] **Step 2: Run tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_predictor_server.py \
  tests/fewsnet_partitioned_rf/test_runtime_image.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement environment-driven Vertex routes**

At app creation, resolve these values inside a guarded startup-load block:

```python
port = int(env.get("AIP_HTTP_PORT", "8080"))
health_route = env.get("AIP_HEALTH_ROUTE", "/health")
predict_route = env.get("AIP_PREDICT_ROUTE", "/predict")
artifact_uri = env["AIP_STORAGE_URI"]
expected_image_digest = env["FEWSNET_CONTAINER_IMAGE_DIGEST"]
expected_source_git_commit = env["FEWSNET_SOURCE_GIT_COMMIT"]
```

Localize the seven package files once, call `load_model_package(..., expected_image_digest=expected_image_digest, expected_source_git_commit=expected_source_git_commit)`, and hold either the predictor or startup error. `create_app` must not raise when required environment values are missing or package loading fails; it installs the routes with a stored startup error so health returns 503 and prediction returns 503 until a valid app is created. The predict handler requires `{"instances": [object, ...]}` and returns `{"predictions": [object, ...]}`. It accepts only `admin_code`, `feature_month`, and the package's exact feature allowlist; it rejects a request-level horizon or undeclared model feature.

Expose module-level `app = create_app()` and a `main()` that runs:

```python
uvicorn.run(
    "fewsnet_partitioned_rf_pipeline.vertex.predictor_server:app",
    host="0.0.0.0",
    port=int(os.environ.get("AIP_HTTP_PORT", "8080")),
)
```

- [ ] **Step 4: Create the dedicated shared image**

Create `docker/Dockerfile.fewsnet-partitioned-rf`:

```dockerfile
FROM python:3.11-slim

ARG SOURCE_GIT_COMMIT

LABEL org.opencontainers.image.title="fewsnet-partitioned-rf-runtime"
LABEL org.opencontainers.image.revision=$SOURCE_GIT_COMMIT
LABEL fewsnet.entrypoint.training="python3 -m fewsnet_partitioned_rf_pipeline.cli.train"
LABEL fewsnet.entrypoint.predictor="python3 -m fewsnet_partitioned_rf_pipeline.vertex.predictor_server"
LABEL fewsnet.entrypoint.orchestrator="python3 -m fewsnet_partitioned_rf_pipeline.cli.run_latest"

WORKDIR /app
COPY requirements-fewsnet-partitioned-rf.txt /app/
RUN pip install --no-cache-dir -r /app/requirements-fewsnet-partitioned-rf.txt
COPY . /app
ENV PYTHONPATH=/app
ENV FEWSNET_SOURCE_GIT_COMMIT=$SOURCE_GIT_COMMIT
EXPOSE 8080
CMD ["python3", "-m", "fewsnet_partitioned_rf_pipeline.vertex.predictor_server"]
```

- [ ] **Step 5: Verify GREEN and commit**

Run Step 2 and this import smoke:

```bash
.venv/bin/python -c "from fewsnet_partitioned_rf_pipeline.vertex.predictor_server import create_app; assert callable(create_app)"
```

Then:

```bash
git add \
  docker/Dockerfile.fewsnet-partitioned-rf \
  fewsnet_partitioned_rf_pipeline/vertex/predictor_server.py \
  tests/fewsnet_partitioned_rf/test_predictor_server.py \
  tests/fewsnet_partitioned_rf/test_runtime_image.py \
  PROGRESS.md
git commit -m "feat: serve FEWSNET models in Vertex"
```

---

### Task 15: Register three stable parent models and immutable candidate versions

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/vertex/registry.py`
- Create: `tests/fewsnet_partitioned_rf/test_registry.py`

**Interfaces:**
- Produces `register_candidate_version(...) -> RegisteredModelVersion`.
- Produces `suite_version_alias(suite_version) -> str`, `resolve_parent_model(...) -> str | None`, and `mark_registered_versions_abandoned(...)`.
- First suite creates the stable model ID; later suites pass the deterministic parent resource name as `parent_model`.

- [ ] **Step 1: Write RED upload-argument tests**

Assert each horizon uses the expected stable model ID, exact artifact URI, shared image digest URI, predict/health routes, port 8080, `FEWSNET_CONTAINER_IMAGE_DIGEST`, `FEWSNET_SOURCE_GIT_COMMIT`, lifecycle label `candidate`, no `production` alias, and the deterministic suite alias. Assert first-parent upload uses `model_id=PARENT_MODEL_IDS[horizon_key]`, `parent_model=None`, `is_default_version=True`; later upload uses `model_id=None`, the full parent resource, and `is_default_version=False`.

- [ ] **Step 2: Run registry tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_registry.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement a narrow SDK adapter**

Pin and test against `google-cloud-aiplatform==1.161.0`. Initialize `google.cloud.aiplatform` with project/region. Resolve the parent by constructing `projects/{project}/locations/{region}/models/{stable_model_id}` and calling `aiplatform.ModelRegistry(...).list_versions()`; treat only `google.api_core.exceptions.NotFound` as absence.

Sanitize the immutable suite identity into a Vertex alias by lowercasing, replacing characters outside `[a-z0-9-]` with `-`, collapsing repeated hyphens, stripping leading/trailing hyphens, prefixing `v-` only if the result does not begin with a letter, and rejecting an empty result or a result longer than 128 characters. Then call `aiplatform.Model.upload` with:

```python
display_name=PARENT_MODEL_IDS[horizon_key]
artifact_uri=artifact_uri
serving_container_image_uri=image_uri
serving_container_predict_route="/predict"
serving_container_health_route="/health"
serving_container_ports=[8080]
serving_container_environment_variables={
    "FEWSNET_CONTAINER_IMAGE_DIGEST": image_digest,
    "FEWSNET_SOURCE_GIT_COMMIT": source_git_commit,
}
labels=labels
parent_model=parent_model_resource_name
model_id=None if parent_model_resource_name else PARENT_MODEL_IDS[horizon_key]
is_default_version=bool(parent_model_resource_name is None)
version_aliases=[suite_alias]
version_description=version_description
sync=True
```

Vertex assigns the numeric version ID; do not invent or pass a `version_id` parameter. Return `uploaded.resource_name`, `uploaded.versioned_resource_name`, `uploaded.version_id`, the suite alias, and artifact URI. Persist a normalized registration response at `runs/{run_id}/registry/{horizon}.json` and update the run manifest immediately.

For retry idempotency, first query `ModelRegistry.get_version_info(suite_alias)`. If it exists, load that exact version and return it only after artifact URI, image URI/digest environment variable, horizon, and suite labels match; otherwise fail rather than creating a duplicate version. An exact retry may restore `lifecycle=candidate` before continuing. On a later suite-stage failure, `mark_registered_versions_abandoned` merges `lifecycle=abandoned` into the existing labels for every already-created candidate without deleting it or dropping provenance labels.

- [ ] **Step 4: Verify GREEN and commit**

Run Step 2, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/vertex/registry.py \
  tests/fewsnet_partitioned_rf/test_registry.py \
  PROGRESS.md
git commit -m "feat: register FEWSNET Vertex model versions"
```

---

### Task 16: Run exact-version Batch Prediction and normalize formal CSVs

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/vertex/batch_prediction.py`
- Create: `fewsnet_partitioned_rf_pipeline/cli/infer.py`
- Create: `tests/fixtures/fewsnet_partitioned_rf/vertex_batch_output.jsonl`
- Create: `tests/fewsnet_partitioned_rf/test_batch_prediction.py`

**Interfaces:**
- Produces `write_batch_input_jsonl(frame, contract, output_path)`.
- Produces `submit_batch_prediction(config, backend) -> BatchJobRef` and `wait_batch_prediction(job_ref, timeout_seconds, backend) -> BatchJobRef`.
- Produces `normalize_batch_output(raw_paths, input_frame, model_ref, suite_version) -> pandas.DataFrame`.

- [ ] **Step 1: Write RED input/job/output tests**

Assert one JSONL instance per latest-month area, no horizon parameter, exact numeric `@version_id` resource name in the job, `instances_format="jsonl"`, `predictions_format="jsonl"`, configured machine type, one starting/max replica, service account, timeout handling, and normalized formal columns/identity.

- [ ] **Step 2: Run tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_batch_prediction.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement Batch input and SDK submission**

Write JSON objects containing `admin_code`, `feature_month`, and every contract feature from `select_latest_inference_frame`; do not include a horizon field. Store input at `runs/{run_id}/batch_prediction/{horizon}/input.jsonl` and use `runs/{run_id}/batch_prediction/{horizon}/raw` as the Vertex destination prefix. With SDK `1.161.0`, submit asynchronously using:

```python
job = aiplatform.BatchPredictionJob.submit(
    job_display_name=job_display_name,
    model_name=model_ref.version_resource_name,
    instances_format="jsonl",
    predictions_format="jsonl",
    gcs_source=input_uri,
    gcs_destination_prefix=destination_prefix,
    machine_type=deployment["batch_machine_type"],
    starting_replica_count=1,
    max_replica_count=1,
    service_account=deployment["batch_prediction_service_account"],
    labels=labels,
    project=deployment["project_id"],
    location=deployment["region"],
)
```

Persist `job.resource_name` before waiting. The wait backend polls the public JobService `get_batch_prediction_job` response until success/failure with the configured deadline; on success it records `output_info.gcs_output_directory`, and on timeout it calls `cancel_batch_prediction_job` for that exact resource and waits for terminal cancellation/failure before raising. Do not use blocking `BatchPredictionJob.create`, because it does not enforce the plan's execution timeout.

- [ ] **Step 4: Normalize and validate raw JSONL**

List `predictions_*.jsonl` below the returned `gcs_output_directory`, reject any `errors_*.jsonl` object or line-level `error`, require each line to contain `instance` and `prediction`, flatten the prediction object, add suite/model version identity, join back to the supplied latest-month `input_frame` by unique `admin_code`, restore its order, and validate every record against `prediction-record.schema.json`.

`cli.infer` accepts the exact candidate model reference, snapshot manifest, horizon, raw output prefix, run CSV URI, and suite CSV URI. It serializes one canonical CSV byte sequence and writes it with `put_immutable_or_verify` to both `runs/{run_id}/predictions/{horizon}.csv` and `suites/{suite_version}/predictions/{horizon}.csv` only after all row-level gates pass.

- [ ] **Step 5: Verify GREEN and commit**

Run Step 2, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/vertex/batch_prediction.py \
  fewsnet_partitioned_rf_pipeline/cli/infer.py \
  tests/fixtures/fewsnet_partitioned_rf/vertex_batch_output.jsonl \
  tests/fewsnet_partitioned_rf/test_batch_prediction.py \
  PROGRESS.md
git commit -m "feat: run FEWSNET Vertex batch prediction"
```

---

### Task 17: Validate three-horizon outputs and implement alias rollback publication

**Files:**
- Modify: `fewsnet_partitioned_rf_pipeline/core/validation.py`
- Create: `fewsnet_partitioned_rf_pipeline/vertex/promotion.py`
- Create: `tests/fewsnet_partitioned_rf/test_promotion.py`

**Interfaces:**
- Produces `validate_prediction_suite(predictions, snapshot, registered_versions)`.
- Produces `acquire_promotion_lease(...)`, `release_promotion_lease(...)`, and `promote_and_publish(...) -> dict` with serialized alias mutation, alias rollback, and generation-safe pointer writes.

- [ ] **Step 1: Write RED validation and rollback tests**

Cover missing horizon, duplicate admin code, 5,718-current-snapshot row reconciliation, invalid probability/class relationship, fallback totals, partition-coverage regression, model-version mismatch, an unexpired competing promotion lease, expired/released lease takeover, initially absent production aliases, second-alias failure with first-alias rollback, idempotent alias movement, same-month revision replacing the month pointer by generation, and current-pointer write failure with all aliases restored plus best-effort month-pointer restoration.

- [ ] **Step 2: Run tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_promotion.py \
  -q -p no:cacheprovider
```

- [ ] **Step 3: Implement complete suite validation**

Require horizon keys exactly `{"0m", "6m", "12m"}`, row universe equal to the snapshot admin universe, each row's feature month equal to `snapshot.latest_feature_month`, target months equal to the keyed horizon offsets, probabilities in `[0,1]`, class equality with threshold, allowed route/source pairs, fallback totals equal to `snapshot.area_count`, fixed-partition coverage within the two-percentage-point gate, and exact registered numeric model resource/version values. Cross-check each Batch input object's URI/generation/checksum and every package's snapshot content digest against the selected `SnapshotManifest`; this is where input-generation identity is enforced even though it is not repeated in every CSV row.

- [ ] **Step 4: Implement reversible alias movement**

Acquire `locks/production-promotion.json` before reading production aliases or pointers. Its payload contains `lease_id`, `run_id`, `status`, `acquired_at_utc`, and `expires_at_utc`. Create it at generation `0`, or replace only a `released`/expired payload using its observed generation; an unexpired lease raises retryable `PromotionBusy`. After acquisition, reread `released/current.json`: if another run already released the same snapshot content digest, abandon this run's candidates and return `NOOP`; if current production has a newer feature month, fail closed rather than promoting an older suite.

Define an alias backend with `current_version(parent, alias)`, `move_alias(parent, alias, target_version)`, and `restore_alias(parent, alias, previous_version)`. The SDK `1.161.0` adapter uses `aiplatform.ModelRegistry(parent).get_version_info(alias)`, `add_version_aliases([alias], version=target_version)`, and—when the alias was previously absent—`remove_version_aliases([alias], version=target_version)`. Adding an alias to a new version moves that unique alias from the old version. Capture all previous versions before changing any alias, treat an alias already on the target as success, and on any exception restore changed aliases in reverse order. Raise a `PromotionError` containing both the original and rollback failures.

- [ ] **Step 5: Write immutable manifests and pointer last**

Before alias movement, call `get_ref` and generation-specific `read_bytes` to capture both `released/{feature_month}/production_suite_manifest.json` and `released/current.json` bytes/generations (`0` when absent). After all aliases move:

1. Write the immutable suite manifest under `suites/{suite_version}/suite_manifest.json` with `put_immutable_or_verify`.
2. Replace the feature-month production manifest with `put_mutable_or_verify(..., expected_generation=previous_month_generation)`; it identifies the immutable suite-manifest URI and generation and therefore supports an explicit same-month revision.
3. Replace `released/current.json` with `put_mutable_or_verify(..., expected_generation=previous_current_generation)` and make this the final write.

If either mutable write fails, roll back aliases, leave the old current pointer unchanged, and best-effort restore the previous month manifest using the generation produced by Step 2. If no previous month manifest existed, an unattached month manifest may remain as non-authoritative evidence; `released/current.json` is the only entrypoint operators treat as current. Never overwrite the immutable suite manifest with different bytes. In `finally`, release only the lease whose `lease_id` still matches by writing `status="released"` with its current generation; a lost/mismatched lease is a hard warning recorded in the run manifest.

- [ ] **Step 6: Verify GREEN and commit**

Run Step 2, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/core/validation.py \
  fewsnet_partitioned_rf_pipeline/vertex/promotion.py \
  tests/fewsnet_partitioned_rf/test_promotion.py \
  PROGRESS.md
git commit -m "feat: promote FEWSNET model suites safely"
```

---

### Task 18: Orchestrate discover -> train -> register -> Batch -> promote

**Files:**
- Create: `fewsnet_partitioned_rf_pipeline/cli/run_latest.py`
- Create: `tests/fewsnet_partitioned_rf/test_run_latest.py`

**Interfaces:**
- Produces `run_latest(deployment, store, training_backend, registry_backend, batch_backend, alias_backend, *, revision_id=None, snapshot_manifest_uri=None, promote=True) -> dict`.
- Produces CLI `python -m fewsnet_partitioned_rf_pipeline.cli.run_latest --deployment-manifest-uri ... [--revision-id ...] [--snapshot-manifest-uri ...] [--candidate-only]`.

- [ ] **Step 1: Write a RED fake-cloud happy-path test**

Seed two snapshot manifests, a prior production pointer, and fake clients. Assert the newer snapshot is selected, one training job is submitted, three model versions are registered, three exact-version Batch jobs run, three aliases move only after all validation, and `released/current.json` is the final write.

- [ ] **Step 2: Add RED failure and idempotency tests**

Cover:

- same feature month/checksum -> `NOOP`;
- same month/different checksum without revision -> failure;
- explicit revision -> new suite version;
- identical content restaged at a new generation -> `NOOP`;
- training failure -> no registration;
- one registration failure -> no Batch/promotion and earlier candidates marked `abandoned`;
- one Batch failure -> no promotion;
- output failure -> no alias movement;
- transient API failure or `PromotionBusy` retries no more than `max_retries` while reusing exact snapshot content digest, image digest, artifact URIs, and candidate versions;
- non-transient validation failure is never retried;
- an ambiguous commit-then-raise training or Batch create reconciles exactly one matching job through the real production adapter over fake SDK/service clients, and fails closed on zero-after-retry, multiple, or mismatched matches;
- a same-month changed-digest race is rejected by the revision gate rechecked inside the promotion lease;
- `PromotionIndeterminate` and failures after an authoritative `RELEASED` result never mark possibly/live versions `abandoned`;
- preflight deployment/source/discovery failure returns a structured error and CLI nonzero exit without formal run artifacts; every failure after successful discovery writes terminal `error.json` and `run_manifest.json`.

- [ ] **Step 3: Run orchestrator tests to verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_run_latest.py \
  -q -p no:cacheprovider
```

- [ ] **Step 4: Implement deterministic discovery and suite identity**

Unless `snapshot_manifest_uri` is explicitly supplied for a gated smoke run, list only objects ending in `/source_manifest.json` below `inputs/snapshots/`, read each listed generation exactly, load schema-valid manifests, and choose the maximum `(latest_feature_month, created_at_utc, snapshot_id)`. Ignore incomplete prefixes with no final manifest. Compare `latest_feature_month + snapshot_content_sha256` to the current pointer. A same-month changed digest requires `revision_id` matching `^[a-z0-9][a-z0-9-]{0,31}$`; a byte-identical restage is a no-op regardless of GCS generation. Create:

```python
source_git_commit = deployment["source_git_commit"]
run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
suite_version = (
    f"fewsnet-prf-{feature_month.replace('-', '')}-"
    f"{source_git_commit[:8]}-{snapshot.snapshot_content_sha256[:8]}-"
    f"{('rev-' + revision_id + '-') if revision_id else ''}{run_stamp}"
)
run_id = suite_version
```

Copy the exact-generation-read selected manifest bytes to a run-specific
immutable object under `runs/{run_id}/inputs/selected_source_manifest.json`.
Pass only that immutable URI to the training worker so source restaging cannot
change worker input or retry identity.

- [ ] **Step 5: Implement monotonic orchestration and evidence writes**

Call `validate_deployment` and require `deployment["source_git_commit"] == os.environ["FEWSNET_SOURCE_GIT_COMMIT"]` before discovery. Preflight exceptions return/log a structured error and cause a nonzero CLI exit without creating formal run artifacts. After successful discovery establishes `run_id`, `suite_version`, and exact snapshot evidence, write `input_snapshot_ref.json`, then advance through every `RunPhase`, updating `run_manifest.json` with generation preconditions after each transition. Use a bounded `retry_transient` helper that retries only `TooManyRequests`, `ServiceUnavailable`, `DeadlineExceeded`, and retryable transport failures, recording each attempt. Training and Batch production adapters must reconcile deterministic operation identity before any retry after an ambiguous submit: return one exact matching created job, submit only when none exists, and fail closed on multiple or mismatched matches. Submit/wait for one training job, verify `training_job_result.json`, register in horizon order with idempotent suite aliases, build the three inference frames from exactly `snapshot.latest_feature_month`, run/wait/normalize three exact-version Batch jobs, validate the suite, then call Task 17 promotion when `promote=True`. Task 17 rechecks same-month revision authorization inside its promotion lease. For `--candidate-only`, stop successfully after `OUTPUT_VALIDATED` and do not read or mutate production aliases/pointers. Catch post-discovery exceptions once at the top, mark registered candidates `abandoned` only when they are definitively not live production, write terminal evidence, set phase `FAILED`, and return nonzero from CLI. Preserve lifecycle labels and surface an indeterminate/evidence-warning outcome for `PromotionIndeterminate` or any failure after promotion returned `RELEASED`.

The retry helper preserves operation identity:

```python
def retry_transient(operation, *, max_retries: int, on_retry):
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except RETRYABLE_EXCEPTIONS:
            if attempt == max_retries:
                raise
            on_retry(attempt + 1)
```

The runtime `on_retry` records the exception and sleeps `min(60, 2 ** retry_number)` seconds; tests inject a no-op sleeper and assert the exact retry count.

- [ ] **Step 6: Verify GREEN and commit**

Run Step 3 plus Tasks 13-17 tests, then:

```bash
git add \
  fewsnet_partitioned_rf_pipeline/cli/run_latest.py \
  tests/fewsnet_partitioned_rf/test_run_latest.py \
  PROGRESS.md
git commit -m "feat: orchestrate FEWSNET model suite releases"
```

---

### Task 19: Add runbook, gated GCP smoke coverage, and full acceptance verification

**Files:**
- Create: `docs/09_fewsnet_partitioned_rf_runbook.md`
- Create: `tests/fewsnet_partitioned_rf/test_gcp_smoke.py`
- Modify only if required by actual image build: `requirements-fewsnet-partitioned-rf.txt`
- Update: `PROGRESS.md`

**Interfaces:**
- The runbook is the operator contract for snapshot staging, image build, deployment manifest, first parent models, routine `run_latest`, rollback, and revision runs.
- The smoke test is skipped unless `FEWSNET_GCP_SMOKE_ENABLED=1` and all required environment variables are present.

- [ ] **Step 1: Write the gated smoke test**

The test must require:

```text
FEWSNET_GCP_SMOKE_ENABLED
FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI
FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI
```

It runs a disposable suite with production promotion disabled, asserts one Custom Job, three candidate versions, three Batch jobs, exact row reconciliation for the test snapshot, and zero Endpoint creation.

Call `run_latest` with `snapshot_manifest_uri=FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI` and `promote=False`. The smoke deployment must use disposable parent model IDs or a dedicated test project so its retained candidate versions cannot be confused with the three production parents.

- [ ] **Step 2: Write the operator runbook**

Document exact commands for:

1. Building and pushing `docker/Dockerfile.fewsnet-partitioned-rf` by digest.
2. Generating the versioned normalized CSV/audit without overwriting the raw
   panel, then staging that verified CSV/audit with the local shapefile.
3. Creating a deployment manifest with three service accounts and stable model IDs, including the submitter's `iam.serviceAccounts.actAs` grants and least-privilege GCS, Artifact Registry Reader, Vertex Custom Job, Model Registry/version-alias, and Batch Prediction permissions for each runtime identity.
4. Running `run_latest` and locating run/model/prediction/suite artifacts.
5. Interpreting fallback counts and threshold reports.
6. Recovering from failed training, candidate registration, Batch output, alias rollback, and pointer conflicts.
7. Running an explicit same-month revision.
8. Proving no online Endpoint exists.
9. Explaining that Vertex numeric version IDs are service-assigned, while the deterministic suite alias and manifests carry the immutable suite identity.

- [ ] **Step 3: Run the complete local verification suite**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf \
  -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/cloud tests/test_operational_launch_inference.py \
  -q -p no:cacheprovider
git diff --check
```

Expected: all new tests pass, selected existing IPCCH regression tests pass, and `git diff --check` is silent.

- [ ] **Step 4: Build the shared container and run local server smoke**

```bash
docker build \
  -f docker/Dockerfile.fewsnet-partitioned-rf \
  -t fewsnet-partitioned-rf:local .
docker run --rm fewsnet-partitioned-rf:local \
  python3 -m fewsnet_partitioned_rf_pipeline.cli.train --help
```

Expected: image build succeeds and training CLI prints `usage:`.

- [ ] **Step 5: Run the optional live GCP smoke when credentials and manifest are available**

```bash
FEWSNET_GCP_SMOKE_ENABLED=1 \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_gcp_smoke.py \
  -q -p no:cacheprovider -s
```

Expected: one disposable training job, three candidate versions, and three Batch jobs pass without modifying production aliases.

- [ ] **Step 6: Run initial production acceptance only after smoke approval**

Run `run_latest` against the approved current snapshot and production deployment manifest. Verify all sixteen acceptance criteria from design section 19, including raw-source checksum preservation, the 1,120,728-row normalized panel and audit, local-store staging evidence, three registered production versions, 5,718 rows per CSV, the approved partition checksum, consistent fallback totals, no Endpoint, and `released/current.json` written last.

- [ ] **Step 7: Run final GitNexus and staged-scope verification**

Run impact analysis for every existing symbol changed, then:

```text
detect_changes(scope="compare", base_ref="main")
```

Review every affected process. Stage only the intended FEWSNET files, run `git diff --cached --check`, and record the final evidence in `PROGRESS.md`.

- [ ] **Step 8: Commit Task 19**

```bash
git add \
  docs/09_fewsnet_partitioned_rf_runbook.md \
  tests/fewsnet_partitioned_rf/test_gcp_smoke.py \
  requirements-fewsnet-partitioned-rf.txt \
  PROGRESS.md
git commit -m "docs: finalize FEWSNET model suite operations"
```

---

## Final Review Gate

Before declaring implementation complete:

- Confirm every task commit exists and `PROGRESS.md` points to the final verification commands.
- Confirm the approved spec and this plan were not silently broadened.
- Confirm existing IPCCH predictions, model packages, Dockerfile, and release roots were not changed.
- Confirm no runtime absolute path references `Food_Crisis_Cluster` or the Dropbox source directories.
- Confirm the three production Model Versions use the same suite version, source snapshot, feature contract, partition checksum, Git commit, and container digest.
- Confirm `released/current.json` identifies those exact three versions and was written after the month production manifest.
- Confirm no persistent Vertex Endpoint was created.
- Use `superpowers:verification-before-completion` before any completion claim.
