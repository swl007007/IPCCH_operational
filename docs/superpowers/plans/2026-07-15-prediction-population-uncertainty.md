# Prediction Population and Qualitative Uncertainty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce new 0m, 6m, and 12m prediction CSVs that include a traceable feature-month population estimate and qualitative threshold-margin uncertainty without changing model weights, model feature values, scores, or phase predictions.

**Architecture:** Add a streaming population snapshot component shared by local and cloud monthly assembly. Assembly writes output-only population fields while preserving the original `estimated_population`; core inference carries those fields into predictions and computes uncertainty from scope-specific score thresholds. The cloud wrapper independently validates the extended schema, records summaries, and releases a new immutable run instead of editing existing results.

**Tech Stack:** Python 3.11, pandas, NumPy, XGBoost model packages, pytest/unittest, Cloud Run orchestration, Vertex AI Custom Jobs, GCS object-store wrappers.

## Global Constraints

- Work on a `features/*` branch; do not push directly to `main` or `development`.
- At implementation start, create or reconcile repository-local `PROGRESS.md` against this plan and `git status`.
- After each task, update `PROGRESS.md` with completed steps, verification output, commit hash, blockers, and the exact next command; include it in that task's commit.
- Do not edit `specs/001-cloud-base-input/spec.md`, `plan.md`, `tasks.md`, or other existing Speckit source-of-truth artifacts without separate explicit authorization.
- Preserve the original `estimated_population` column exactly; new population fields are output-only and must not enter the model feature matrix.
- Keep model package files and weights unchanged.
- Existing score columns, binary boundary predictions, and `overall_phase_pred` must remain row-for-row identical for the same input and model package.
- Population lookup may use only the feature month or an earlier month for the same `area_id`; future values and cross-area fills are forbidden.
- `prediction_uncertainty` is qualitative decision stability, not probability, confidence level, calibrated interval, or statistical coverage.
- Use each scope's resolved model metadata thresholds; never hard-code `0.20` as the model threshold.
- Existing released runs remain immutable. Enhanced outputs require a new `run_id` and a new complete assembly-to-release run.
- Use ADC/service-account credentials for GCP; do not introduce `GEMINI_API_KEY` or committed local credential files.
- Run tests with `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` to avoid workspace cache changes.

---

## File Structure

### New files

- `model_pipeline/ipcch_launch_runtime/population.py` — streaming, no-future-leakage population selection and shared population field constants.
- `model_pipeline/ipcch_launch_runtime/uncertainty.py` — deterministic threshold-margin calculation and summary helpers.
- `tests/test_population_output.py` — focused population selector unit tests.
- `tests/test_prediction_uncertainty.py` — focused uncertainty calculation unit tests.

### Modified files

- `Final_harmonise/00_build_monthly_ipcch_base_input.py` — attach population output fields during local monthly assembly.
- `cloud/orchestrator/assembly.py` — attach the same population fields during cloud assembly.
- `cloud/orchestrator/base_input_validation.py` — hard-gate population fields before inference.
- `model_pipeline/ipcch_launch_runtime/inference.py` — preserve population fields and add uncertainty fields to scored output.
- `tests/test_build_monthly_ipcch_base_input.py` — local assembly behavior and no-future-leakage coverage.
- `tests/cloud/test_monthly_assembly_wrapper.py` — cloud assembly population behavior and summary coverage.
- `tests/test_operational_launch_inference.py` — population propagation, uncertainty integration, and prediction regression coverage.
- `tests/test_operational_launch_cli.py` — three-file CLI output contains the extended fields.
- `cloud/orchestrator/inference.py` — require and validate seven new prediction columns, read local thresholds from `run_summary.json`, and report distributions.
- `tests/cloud/test_vertex_ai_custom_job_contract.py` — extended schema, threshold recomputation, failure cases, and report summaries.
- `tests/cloud/test_gcp_smoke_monthly_e2e.py` — live release validator reads prediction CSVs and checks the enhanced schema.
- `docs/03_workflow_runbook.md` — document the mandatory new-run rerun sequence.
- `docs/04_output_inventory.md` — document the seven added prediction fields.
- `README.md` — summarize enriched inference outputs and immutable rerun behavior.

---

### Task 1: Add the streaming population snapshot component

**Files:**
- Create: `model_pipeline/ipcch_launch_runtime/population.py`
- Create: `tests/test_population_output.py`

**Interfaces:**
- Consumes: normalized `(area_id, year, month, estimated_population)` records from either CSV streaming or pandas iteration.
- Produces: `POPULATION_OUTPUT_COLUMNS`, `PopulationSelectionError`, and `PopulationSnapshotBuilder(feature_year: int, feature_month: int)` with `add(...)` and `build(required_area_ids)` methods.
- `build(...)` returns `(snapshot, summary)`, where `snapshot[area_id]` contains `population_estimate`, `population_reference_period`, and `population_imputation_method`.

- [ ] **Step 1: Write focused failing tests for current-month selection, LOCF, future exclusion, and hard failures**

Create `tests/test_population_output.py`:

```python
import pytest

from model_pipeline.ipcch_launch_runtime.population import (
    PopulationSelectionError,
    PopulationSnapshotBuilder,
)


def test_population_snapshot_uses_current_then_latest_prior_without_future_leakage():
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)
    builder.add("A", 2026, 4, 120.0)
    builder.add("A", 2026, 5, 999.0)
    builder.add("B", 2025, 9, 80.0)
    builder.add("B", 2026, 5, 900.0)

    snapshot, summary = builder.build(["A", "B"])

    assert snapshot["A"] == {
        "population_estimate": 120.0,
        "population_reference_period": "2026-04",
        "population_imputation_method": "observed_feature_month",
    }
    assert snapshot["B"] == {
        "population_estimate": 80.0,
        "population_reference_period": "2025-09",
        "population_imputation_method": "last_observation_carried_forward",
    }
    assert summary == {
        "observed_feature_month_rows": 1,
        "last_observation_carried_forward_rows": 1,
        "missing_area_count": 0,
    }


def test_population_snapshot_rejects_area_without_current_or_prior_population():
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)
    builder.add("A", 2026, 5, 100.0)

    with pytest.raises(PopulationSelectionError, match="no current or prior population"):
        builder.build(["A"])


@pytest.mark.parametrize("value", [-1, float("inf"), "not-a-number"])
def test_population_snapshot_rejects_invalid_candidate_population(value):
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)

    with pytest.raises(PopulationSelectionError, match="finite and non-negative"):
        builder.add("A", 2026, 4, value)


def test_population_snapshot_rejects_conflicting_values_for_same_area_period():
    builder = PopulationSnapshotBuilder(feature_year=2026, feature_month=4)
    builder.add("A", 2026, 4, 100.0)

    with pytest.raises(PopulationSelectionError, match="conflicting population"):
        builder.add("A", 2026, 4, 101.0)
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_population_output.py -q -p no:cacheprovider
```

Expected: collection fails with `ModuleNotFoundError: No module named 'model_pipeline.ipcch_launch_runtime.population'`.

- [ ] **Step 3: Implement the minimal streaming selector**

Create `model_pipeline/ipcch_launch_runtime/population.py` with this interface and behavior:

```python
"""Output-only population selection for monthly assembly."""

import math


POPULATION_OUTPUT_COLUMNS = (
    "population_estimate",
    "population_reference_period",
    "population_imputation_method",
)


class PopulationSelectionError(ValueError):
    """Raised when a complete no-future population snapshot cannot be built."""


class PopulationSnapshotBuilder:
    def __init__(self, *, feature_year: int, feature_month: int):
        self.feature_period = (int(feature_year), int(feature_month))
        self._by_area = {}
        self._by_area_period = {}

    def add(self, area_id, year, month, population):
        area_id = str(area_id).strip()
        period = (int(year), int(month))
        if period > self.feature_period or _is_blank(population):
            return
        try:
            value = float(population)
        except (TypeError, ValueError) as exc:
            raise PopulationSelectionError(
                "population must be finite and non-negative"
            ) from exc
        if not math.isfinite(value) or value < 0:
            raise PopulationSelectionError(
                "population must be finite and non-negative"
            )
        key = (area_id, period)
        previous_same_period = self._by_area_period.get(key)
        if previous_same_period is not None and previous_same_period != value:
            raise PopulationSelectionError(
                "conflicting population values for the same area and period"
            )
        self._by_area_period[key] = value
        previous = self._by_area.get(area_id)
        if previous is None or period > previous[0]:
            self._by_area[area_id] = (period, value)

    def build(self, required_area_ids):
        required = [str(area_id).strip() for area_id in required_area_ids]
        missing = [area_id for area_id in required if area_id not in self._by_area]
        if missing:
            raise PopulationSelectionError(
                "area_id has no current or prior population: {0}".format(
                    ", ".join(missing[:5])
                )
            )
        snapshot = {}
        observed = 0
        carried = 0
        for area_id in required:
            period, value = self._by_area[area_id]
            is_current = period == self.feature_period
            method = (
                "observed_feature_month"
                if is_current
                else "last_observation_carried_forward"
            )
            observed += int(is_current)
            carried += int(not is_current)
            snapshot[area_id] = {
                "population_estimate": value,
                "population_reference_period": "{0:04d}-{1:02d}".format(*period),
                "population_imputation_method": method,
            }
        return snapshot, {
            "observed_feature_month_rows": observed,
            "last_observation_carried_forward_rows": carried,
            "missing_area_count": 0,
        }


def _is_blank(value):
    return value is None or str(value).strip() == "" or str(value).lower() == "nan"
```

- [ ] **Step 4: Run the population selector tests to verify GREEN**

Run the command from Step 2.

Expected: `6 passed`.

- [ ] **Step 5: Commit the shared population component**

```bash
git add \
  model_pipeline/ipcch_launch_runtime/population.py \
  tests/test_population_output.py \
  PROGRESS.md
git commit -m "feat: add population snapshot selector"
```

---

### Task 2: Attach output-only population fields during local and cloud assembly

**Files:**
- Modify: `Final_harmonise/00_build_monthly_ipcch_base_input.py:310-461`
- Modify: `cloud/orchestrator/assembly.py:29-133`
- Modify: `cloud/orchestrator/base_input_validation.py:19-66`
- Modify: `tests/test_build_monthly_ipcch_base_input.py`
- Modify: `tests/cloud/test_monthly_assembly_wrapper.py`

**Interfaces:**
- Consumes: `PopulationSnapshotBuilder` from Task 1 and the full historical/source panel already supplied to assembly.
- Produces: base-input columns `population_estimate`, `population_reference_period`, and `population_imputation_method`, plus `population_selection` summary counts.
- Guarantees: the pre-existing `estimated_population` source column is left unchanged and remains available to the model feature contract.

