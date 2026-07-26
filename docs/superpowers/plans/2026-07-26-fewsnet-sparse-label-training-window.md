# FEWSNET Sparse-Label Training Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make shared FEWSNET training select the latest 36 actually labeled
target periods without requiring calendar contiguity, preserve the existing
30/6 threshold procedure, and complete the full unsampled local `2026-04`
acceptance run.

**Architecture:** Change only the shared horizon selector and exact-window
validator. The selector chooses the latest distinct labeled periods at or
before the declared boundary; the trainer continues to split those periods
chronologically, select the threshold on the last six, and refit on all 36.
The local runner and future Vertex training consume the same corrected core
semantics without a local-only branch.

**Tech Stack:** Python 3.12, pandas 3.0.0, NumPy 2.4.2, scikit-learn 1.8.0,
joblib 1.5.3, imbalanced-learn 0.14.0, pytest 9.1.1, GitNexus, and local
filesystem publication.

## Global Constraints

- The authoritative design is
  `docs/superpowers/specs/2026-07-26-fewsnet-sparse-label-training-window-design.md`,
  approved at commit `64e6328926a96613c8a5fa26534091e0ac160b61`,
  SHA-256
  `8ae88a0c67de86db8a0c7bbfb7ae65f9107ed491a49664f8adbe4207129eabc8`.
- Execute in the existing linked worktree
  `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.worktrees/fewsnet-local-202604`
  on branch `feat/fewsnet-local-202604`.
- Reconcile tracked `PROGRESS.md` and ignored
  `.superpowers/sdd/2026-07-26-fewsnet-local-202604-prediction-experiment/progress.md`
  before each task. Record exact RED/GREEN commands, results, commit identity,
  blocker state, and the next task.
- Use `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` for every pytest
  command.
- Preserve all dependency pins, including `scikit-learn==1.8.0` and
  `imbalanced-learn==0.14.0`, and preserve the reviewed SMOTE compatibility
  bridge.
- The selector signature remains
  `select_training_window(aligned, latest_label_month, months=36) -> pd.DataFrame`.
  The `months` parameter counts distinct labeled monthly periods.
- Require the latest-label boundary itself to be represented and require at
  least the requested number of eligible periods. Do not move the boundary or
  silently shorten the window.
- Preserve `split_threshold_window`: the first 30 selected periods fit the
  temporary model, the last six validate the threshold, and all 36 fit the
  final model.
- Do not forward-fill, interpolate, synthesize, or weight missing calendar
  months. Calendar gaps remain absent.
- Report start/end fields are bounds over observed periods. Do not add a
  report schema version, package schema version, or prediction column.
- Preserve Random Forest, SMOTE, imputation, fixed partition routing, pooled
  fallbacks, threshold search, probability, binary-label, and population
  behavior.
- Preserve `probability_crisis` in `[0, 1]` and
  `predicted_crisis = int(probability_crisis >= threshold)`. Add no phase or
  categorical-uncertainty field.
- The approved panel is
  `/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv`,
  SHA-256
  `510375f58cd835e694b6e287cce9439bbe1b6246d752daabc8151df8ffdda61d`.
- The matching `.audit.json` has SHA-256
  `1c37232629dd11f657e77c361a033f9a30e910441e5d8c73ea703f3b22ef1166`.
- The real selected window is 36 periods bounded by `2014-04..2026-02`;
  fit bounds are `2014-04..2023-06`; validation periods are `2023-10`,
  `2024-02`, `2024-06`, `2024-10`, `2025-10`, and `2026-02`.
- Expected real aligned counts are 188,643 total rows, 155,067 fit rows, and
  33,576 validation rows for every horizon.
- Do not sample the real run. Do not pass `--overwrite` while
  `Outcome/fewsnet_partitioned_rf/` is absent.
- Do not mutate anything under `Outcome/ipcch_unified/`; prove byte identity
  with before/after manifests.
- Make no GCP, GCS, Vertex AI, Model Registry, Batch Prediction, alias,
  endpoint, network, or production-pointer mutation.
