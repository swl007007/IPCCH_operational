# G-09 Monthly IPCCH Base Input Assembly Design

## Context

The handover now defines IPCCH as one unified production contract. Legacy
`Final_harmonise` scripts still assemble separate CH and IPC files, use
hard-coded source paths, and mix source joins with model-oriented cleanup. The
repository's operational product should instead be one monthly
model-compatible IPCCH input table. Prediction remains downstream and will use
model weights and a model pipeline exported separately by Weilun.

G-06 model weights/pipeline and G-07 downstream feature engineering are
deferred. Therefore G-09 must not make the existing deep-feature or
scope-specific `model_ready` files canonical.

## Decision

Implement a conservative unified monthly assembly path.

G-09 will build a base monthly IPCCH input surface from the one-month scaffold,
the current unified panel, and fixed/slow area features. It will not recreate
lag, rolling, scope-specific, or model-pipeline transformations from
`assembled_IPCCH/model_ready`.

## Goals

- Produce one long CSV for a target month keyed by `area_id`, `year`, and
  `month`.
- Keep `admin_code`, `lat`, and `lon` as audit and compatibility fields.
- Treat `area_id = admin_code` for current handover assets.
- Join fixed/slow area features for all scaffold rows.
- Join same-month source-level fields when they exist in the unified historical
  panel.
- Report row counts, duplicate keys, join coverage, and feature missingness.
- Make legacy split CH/IPC final harmonise scripts clearly non-production.

## Non-Goals

- Do not train or run the prediction model.
- Do not require model weights or the exported model pipeline.
- Do not implement G-07 lag, rolling, forecasting-scope, spatial-neighbor, or
  leakage-safe engineered features.
- Do not copy `assembled_IPCCH/model_ready/*` as the production contract.
- Do not preserve split IPC and CH production outputs unless a downstream
  consumer later requires a compatibility export.

## Inputs

| Input | Role |
| --- | --- |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_YYYYMM.csv` | One-month row universe for the target production month. |
| `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | Current unified source panel through 2026-04; used for same-month source-level fields where available. |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` | One-row-per-area fixed and slow-moving feature asset. |
| `config/paths_template.ini` or a user-supplied copy | Path configuration surface. |

For future months not present in the raw panel, the assembly should still write
the scaffold plus fixed/slow features and report missing dynamic source fields
in the QA summary.

## Outputs

| Output | Shape | Role |
| --- | --- | --- |
| `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_YYYYMM.csv` | One row per `area_id`, `year`, `month` | Base monthly model-compatible IPCCH input surface. |
| `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_YYYYMM_summary.json` | QA metadata | Row counts, key checks, join coverage, date coverage, and missingness summary. |

The CSV should put identifier columns first:

```text
area_id, admin_code, lat, lon, year, month
```

Outcome columns may be present when observed in the source panel, but forecast
months may leave them blank or absent from the same-month source join. The
prediction step must not depend on outcomes being available.

## Assembly Flow

1. Load the one-month scaffold and validate required columns:
   `admin_code`, `lat`, `lon`, `year`, `month`.
2. Add `area_id` from `admin_code`, preserving `admin_code`.
3. Validate scaffold grain:
   - exactly one target `year`/`month`;
   - unique `(area_id, year, month)`;
   - no blank `area_id`.
4. Load fixed/slow features and join on `area_id`.
5. Load the unified raw panel only for the requested year/month and derive
   `area_id = admin_code`.
6. Drop duplicate source rows on `(area_id, year, month)` only after reporting
   the duplicate count.
7. Join source-level fields on `(area_id, year, month)`.
8. Reorder identifier columns first, then fixed/slow columns, then same-month
   source-level columns.
9. Write the monthly CSV and QA summary.

## Source-Column Policy

The raw panel contains identifiers, outcomes, static fields, dynamic
source-level fields, and diagnostics. G-09 should use an explicit exclusion
policy rather than blindly preserving every column:

- Always exclude duplicate key aliases from the source slice after joining:
  source `admin_code`, `lat`, `lon`, `year`, and `month`.
- Keep source-level feature and outcome columns available in the raw panel.
- Exclude obvious non-feature diagnostics only when they are known from the
  existing schema or codebook.
- Do not generate new engineered features whose names imply a forecast scope,
  lag, rolling window, trend, stress spell, historical-relative value, or
  model-specific interaction.

The first implementation can be conservative: join raw same-month columns that
already pass the existing IPCCH schema contract, and surface any questionable
columns in the QA summary rather than silently dropping them.

## Error Handling

Hard failures:

- Missing scaffold file.
- Scaffold missing required key columns.
- Scaffold contains multiple months.
- Duplicate `(area_id, year, month)` in the final output.
- Fixed/slow asset has duplicate `area_id`.
- Output directory cannot be written.

Soft warnings recorded in the summary:

- Target month is absent from the raw panel.
- Some scaffold areas do not match the raw panel for the target month.
- Same-month source fields have high missingness.
- Source slice contains duplicates that had to be de-duplicated before join.
- Fixed/slow join has unmatched areas.

## Validation

For the current 2026-04 handover month:

- output row count equals the scaffold row count, currently 6,227;
- `(area_id, year, month)` is unique;
- `area_id = admin_code` for every row;
- fixed/slow area join has full or explicitly reported coverage;
- same-month source join coverage is reported;
- summary JSON includes input paths, output path, row counts, duplicate counts,
  and feature missingness.

For future target months:

- the script can still build the scaffold plus fixed/slow features;
- missing dynamic source features are visible in the summary;
- no blank or duplicate keys are introduced.

## Documentation Updates

Update the runbook and gap list after implementation:

- `docs/03_workflow_runbook.md` should list the new unified monthly assembly
  command after source-workflow extraction steps.
- `docs/04_output_inventory.md` should list the monthly base input CSV and QA
  summary.
- `docs/05_weilun_handover_gap_list.md` should mark G-09 resolved for base
  monthly assembly and keep G-06/G-07 deferred.
- Legacy split CH/IPC final harmonise scripts should be archived or explicitly
  labeled as non-production compatibility artifacts.

## Acceptance Criteria

- A new operator can run one command for a target month and get a unified
  monthly IPCCH base input table.
- The command does not require model weights, the model pipeline, or G-07
  engineered-feature assets.
- The output uses one IPCCH contract, not separate IPC and CH outputs.
- The 2026-04 sample run validates against the row-grain and key checks above.
- Documentation points operators to the unified G-09 flow and away from legacy
  split final harmonise scripts.