- [ ] **Step 1: Extend local and cloud assembly fixtures with population history and write RED assertions**

In `tests/test_build_monthly_ipcch_base_input.py`, add `estimated_population` to the panel fixture. Give area `101` a feature-month value of `120`, give area `102` a blank feature-month value and a 2026-03 value of `80`, and add a future 2026-05 value of `900` for `102`. Add assertions:

```python
self.assertEqual("120.0", rows[0]["population_estimate"])
self.assertEqual("2026-04", rows[0]["population_reference_period"])
self.assertEqual("observed_feature_month", rows[0]["population_imputation_method"])
self.assertEqual("80.0", rows[1]["population_estimate"])
self.assertEqual("2026-03", rows[1]["population_reference_period"])
self.assertEqual(
    "last_observation_carried_forward",
    rows[1]["population_imputation_method"],
)
self.assertEqual("", rows[1]["estimated_population"])
self.assertEqual(1, summary["population_selection"]["observed_feature_month_rows"])
self.assertEqual(
    1,
    summary["population_selection"]["last_observation_carried_forward_rows"],
)
```

Add a local failure test whose scaffold area has no current or prior population and assert `SystemExit` contains `no current or prior population`.

In `tests/cloud/test_monthly_assembly_wrapper.py`, add equivalent source history and assert the three fields and summary counts. Add a base-input validation failure test:

```python
def test_base_input_validation_rejects_missing_population_output_fields():
    base = pd.DataFrame({"area_id": ["A"], "year": [2026], "month": [4]})
    scaffold = pd.DataFrame({"area_id": ["A"], "year": [2026], "month": [4]})

    with pytest.raises(
        base_input_validation.BaseInputValidationError,
        match="population output columns",
    ):
        base_input_validation.validate_base_input(
            base_input=base,
            scaffold=scaffold,
            feature_month="2026-04",
        )
```

- [ ] **Step 2: Run assembly tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_build_monthly_ipcch_base_input.py \
  tests/cloud/test_monthly_assembly_wrapper.py \
  -q -p no:cacheprovider
```

Expected: failures report missing `population_estimate`, missing `population_selection`, and absent population hard-gate behavior.

- [ ] **Step 3: Stream population history in the local builder and attach fields without overwriting the model feature**

Update `Final_harmonise/00_build_monthly_ipcch_base_input.py` to import the Task 1 interface and change `load_source_slice` to accept required area IDs:

```python
from model_pipeline.ipcch_launch_runtime.population import (
    POPULATION_OUTPUT_COLUMNS,
    PopulationSelectionError,
    PopulationSnapshotBuilder,
)


def load_source_slice(path, year, month, excluded_columns, required_area_ids):
    require_file(path, "historical panel")
    handle, reader = open_reader(path)
    require_columns(
        reader.fieldnames,
        ["admin_code", "year", "month", "estimated_population"],
        "Historical panel",
    )
    source_columns = [
        column
        for column in reader.fieldnames
        if column not in SOURCE_KEY_COLUMNS
        and column not in excluded_columns
        and column not in POPULATION_OUTPUT_COLUMNS
        and not is_engineered_column(column)
    ]
    population_builder = PopulationSnapshotBuilder(
        feature_year=year, feature_month=month
    )
    by_key = {}
    duplicate_count = 0
    scanned_rows = 0
    matched_month_rows = 0
    with handle:
        for row in reader:
            scanned_rows += 1
            row_year = parse_int(row.get("year"), "historical panel year")
            row_month = parse_int(row.get("month"), "historical panel month")
            area_id = normalize_area_id(row.get("admin_code"))
            population_builder.add(
                area_id,
                row_year,
                row_month,
                row.get("estimated_population"),
            )
            if row_year != year or row_month != month:
                continue
            matched_month_rows += 1
            key = (area_id, str(year), str(month))
            if key in by_key:
                duplicate_count += 1
                continue
            by_key[key] = row
    population_snapshot, population_summary = population_builder.build(
        required_area_ids
    )
    return source_columns, by_key, population_snapshot, population_summary, {
        "scanned_rows": scanned_rows,
        "target_month_rows": matched_month_rows,
        "duplicate_rows": duplicate_count,
        "target_month_present_in_source": matched_month_rows > 0,
    }
```

In `build_monthly_base_input`, pass scaffold area IDs, append `POPULATION_OUTPUT_COLUMNS` to `output_header`, copy the snapshot entry into each `output_row`, and add `summary["population_selection"] = population_summary`. Convert `PopulationSelectionError` to the existing `fail(...)` path so CLI failures remain consistent.

- [ ] **Step 4: Attach the same snapshot in cloud assembly and add the pre-inference hard gate**

In `cloud/orchestrator/assembly.py`, build the snapshot before filtering `source_panel` to the selected month:

```python
from model_pipeline.ipcch_launch_runtime.population import (
    POPULATION_OUTPUT_COLUMNS,
    PopulationSnapshotBuilder,
)


population_builder = PopulationSnapshotBuilder(
    feature_year=year, feature_month=month
)
for row in source_panel[
    ["area_id", "year", "month", "estimated_population"]
].itertuples(index=False, name=None):
    population_builder.add(*row)