- Before editing an existing function, run GitNexus upstream impact and
  report direct callers, affected processes, and risk. Stop and warn before
  any HIGH or CRITICAL edit.
- Planning-time impact is LOW: `select_training_window` has four direct
  dependents and one affected process; `_validate_exact_training_window` has
  one direct dependent and two affected processes; `train_horizon_model` has
  one direct dependent and one affected process. Re-run these checks before
  editing rather than relying on the planning snapshot.
- Before every commit, stage only intended files, run GitNexus
  `detect_changes(scope="staged", repo="IPCCH_operational", worktree=...)`,
  inspect `git diff --cached --stat`, and require
  `git diff --cached --check` to exit zero.
- Do not retain analyzer-generated count-only changes in `AGENTS.md` or
  `CLAUDE.md`.

---

## File Structure

- Modify `fewsnet_partitioned_rf_pipeline/core/horizons.py` for latest
  distinct-period selection and boundary/history validation.
- Modify `fewsnet_partitioned_rf_pipeline/core/training.py` to retain exactly
  36 periods without requiring calendar contiguity.
- Modify `tests/fewsnet_partitioned_rf/test_horizons.py` for sparse selection,
  boundary, insufficient-history, dense-compatibility, and ordering tests.
- Modify `tests/fewsnet_partitioned_rf/test_training_inference.py` for sparse
  30/6 training, report bounds, and 35-period rejection.
- Modify `docs/09_fewsnet_partitioned_rf_runbook.md` to document the corrected
  operational meaning.
- Modify `PROGRESS.md` plus the ignored progress and Task 5 report under
  `.superpowers/sdd/2026-07-26-fewsnet-local-202604-prediction-experiment/`.
- Generate ignored artifacts only under `Outcome/fewsnet_partitioned_rf/`.

No new production module, model schema, prediction schema, configuration flag,
or cloud entrypoint is created.

---

### Task 1: Select the Latest 36 Distinct Labeled Periods

**Files:**

- Modify: `fewsnet_partitioned_rf_pipeline/core/horizons.py:203-215`
- Modify: `tests/fewsnet_partitioned_rf/test_horizons.py:32-225`
- Modify: `PROGRESS.md`
- Modify ignored progress ledger under the active SDD feature directory.

**Interfaces:**

- Consumes: `_validate_positive_integer`, `_normalize_month_value`,
  `_prepare_aligned_frame`, `_sort_aligned_rows`, and
  `TARGET_MONTH_COLUMN`.
- Produces: unchanged public signature
  `select_training_window(aligned, latest_label_month, months=36) -> pd.DataFrame`.
- Guarantees: exactly the latest requested distinct periods, all their rows,
  the declared boundary present, deterministic sort order, and fail-closed
  behavior for insufficient history.

- [ ] **Step 1: Reconcile the ledger and clean state**

Read both progress ledgers and `git status --short`. Record Task 1 as in
progress. Confirm no tracked change exists and
`Outcome/fewsnet_partitioned_rf/` remains absent.

- [ ] **Step 2: Re-run upstream impact before editing the selector**

Run GitNexus upstream impact for `select_training_window` in
`core/horizons.py`, including tests. Record risk, direct dependents, and the
affected training-worker process. Stop before editing on HIGH or CRITICAL.

- [ ] **Step 3: Add the sparse selector fixture and failing tests**

Add below `aligned_fixture()`:

```python
def sparse_aligned_fixture() -> tuple[pd.DataFrame, list[pd.Period]]:
    rows: list[dict[str, object]] = []
    target_months = [
        pd.Period("2018-01", freq="M") + 2 * index
        for index in range(42)
    ]
    for admin_code in ("B", "A"):
        for month_index, target_month in enumerate(target_months):
            rows.append(
                {
                    "admin_code": admin_code,
                    "feature_month": str(target_month),
                    "target_month": target_month.start_time,
                    "fews_ipc_crisis": float(month_index % 2),
                    "predictor": float(target_month.ordinal),
                }
            )
    return pd.DataFrame(reversed(rows)), target_months
```