population_snapshot, population_summary = population_builder.build(
    scaffold["area_id"].tolist()
)
population_frame = pd.DataFrame.from_dict(population_snapshot, orient="index")
population_frame.index.name = "area_id"
population_frame = population_frame.reset_index()
```

Merge `population_frame` into `base` with `validate="many_to_one"`, and add `population_selection=population_summary` to the assembly report. Exclude `POPULATION_OUTPUT_COLUMNS` from `source_feature_columns`.

In `cloud/orchestrator/base_input_validation.py`, add `_validate_population_output` and call it before schema validation:

```python
def _validate_population_output(base_input: pd.DataFrame, feature_month: str) -> dict:
    required = list(POPULATION_OUTPUT_COLUMNS)
    missing = [column for column in required if column not in base_input.columns]
    if missing:
        raise BaseInputValidationError(
            f"base input missing population output columns: {missing}"
        )
    values = pd.to_numeric(base_input["population_estimate"], errors="coerce")
    if values.isna().any() or not values.map(math.isfinite).all() or (values < 0).any():
        raise BaseInputValidationError(
            "population_estimate must be finite and non-negative"
        )
    references = pd.to_datetime(
        base_input["population_reference_period"], format="%Y-%m", errors="coerce"
    )
    feature_period = pd.Timestamp(feature_month + "-01")
    if references.isna().any() or (references > feature_period).any():
        raise BaseInputValidationError(
            "population_reference_period must not be later than feature_month"
        )
    expected_methods = references.map(
        lambda value: (
            "observed_feature_month"
            if value == feature_period
            else "last_observation_carried_forward"
        )
    )
    if not expected_methods.equals(base_input["population_imputation_method"]):
        raise BaseInputValidationError(
            "population_imputation_method does not match reference period"
        )
    return {
        "observed_feature_month_rows": int(
            (expected_methods == "observed_feature_month").sum()
        ),
        "last_observation_carried_forward_rows": int(
            (expected_methods == "last_observation_carried_forward").sum()
        ),
    }
```

Add the returned summary to `base_input_validation_report` as `population_selection`.

- [ ] **Step 5: Run assembly and base-input tests to verify GREEN**

Run the command from Step 2.

Expected: all selected tests pass.

- [ ] **Step 6: Commit assembly population enrichment**

```bash
git add \
  Final_harmonise/00_build_monthly_ipcch_base_input.py \
  cloud/orchestrator/assembly.py \
  cloud/orchestrator/base_input_validation.py \
  tests/test_build_monthly_ipcch_base_input.py \
  tests/cloud/test_monthly_assembly_wrapper.py \
  PROGRESS.md
git commit -m "feat: add output population to monthly assembly"
```

---

### Task 3: Calculate qualitative uncertainty in core inference

**Files:**
- Create: `model_pipeline/ipcch_launch_runtime/uncertainty.py`
- Create: `tests/test_prediction_uncertainty.py`
- Modify: `model_pipeline/ipcch_launch_runtime/inference.py:9-105`
- Modify: `tests/test_operational_launch_inference.py`
- Modify: `tests/test_operational_launch_cli.py`

**Interfaces:**
- Consumes: a DataFrame containing the four score columns and the already-resolved per-target threshold mapping.
- Produces: `UNCERTAINTY_OUTPUT_COLUMNS`, `UNCERTAINTY_METHOD`, `calculate_qualitative_uncertainty(frame, thresholds) -> (fields, summary)`.
- Core `score_scope(...)` appends the returned fields and stores the returned summary under `scope_summary["uncertainty"]`.

- [ ] **Step 1: Write RED tests for boundary labels, tie order, and scope-specific thresholds**

Create `tests/test_prediction_uncertainty.py`:

```python
import pandas as pd
import pytest

from model_pipeline.ipcch_launch_runtime.uncertainty import (
    UNCERTAINTY_METHOD,
    calculate_qualitative_uncertainty,
)


def test_uncertainty_labels_use_approved_boundaries_and_fixed_tie_order():
    scores = pd.DataFrame(
        {
            "phase2_worse_score": [0.21, 0.25, 0.30],
            "phase3_worse_score": [0.80, 0.80, 0.80],
            "phase4_worse_score": [0.80, 0.80, 0.80],
            "phase5_worse_score": [0.80, 0.80, 0.80],
        }
    )
    thresholds = {
        "phase2_worse": 0.20,
        "phase3_worse": 0.20,
        "phase4_worse": 0.20,
        "phase5_worse": 0.20,
    }

    fields, summary = calculate_qualitative_uncertainty(scores, thresholds)

    assert fields["prediction_uncertainty"].tolist() == ["high", "medium", "low"]
    assert fields["decision_margin"].tolist() == pytest.approx([0.01, 0.05, 0.10])
    assert fields["uncertainty_critical_boundary"].tolist() == [
        "phase2_worse",
        "phase2_worse",
        "phase2_worse",
    ]
    assert set(fields["uncertainty_method"]) == {UNCERTAINTY_METHOD}
    assert summary["label_counts"] == {"high": 1, "medium": 1, "low": 1}


def test_uncertainty_uses_each_target_threshold_and_phase_order_for_ties():
    scores = pd.DataFrame(
        {
            "phase2_worse_score": [0.40],
            "phase3_worse_score": [0.35],
            "phase4_worse_score": [0.90],
            "phase5_worse_score": [0.90],
        }
    )
    thresholds = {
        "phase2_worse": 0.45,
        "phase3_worse": 0.30,
        "phase4_worse": 0.20,
        "phase5_worse": 0.20,
    }

    fields, _ = calculate_qualitative_uncertainty(scores, thresholds)

    assert fields.loc[0, "decision_margin"] == pytest.approx(0.05)
    assert fields.loc[0, "uncertainty_critical_boundary"] == "phase2_worse"