Add next to the dense window test:

```python
def test_training_window_selects_latest_36_sparse_labeled_periods():
    frame, target_months = sparse_aligned_fixture()
    latest_label_month = target_months[-2]
    eligible_periods = [
        period for period in target_months if period <= latest_label_month
    ]
    expected_periods = eligible_periods[-36:]

    training = select_training_window(
        frame,
        latest_label_month=latest_label_month,
        months=36,
    )

    assert sorted(training["target_month"].unique()) == expected_periods
    assert len(training) == 72
    assert training["target_month"].nunique() == 36
    assert not training["target_month"].eq(target_months[-1]).any()
    assert list(
        training[["admin_code", "feature_month"]].itertuples(
            index=False,
            name=None,
        )
    ) == sorted(
        training[["admin_code", "feature_month"]].itertuples(
            index=False,
            name=None,
        )
    )


def test_training_window_requires_the_latest_label_boundary_period():
    frame, target_months = sparse_aligned_fixture()
    unlabeled_boundary = target_months[-2] + 1

    with pytest.raises(
        ValueError,
        match="latest_label_month must be represented",
    ):
        select_training_window(
            frame,
            latest_label_month=unlabeled_boundary,
            months=36,
        )


def test_training_window_requires_requested_distinct_period_count():
    frame, target_months = sparse_aligned_fixture()
    retained_periods = set(target_months[-35:])
    only_35 = frame.loc[
        pd.to_datetime(frame["target_month"])
        .dt.to_period("M")
        .isin(retained_periods)
    ]

    with pytest.raises(
        ValueError,
        match="at least 36 distinct labeled target_month periods",
    ):
        select_training_window(
            only_35,
            latest_label_month=target_months[-1],
            months=36,
        )
```

Keep `test_current_36_month_and_six_month_windows_are_exact` unchanged as the
dense-cadence compatibility regression.

- [ ] **Step 4: Run the new tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_horizons.py::test_training_window_selects_latest_36_sparse_labeled_periods \
  tests/fewsnet_partitioned_rf/test_horizons.py::test_training_window_requires_the_latest_label_boundary_period \
  tests/fewsnet_partitioned_rf/test_horizons.py::test_training_window_requires_requested_distinct_period_count \
  -q -p no:cacheprovider
```

Expected RED: old dense-interval selection returns fewer than 36 sparse
periods, accepts an absent boundary, and does not raise the selector-level
insufficient-history error.

- [ ] **Step 5: Implement the minimal distinct-period selector**

Replace the function with:

```python
def select_training_window(
    aligned: pd.DataFrame,
    latest_label_month: object,
    months: int = 36,
) -> pd.DataFrame:
    month_count = _validate_positive_integer(months, "months")
    end = _normalize_month_value(latest_label_month, "latest_label_month")
    working = _prepare_aligned_frame(aligned)
    eligible = working.loc[
        working[TARGET_MONTH_COLUMN].le(end)
    ].copy()
    target_periods = sorted(eligible[TARGET_MONTH_COLUMN].unique())
    if end not in target_periods:
        raise ValueError(
            "latest_label_month must be represented by labeled "
            "target_month rows"
        )
    if len(target_periods) < month_count:
        raise ValueError(
            "training requires at least "
            f"{month_count} distinct labeled target_month periods at or "
            "before latest_label_month"
        )
    selected_periods = set(target_periods[-month_count:])
    selected = eligible.loc[
        eligible[TARGET_MONTH_COLUMN].isin(selected_periods)
    ].copy()
    return _sort_aligned_rows(selected)
```

Do not alter `split_threshold_window`.

- [ ] **Step 6: Verify GREEN and the full horizon regression**

Repeat Step 4, then run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_horizons.py \
  -q -p no:cacheprovider
```

Expected: all horizon tests pass, including the dense case and existing month,
alignment, split, and inference validations.

- [ ] **Step 7: Record evidence and commit Task 1**

Update both ledgers with impact, RED/GREEN commands and observed results, files
changed, and Task 2 as next. Stage only `core/horizons.py`,
`test_horizons.py`, and `PROGRESS.md`. Run staged GitNexus detection, staged
stat, and staged whitespace check, then commit:

```bash
git commit -m "fix: select sparse FEWSNET label periods"
```

---

### Task 2: Accept Sparse 36-Period Training and Preserve 30/6 Reports

**Files:**

- Modify: `fewsnet_partitioned_rf_pipeline/core/training.py:398-424`
- Modify: the `train_horizon_model` docstring in `core/training.py`
- Modify: `tests/fewsnet_partitioned_rf/test_training_inference.py:79-101`
- Modify: `tests/fewsnet_partitioned_rf/test_training_inference.py:483-520`
- Modify: `docs/09_fewsnet_partitioned_rf_runbook.md:2742-2857`
- Modify: `PROGRESS.md`
- Modify ignored progress ledger under the active SDD feature directory.

**Interfaces:**

- Consumes: unchanged `split_threshold_window(training, validation_months=6)`.
- Produces: unchanged private return contract
  `_validate_exact_training_window(training) -> (fit, validation, combined)`.
- Produces: unchanged public
  `train_horizon_model(aligned_frame, feature_contract, partition_map, horizon_key)`.
- Guarantees: exactly 36 distinct periods, 30 fit periods, six validation
  periods, no contiguity assertion, and sparse-set report bounds.

- [ ] **Step 1: Reconcile Task 1 and mark Task 2 in progress**

Read both ledgers, verify the Task 1 commit and focused test evidence, and
require a clean tracked worktree. Record Task 2 as in progress.

- [ ] **Step 2: Re-run impact before editing training symbols**

Run GitNexus upstream impact separately for
`_validate_exact_training_window` and `train_horizon_model`, including tests.
Record direct callers, affected processes, and risk. Stop before editing on
HIGH or CRITICAL.

- [ ] **Step 3: Add a sparse 36-period training fixture**

Add below `_aligned_training_frame()`:

```python
def _sparse_aligned_training_frame() -> tuple[
    pd.DataFrame,
    list[pd.Period],
]:
    frame = _aligned_training_frame()
    dense_periods = sorted(frame["target_month"].unique())
    sparse_periods = [
        pd.Period("2014-04", freq="M") + 4 * index
        for index in range(36)
    ]
    period_mapping = dict(zip(dense_periods, sparse_periods, strict=True))
    frame["feature_month"] = frame["feature_month"].map(period_mapping)
    frame["target_month"] = frame["target_month"].map(period_mapping)
    return frame, sparse_periods
```

- [ ] **Step 4: Add failing sparse trainer and report tests**

Add near the existing `train_horizon_model` tests:

```python
def test_train_horizon_model_accepts_sparse_periods_and_reports_bounds():
    training = _training_module()
    frame, target_periods = _sparse_aligned_training_frame()

    result = training.train_horizon_model(
        frame,
        _feature_contract(),
        _partition_map(),
        "0m",
    )

    report = result.training_report
    assert report["training_target_month_range"] == {
        "start": str(target_periods[0]),
        "end": str(target_periods[-1]),
    }
    assert report["fit_target_month_range"] == {
        "start": str(target_periods[0]),
        "end": str(target_periods[29]),
    }
    assert report["validation_target_month_range"] == {
        "start": str(target_periods[30]),
        "end": str(target_periods[-1]),
    }
    assert report["sample_count"] == 180
    assert report["fit_sample_count"] == 150
    assert report["validation_sample_count"] == 30


def test_train_horizon_model_rejects_35_sparse_periods():
    training = _training_module()
    frame, target_periods = _sparse_aligned_training_frame()
    only_35 = frame.loc[frame["target_month"].ne(target_periods[0])]

    with pytest.raises(
        ValueError,
        match="exactly 36 distinct target_month periods",
    ):
        training.train_horizon_model(
            only_35,
            _feature_contract(),
            _partition_map(),
            "0m",
        )
```

- [ ] **Step 5: Run the trainer tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_training_inference.py::test_train_horizon_model_accepts_sparse_periods_and_reports_bounds \
  tests/fewsnet_partitioned_rf/test_training_inference.py::test_train_horizon_model_rejects_35_sparse_periods \
  -q -p no:cacheprovider
```

Expected RED: the 36-period sparse test raises the current contiguous-window
error, and the 35-period test's required distinct-period message does not match
the old inclusive-window message.

- [ ] **Step 6: Remove only the contiguity assertion**

Replace `_validate_exact_training_window` with:

```python
def _validate_exact_training_window(
    training: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fit, validation = split_threshold_window(
        training,
        validation_months=THRESHOLD_VALIDATION_MONTHS,
    )
    combined = pd.concat([fit, validation], ignore_index=True)
    target_periods = sorted(combined[TARGET_MONTH_COLUMN].unique())
    if len(target_periods) != TRAIN_WINDOW_MONTHS:
        raise ValueError(
            "training frame must contain exactly "
            f"{TRAIN_WINDOW_MONTHS} distinct target_month periods"
        )
    return fit, validation, combined
```

Change only the `train_horizon_model` docstring to:

```python
"""Select a threshold on 30 labeled periods and refit on all 36."""
```

Do not change split, threshold, imputer, SMOTE, RF, partition, report schema,
or predictor construction code.

- [ ] **Step 7: Verify GREEN**

Repeat Step 5. Expected: both tests pass.

- [ ] **Step 8: Document the operational meaning**

Add this paragraph in runbook section 14 after the approved source command:

```markdown
Training uses the latest 36 distinct target periods with non-null labels at or
before the audited `latest_label_month`. The periods may contain calendar
gaps. The first 30 observed periods fit the temporary threshold-selection
model, the last six validate the threshold, and the final model refits on all
36. Training and validation start/end fields are bounds over those observed
period sets; they do not assert that every intervening calendar month is
labeled.
```

- [ ] **Step 9: Run focused shared-core and local-runner regression**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf/test_horizons.py \
  tests/fewsnet_partitioned_rf/test_training_inference.py \
  tests/fewsnet_partitioned_rf/test_training_job.py \
  tests/fewsnet_partitioned_rf/test_model_package.py \
  tests/fewsnet_partitioned_rf/test_local_runner.py \
  -q -p no:cacheprovider
```

Expected: all selected tests pass with no package, training-worker, or local-
publication contract regression.

Run static parsing:

```bash
.venv/bin/python -m py_compile \
  fewsnet_partitioned_rf_pipeline/core/horizons.py \
  fewsnet_partitioned_rf_pipeline/core/training.py \
  tests/fewsnet_partitioned_rf/test_horizons.py \
  tests/fewsnet_partitioned_rf/test_training_inference.py
```

Expected: exit zero.

- [ ] **Step 10: Record evidence, obtain independent review, and commit**

Update both ledgers with RED/GREEN results, report-bound assertions, focused
regression, static checks, and Task 3 as next. Stage only the two core files,
two test files, runbook, and `PROGRESS.md`. Run staged GitNexus detection and
staged Git checks, then commit:

```bash
git commit -m "fix: support sparse FEWSNET label periods"
```

Do not begin Task 3 until an independent reviewer confirms that the change
removes only calendar contiguity, preserves exact 36-period and 30/6 behavior,
and introduces no model-mathematics or artifact-contract drift. Route review
findings through focused RED/GREEN tests and a separately checked fix commit.

---

### Task 3: Run Full Regression and Complete the Real 2026-04 Acceptance

**Files:**

- Modify: `PROGRESS.md`
- Modify ignored progress and Task 5 report under the active SDD feature
  directory.
- Generate ignored artifacts under `Outcome/fewsnet_partitioned_rf/`.

**Interfaces:**

- Consumes: the reviewed shared-core fix and existing
  `fewsnet_partitioned_rf_pipeline.cli.run_local_experiment` CLI.
- Produces: three reloadable local packages, two suite reports, three
  5,718-row prediction CSVs, a checksum-valid passed `run_summary.json`, and
  durable acceptance evidence.
- Preserves: absent cloud mutations and byte-identical
  `Outcome/ipcch_unified/`.

- [ ] **Step 1: Verify the reviewed implementation baseline**

Require a clean tracked worktree, record the exact HEAD, confirm independent
review approval, and confirm both implementation commits are present. Mark
Task 3 in progress in both ledgers.

- [ ] **Step 2: Verify dependencies and the SMOTE bridge**

```bash
UV_CACHE_DIR=/tmp/ipcch-fewsnet-uv-cache \
  uv pip check --python .venv/bin/python
.venv/bin/python -c \
  'import fewsnet_partitioned_rf_pipeline.core.training as training; smote = training._load_smote_type(); print(smote.__module__, smote.__name__)'
```

Expected: no broken requirements, and the second command prints the real
`imblearn` `SMOTE` type through the reviewed bridge.

- [ ] **Step 3: Run the complete FEWSNET regression**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/fewsnet_partitioned_rf \
  -q -p no:cacheprovider
```

Expected: the complete suite passes. Record exact pass/skip count and elapsed
time. Do not continue after any failure.

- [ ] **Step 4: Re-verify source identities and clean output state**

```bash
sha256sum \
  "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv" \
  "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json"
test ! -e Outcome/fewsnet_partitioned_rf
git status --porcelain --untracked-files=no
```

Expected: both digests match the Global Constraints, the output-root test
exits zero, and tracked status is empty. Do not use `--overwrite`.

- [ ] **Step 5: Capture the IPCCH before-manifest**

```bash
find Outcome/ipcch_unified -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > /tmp/ipcch-unified-before-fewsnet-local.sha256
wc -l /tmp/ipcch-unified-before-fewsnet-local.sha256
sha256sum /tmp/ipcch-unified-before-fewsnet-local.sha256
```

Expected: the manifest covers the complete IPCCH tree. Record its line count
and digest before running FEWSNET.

- [ ] **Step 6: Run the complete unsampled experiment**

Run exactly, without `--overwrite`:

```bash
set -o pipefail
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m \
  fewsnet_partitioned_rf_pipeline.cli.run_local_experiment \
  --panel "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.csv" \
  --normalization-audit "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/1.Source Data/assembled_FEWSNET/FEWSNET_forecast_unadjusted_bm_2025_combined.normalized-v1.audit.json" \
  --feature-month 2026-04 \
  --output-root Outcome/fewsnet_partitioned_rf \
  > >(tee /tmp/fewsnet-local-202604-cli-result.json) \
  2> >(tee /tmp/fewsnet-local-202604-cli-stderr.json >&2)
```

Expected: exit zero and exactly one success JSON object on stdout. Keep the
process in a persistent terminal session, report progress at least every 60
seconds, and do not infer success from CPU activity alone.

- [ ] **Step 7: Run an independent artifact verifier**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path

import pandas as pd

from fewsnet_partitioned_rf_pipeline.local.outputs import (
    validate_local_prediction_suite,
)
from fewsnet_partitioned_rf_pipeline.local.package import (
    load_local_model_package,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


root = Path("Outcome/fewsnet_partitioned_rf")
summary_path = root / "predictions/202604/run_summary.json"
summary = json.loads(summary_path.read_text(encoding="utf-8"))
assert summary["status"] == "passed"
assert summary["runtime_backend"] == "local_python"
assert summary["gcp_write_performed"] is False
assert summary["latest_feature_month"] == "2026-04"
assert summary["latest_label_month"] == "2026-02"
assert summary["training_target_month_range"] == {
    "start": "2014-04",
    "end": "2026-02",
}
assert summary["validation_target_month_range"] == {
    "start": "2023-10",
    "end": "2026-02",
}
assert summary["population"]["raw_last_observed_count"] == 5716
assert summary["population"]["missing_raw_count"] == 2
assert len(summary["population"]["missing_admin_codes"]) == 2

suite_version = summary["suite_version"]
source_commit = summary["source_git_commit"]
panel_sha256 = summary["panel"]["sha256"]
frames = {}
for key in ("0m", "6m", "12m"):
    horizon = summary["horizons"][key]
    prediction_ref = horizon["prediction"]
    prediction_path = root / prediction_ref["relative_path"]
    assert prediction_path.stat().st_size == prediction_ref["size_bytes"]
    assert sha256(prediction_path) == prediction_ref["sha256"]
    frames[key] = pd.read_csv(
        prediction_path,
        dtype={"admin_code": "string"},
    )
    assert len(frames[key]) == 5718
    assert horizon["row_count"] == 5718

    package_path = root / summary["model_packages"][key]["relative_path"]
    loaded = load_local_model_package(
        package_path,
        expected_suite_version=suite_version,
        expected_source_git_commit=source_commit,
        expected_panel_sha256=panel_sha256,
    )
    report = loaded.training_report
    assert report["training_target_month_range"] == {
        "start": "2014-04",
        "end": "2026-02",
    }
    assert report["fit_target_month_range"] == {
        "start": "2014-04",
        "end": "2023-06",
    }
    assert report["validation_target_month_range"] == {
        "start": "2023-10",
        "end": "2026-02",
    }
    assert report["sample_count"] == 188643
    assert report["fit_sample_count"] == 155067
    assert report["validation_sample_count"] == 33576

expected_admin_codes = tuple(frames["0m"]["admin_code"].tolist())
assert len(expected_admin_codes) == 5718
assert len(set(expected_admin_codes)) == 5718
suite = validate_local_prediction_suite(
    frames,
    expected_admin_codes=expected_admin_codes,
    feature_month="2026-04",
    suite_version=suite_version,
)
assert set(suite["target_months"].items()) == {
    ("0m", "2026-04"),
    ("6m", "2026-10"),
    ("12m", "2027-04"),
}

for report_ref in summary["reports"].values():
    report_path = root / report_ref["relative_path"]
    assert report_path.stat().st_size == report_ref["size_bytes"]
    assert sha256(report_path) == report_ref["sha256"]

print(
    json.dumps(
        {
            "run_id": summary["run_id"],
            "suite_version": suite_version,
            "prediction_rows_per_horizon": 5718,
            "training_rows_per_horizon": 188643,
            "fit_rows_per_horizon": 155067,
            "validation_rows_per_horizon": 33576,
            "status": "passed",
        },
        sort_keys=True,
    )
)
PY
```

Expected: exit zero and one JSON evidence object with `status: passed`.

- [ ] **Step 8: Prove IPCCH identity and tracked cleanliness**

```bash
find Outcome/ipcch_unified -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > /tmp/ipcch-unified-after-fewsnet-local.sha256
cmp \
  /tmp/ipcch-unified-before-fewsnet-local.sha256 \
  /tmp/ipcch-unified-after-fewsnet-local.sha256
git status --short
```

Expected: `cmp` exits zero. The generated FEWSNET root is ignored and tracked
status is empty before evidence-document updates.

- [ ] **Step 9: Record accepted Task 5 evidence**

Change the ignored Task 5 report status from `BLOCKED` to `PASSED`. Record the
implementation commit, source identities, full regression output, run timing,
run ID, suite version, sparse bounds and row counts, artifact paths and
checksums, 5,718 rows per horizon, target months, `5716 + 2` population split,
IPCCH manifest identity, and absence of cloud/network/overwrite mutation.

Update both progress ledgers to mark Task 5 and the active feature complete.
Tracked `PROGRESS.md` must contain enough exact evidence to audit the result
without the ignored report.

- [ ] **Step 10: Commit tracked evidence and review the branch**

Stage only `PROGRESS.md`. Run staged GitNexus detection, staged stat, and
staged whitespace checks, then commit:

```bash
git commit -m "docs: record FEWSNET local 202604 acceptance"
```

After the commit, run:

```bash
git status --short --branch
git log --oneline --decorate -8
git diff --check main...HEAD
```

Run GitNexus `detect_changes(scope="compare", base_ref="main")` for final
branch review. Confirm the only behavioral change is sparse-label window
selection and generated FEWSNET outputs remain outside Git.