```

- [ ] **Step 2: Run the uncertainty unit tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_prediction_uncertainty.py -q -p no:cacheprovider
```

Expected: collection fails because `uncertainty.py` does not exist.

- [ ] **Step 3: Implement the deterministic calculation module**

Create `model_pipeline/ipcch_launch_runtime/uncertainty.py`:

```python
"""Qualitative distance-to-threshold uncertainty for launch predictions."""

import math

import pandas as pd


TARGETS = (
    "phase2_worse",
    "phase3_worse",
    "phase4_worse",
    "phase5_worse",
)
UNCERTAINTY_METHOD = "qualitative_threshold_margin_v1"
UNCERTAINTY_OUTPUT_COLUMNS = (
    "prediction_uncertainty",
    "decision_margin",
    "uncertainty_critical_boundary",
    "uncertainty_method",
)


class UncertaintyError(ValueError):
    """Raised when uncertainty fields cannot be calculated."""


def calculate_qualitative_uncertainty(frame, thresholds):
    margins = {}
    for target in TARGETS:
        score_column = "{0}_score".format(target)
        if score_column not in frame.columns or target not in thresholds:
            raise UncertaintyError(
                "missing score or resolved threshold for {0}".format(target)
            )
        scores = pd.to_numeric(frame[score_column], errors="coerce")
        threshold = float(thresholds[target])
        if (
            scores.isna().any()
            or not scores.map(math.isfinite).all()
            or not math.isfinite(threshold)
        ):
            raise UncertaintyError("scores and thresholds must be finite")
        margins[target] = (scores - threshold).abs().round(12)
    margin_frame = pd.DataFrame(margins, index=frame.index)
    decision_margin = margin_frame.min(axis=1)
    critical_boundary = margin_frame.idxmin(axis=1)
    labels = pd.Series("low", index=frame.index, dtype="object")
    labels.loc[decision_margin < 0.10] = "medium"
    labels.loc[decision_margin < 0.05] = "high"
    fields = pd.DataFrame(
        {
            "prediction_uncertainty": labels,
            "decision_margin": decision_margin.astype("float64"),
            "uncertainty_critical_boundary": critical_boundary,
            "uncertainty_method": UNCERTAINTY_METHOD,
        },
        index=frame.index,
    )
    counts = labels.value_counts().reindex(["high", "medium", "low"], fill_value=0)
    summary = {
        "method": UNCERTAINTY_METHOD,
        "label_counts": {key: int(value) for key, value in counts.items()},
        "decision_margin": {
            "min": float(decision_margin.min()),
            "median": float(decision_margin.median()),
            "max": float(decision_margin.max()),
        },
    }
    return fields, summary
```

- [ ] **Step 4: Integrate population propagation and uncertainty into `score_scope`**

In `model_pipeline/ipcch_launch_runtime/inference.py`:

```python
from model_pipeline.ipcch_launch_runtime.population import POPULATION_OUTPUT_COLUMNS
from model_pipeline.ipcch_launch_runtime.uncertainty import (
    UncertaintyError,
    calculate_qualitative_uncertainty,
)
```

Pass `feature_month` into `_validate_inputs`, require all population output columns there, validate population values as finite/non-negative, and change `_identity_frame` to preserve:

```python
_validate_inputs(
    monthly_rows,
    feature_matrix,
    models,
    thresholds,
    monotonicity_policy,
    feature_month,
)
```

```python
identity_columns = [
    column
    for column in (
        "area_id",
        "admin_code",
        "_row_id",
        *POPULATION_OUTPUT_COLUMNS,
    )
    if column in monthly_rows.columns
]
```

Also validate reference-period and method consistency against `feature_month`:

```python
references = pd.to_datetime(
    monthly_rows["population_reference_period"],
    format="%Y-%m",
    errors="coerce",
)
feature_period = pd.Timestamp(str(feature_month) + "-01")
if references.isna().any() or (references > feature_period).any():
    raise InferenceError(
        "population_reference_period must not be later than feature_month"
    )
expected_methods = references.map(
    lambda value: (
        "observed_feature_month"
        if value == feature_period
        else "last_observation_carried_forward"
    )
)
if not expected_methods.equals(monthly_rows["population_imputation_method"]):
    raise InferenceError(
        "population_imputation_method does not match reference period"
    )
```

After all four scores and resolved thresholds are available, add:

```python
uncertainty_fields, uncertainty_summary = calculate_qualitative_uncertainty(
    output, applied_thresholds
)
for column in uncertainty_fields.columns:
    output[column] = uncertainty_fields[column]
```

Store `"uncertainty": uncertainty_summary` in the returned scope summary and add `UncertaintyError` to the CLI's expected error tuple in `model_pipeline/run_operational_launch_inference.py`.

- [ ] **Step 5: Extend core inference and CLI tests and verify prediction values remain unchanged**

Update the `_score` fixture in `tests/test_operational_launch_inference.py` so default `monthly_rows` includes valid population fields:

```python
monthly_rows = pd.DataFrame(
    {
        "area_id": ["A", "B"],
        "population_estimate": [100.0, 200.0],
        "population_reference_period": ["2026-04", "2025-09"],
        "population_imputation_method": [
            "observed_feature_month",
            "last_observation_carried_forward",
        ],
    }
)
```

Assert population columns are unchanged in scored output, uncertainty fields are present, and pre-existing expected scores/predictions retain their current values. Add a failure test for missing population columns.

Update CLI fixtures and fake `run_scope` outputs in `tests/test_operational_launch_cli.py` to include the seven required fields, then assert every generated CSV contains them.

- [ ] **Step 6: Run core inference tests to verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_prediction_uncertainty.py \
  tests/test_operational_launch_inference.py \
  tests/test_operational_launch_cli.py \
  -q -p no:cacheprovider
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit core inference enrichment**

```bash
git add \
  model_pipeline/ipcch_launch_runtime/uncertainty.py \
  model_pipeline/ipcch_launch_runtime/inference.py \
  model_pipeline/run_operational_launch_inference.py \
  tests/test_prediction_uncertainty.py \
  tests/test_operational_launch_inference.py \
  tests/test_operational_launch_cli.py \
  PROGRESS.md
git commit -m "feat: add qualitative prediction uncertainty"
```

---

### Task 4: Enforce the extended prediction contract in the Vertex wrapper

**Files:**
- Modify: `cloud/orchestrator/inference.py:19-241,515-797,834-859`
- Modify: `tests/cloud/test_vertex_ai_custom_job_contract.py`
- Modify: `tests/cloud/test_report_contracts.py`

**Interfaces:**
- Consumes: enriched base input, enriched local prediction CSVs, and per-scope resolved thresholds stored in local `run_summary.json`.
- Produces: cloud-validated prediction CSVs and `inference_report.json` with `population_selection` and `uncertainty_summary` grouped by scope.
- Changes `_run_script_and_collect_predictions(...)` return type to `(predictions, local_run_summary, command, command_result)`.

- [ ] **Step 1: Add RED cloud contract tests for seven required fields and independent uncertainty recomputation**

Update the prediction fixture helper in `tests/cloud/test_vertex_ai_custom_job_contract.py` to include:

```python
"population_estimate": [100.0],
"population_reference_period": ["2026-04"],
"population_imputation_method": ["observed_feature_month"],
"prediction_uncertainty": ["high"],
"decision_margin": [0.01],
"uncertainty_critical_boundary": ["phase2_worse"],
"uncertainty_method": ["qualitative_threshold_margin_v1"],
```

Pass this threshold mapping to `validate_prediction_outputs`:

```python
thresholds_by_scope = {
    scope: {
        "phase2_worse": 0.2,
        "phase3_worse": 0.2,
        "phase4_worse": 0.2,
        "phase5_worse": 0.2,
    }
    for scope in ("0m", "6m", "12m")
}
```

Add parameterized failure cases for a wrong label, wrong margin, future population reference period, changed population across scopes, and missing local run-summary thresholds. Add assertions that the report contains per-scope population method counts and uncertainty label counts.

- [ ] **Step 2: Run Vertex wrapper tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/cloud/test_vertex_ai_custom_job_contract.py \
  tests/cloud/test_report_contracts.py \
  -q -p no:cacheprovider
```

Expected: failures report missing required columns, unsupported `thresholds_by_scope`, and absent report summaries.

- [ ] **Step 3: Extend required columns and validate population alignment**

In `cloud/orchestrator/inference.py`, import `POPULATION_OUTPUT_COLUMNS`, `UNCERTAINTY_OUTPUT_COLUMNS`, `UNCERTAINTY_METHOD`, and `calculate_qualitative_uncertainty`. Extend `REQUIRED_PREDICTION_COLUMNS` with all seven fields.

Change the validator signature:

```python
def validate_prediction_outputs(
    predictions: dict[str, pd.DataFrame],
    *,
    feature_month: str,
    base_input: pd.DataFrame | None = None,
    reference_predictions: dict[str, pd.DataFrame] | None = None,
    expected_model_package_id: str | None = None,
    thresholds_by_scope: dict[str, dict[str, float]],
) -> tuple[dict[str, pd.DataFrame], dict]:
```

Require a threshold mapping for every scope. In `_validate_prediction_base_alignment`, compare all three population columns against base input in addition to `_row_id` and optional `admin_code`. This makes cross-scope consistency a consequence of matching the same base input.

Change the scope validator signature and call site to pass the resolved mapping:

```python
def _validate_prediction_scope_contract(
    frame: pd.DataFrame,
    *,
    scope: str,
    feature_month: str,
    thresholds: dict[str, float],
    expected_model_package_id: str | None = None,
) -> None:
```

- [ ] **Step 4: Independently recompute uncertainty and add report summaries**

Inside `_validate_prediction_scope_contract`, calculate expected fields from scores and `thresholds_by_scope[scope]`:

```python
expected_uncertainty, _ = calculate_qualitative_uncertainty(
    frame, thresholds_by_scope[scope]
)
margin_delta = (
    pd.to_numeric(frame["decision_margin"], errors="coerce")
    - expected_uncertainty["decision_margin"]
).abs()
if margin_delta.isna().any() or (margin_delta > 1e-12).any():
    raise ValueError(f"{scope} prediction decision_margin is inconsistent")
for column in (
    "prediction_uncertainty",
    "uncertainty_critical_boundary",
    "uncertainty_method",
):
    if not frame[column].astype(str).equals(
        expected_uncertainty[column].astype(str)
    ):
        raise ValueError(f"{scope} prediction {column} is inconsistent")
```

Build report summaries:

```python
population_selection = {
    scope: enriched[scope]["population_imputation_method"]
    .value_counts()
    .to_dict()
    for scope in PREDICTION_SCOPES
}
uncertainty_summary = {
    scope: {
        "method": UNCERTAINTY_METHOD,
        "label_counts": enriched[scope]["prediction_uncertainty"]
        .value_counts()
        .reindex(["high", "medium", "low"], fill_value=0)
        .astype(int)
        .to_dict(),
        "decision_margin": {
            "min": float(enriched[scope]["decision_margin"].min()),
            "median": float(enriched[scope]["decision_margin"].median()),
            "max": float(enriched[scope]["decision_margin"].max()),
        },
    }
    for scope in PREDICTION_SCOPES
}
```

Include both objects in `inference_report.json` and add them to the report-contract test's required field set.

- [ ] **Step 5: Read resolved thresholds from the local inference run summary**

After the command succeeds in `_run_script_and_collect_predictions`, read `output_dir / "run_summary.json"`, require `status == "passed"`, and extract:

```python
thresholds_by_scope = {
    scope: local_run_summary["scope_summaries"][scope.removesuffix("m")][
        "thresholds"
    ]
    for scope in PREDICTION_SCOPES
}
```

Return the local summary with predictions. In `_run_inference_wrapper_success`, pass these thresholds into `validate_prediction_outputs` and record them in `report["resolved_thresholds_by_scope"]`.

For `allow_synthetic_predictions=True`, use an explicit test-only threshold mapping of `0.2` for all four targets and generate uncertainty fields through `calculate_qualitative_uncertainty`; do not hand-author synthetic labels.

Update fake command runners in the test file so they write a valid `run_summary.json` containing per-scope thresholds alongside the three prediction CSVs.

Update every inline base-input CSV fixture in this test file to use this minimum
valid population contract:

```text
area_id,year,month,admin_code,_row_id,population_estimate,population_reference_period,population_imputation_method
A,2026,4,A,0,100.0,2026-04,observed_feature_month
```

- [ ] **Step 6: Run Vertex wrapper and report tests to verify GREEN**

Run the command from Step 2.

Expected: all selected tests pass.

- [ ] **Step 7: Commit the cloud prediction contract**

```bash
git add \
  cloud/orchestrator/inference.py \
  tests/cloud/test_vertex_ai_custom_job_contract.py \
  tests/cloud/test_report_contracts.py \
  PROGRESS.md
git commit -m "feat: validate enriched cloud predictions"
```

---

### Task 5: Prove regression safety, update operator docs, and prepare the new immutable run

**Files:**
- Modify: `tests/cloud/test_gcp_smoke_monthly_e2e.py`
- Modify: `docs/03_workflow_runbook.md:184-202`
- Modify: `docs/04_output_inventory.md:44-80`
- Modify: `README.md:90-145`
- Do not commit: generated CSVs under ignored `Outcome/ipcch_unified/model_input/` or `Outcome/ipcch_unified/predictions/`.

**Interfaces:**
- Consumes: all implementation from Tasks 1-4 and existing 2026-04 local predictions as regression evidence.
- Produces: full deterministic test evidence, temporary enhanced 2026-04 outputs, documented new-run procedure, and a gated live-smoke validator for the extended schema.

- [ ] **Step 1: Extend the live smoke release validator to inspect prediction CSV contents**

In `tests/cloud/test_gcp_smoke_monthly_e2e.py`, define:

```python
ENRICHED_PREDICTION_COLUMNS = {
    "population_estimate",
    "population_reference_period",
    "population_imputation_method",
    "prediction_uncertainty",
    "decision_margin",
    "uncertainty_critical_boundary",
    "uncertainty_method",
}
```

In `validate_release_manifest_after_smoke`, parse every prediction artifact:

```python
for path in manifest["prediction_output_paths"]:
    frame = pd.read_csv(StringIO(store.read_text(path)))
    assert ENRICHED_PREDICTION_COLUMNS <= set(frame.columns)
    assert frame["population_estimate"].notna().all()
    assert set(frame["prediction_uncertainty"]) <= {"high", "medium", "low"}
    assert set(frame["uncertainty_method"]) == {
        "qualitative_threshold_margin_v1"
    }
```

Update local smoke fixtures to contain these columns.

- [ ] **Step 2: Update operator-facing documentation**

Add the following exact behavior to `docs/03_workflow_runbook.md`, `docs/04_output_inventory.md`, and `README.md`:

```text
Enhanced population and uncertainty fields are produced only by a new complete
monthly run. Do not edit an existing prediction CSV or released run in place.
Use a new run_id, rerun monthly assembly, then run Vertex AI inference with the
same immutable model package. population_estimate is output-only; the model
continues to receive the original estimated_population feature. The uncertainty
label is qualitative distance-to-threshold stability, not a confidence interval.
```

List all seven fields and the `high < 0.05`, `medium < 0.10`, `low >= 0.10` rules. State that country-level percentage calculation remains downstream scope.

- [ ] **Step 3: Run the complete deterministic regression suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_population_output.py \
  tests/test_prediction_uncertainty.py \
  tests/test_build_monthly_ipcch_base_input.py \
  tests/test_operational_launch_inference.py \
  tests/test_operational_launch_cli.py \
  tests/test_operational_launch_input_contract.py \
  tests/cloud \
  -q -p no:cacheprovider
```

Expected: all tests pass; the gated live GCP test is skipped unless `IPCCH_GCP_SMOKE_ENABLED` is set.

- [ ] **Step 4: Generate temporary enhanced 2026-04 local artifacts without overwriting existing results**

Run:

```bash
mkdir -p /tmp/ipcch-pop-uncertainty-202604/model_input
mkdir -p /tmp/ipcch-pop-uncertainty-202604/predictions
PYTHONDONTWRITEBYTECODE=1 python3 Final_harmonise/00_build_monthly_ipcch_base_input.py \
  --year 2026 \
  --month 4 \
  --scaffold Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv \
  --historical-panel Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv \
  --fixed-slow-features Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv \
  --output /tmp/ipcch-pop-uncertainty-202604/model_input/ipcch_monthly_base_input_202604.csv \
  --summary-output /tmp/ipcch-pop-uncertainty-202604/model_input/ipcch_monthly_base_input_202604_summary.json
PYTHONDONTWRITEBYTECODE=1 python3 model_pipeline/run_operational_launch_inference.py \
  --input /tmp/ipcch-pop-uncertainty-202604/model_input/ipcch_monthly_base_input_202604.csv \
  --model-package model_artifacts/launch_2026_04 \
  --output-dir /tmp/ipcch-pop-uncertainty-202604/predictions \
  --feature-month 2026-04 \
  --no-map \
  --overwrite
```

Expected: three enhanced prediction CSVs and `run_summary.json` are written under `/tmp`; tracked and ignored existing results remain untouched.

- [ ] **Step 5: Compare existing and enhanced model results row by row**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path

import pandas as pd

old_root = Path("Outcome/ipcch_unified/predictions/202604")
new_root = Path("/tmp/ipcch-pop-uncertainty-202604/predictions")
unchanged = [
    "area_id",
    "phase2_worse_score",
    "phase2_worse_pred",
    "phase3_worse_score",
    "phase3_worse_pred",
    "phase4_worse_score",
    "phase4_worse_pred",
    "phase5_worse_score",
    "phase5_worse_pred",
    "overall_phase_pred",
    "feature_period",
    "target_period",
    "scope_months",
    "model_package_id",
]
added = {
    "population_estimate",
    "population_reference_period",
    "population_imputation_method",
    "prediction_uncertainty",
    "decision_margin",
    "uncertainty_critical_boundary",
    "uncertainty_method",
}
for scope in ("0m", "6m", "12m"):
    name = f"ipcch_launch_202604_scope_{scope}_predictions.csv"
    old = pd.read_csv(old_root / name)
    new = pd.read_csv(new_root / name)
    pd.testing.assert_frame_equal(
        old[unchanged].reset_index(drop=True),
        new[unchanged].reset_index(drop=True),
        check_exact=True,
    )
    assert added <= set(new.columns)
    assert new["population_estimate"].notna().all()
print("enhanced outputs preserve all existing model results")
PY
```

Expected output: `enhanced outputs preserve all existing model results`.

- [ ] **Step 6: Validate documentation and repository cleanliness**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; only intended source, test, documentation, `PROGRESS.md`, and plan-related changes appear. Generated `/tmp` artifacts and ignored `Outcome/...` files do not appear.

- [ ] **Step 7: Commit tests and operator documentation**

```bash
git add \
  tests/cloud/test_gcp_smoke_monthly_e2e.py \
  docs/03_workflow_runbook.md \
  docs/04_output_inventory.md \
  README.md \
  PROGRESS.md
git commit -m "docs: document enriched inference rerun"
```

- [ ] **Step 8: Execute a new live cloud run only when deployment prerequisites are present**

Confirm ADC, exact service accounts, bucket, Cloud Run Job, and manifest URI already exist. Confirm the manifest points to a digest-pinned runtime image built from the completed implementation commit, not the previous image. Then use a unique run ID:

```bash
export IPCCH_GCP_SMOKE_ENABLED=1
export IPCCH_GCP_PROJECT_ID=food-crisis-modeling
export IPCCH_GCP_REGION=us-central1
export IPCCH_GCP_FEATURE_MONTH=2026-04
export IPCCH_GCP_RUN_ID=smoke-202604-pop-uncertainty-$(date -u +%Y%m%d-%H%M%S)
: "${IPCCH_GCP_INPUT_MANIFEST_URI:?export the immutable GCS input manifest URI}"
export IPCCH_GCP_CLOUD_RUN_JOB=ipcch-monthly-e2e-orchestrator
: "${IPCCH_GCP_RELEASE_MANIFEST_URI:?export the expected release manifest URI}"
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/cloud/test_gcp_smoke_monthly_e2e.py \
  -q -p no:cacheprovider
```

Expected: the gated test dispatches the new Cloud Run execution, the new immutable release becomes `current`, and all three released prediction CSVs contain the seven new fields. If IAM or named infrastructure is missing, record the exact blocker in `PROGRESS.md`; do not reuse or mutate an old run ID.

---

## Final Verification Gate

Before claiming completion, run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  tests/test_population_output.py \
  tests/test_prediction_uncertainty.py \
  tests/test_build_monthly_ipcch_base_input.py \
  tests/test_operational_launch_inference.py \
  tests/test_operational_launch_cli.py \
  tests/test_operational_launch_input_contract.py \
  tests/cloud \
  -q -p no:cacheprovider
git diff --check
git status --short --branch
```

Required evidence:

- All deterministic tests pass.
- The three temporary enhanced 2026-04 outputs contain all seven new fields.
- Row-by-row comparison proves all original scores and predictions are exactly unchanged.
- Existing released/local result files were not edited in place.
- A live GCP run is either successful under a new `run_id` or has an exact external IAM/infrastructure blocker recorded without weakening the local completion claim.
