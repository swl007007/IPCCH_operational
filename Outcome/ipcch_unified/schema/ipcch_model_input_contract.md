# Unified IPCCH Model Input Contract

G-05 defines the base handover schema for the unified IPCCH production
input/output contract. Treat IPCCH as one long monthly panel, not as separate
IPC and CH production contracts.

The repository's final operational output is a monthly model-compatible input
table. Prediction is a downstream step: Weilun will export the trained model
weights and model pipeline separately, and the operator will combine those
model artifacts with the monthly compatible input to produce predictions.

## Canonical Row Grain

The standardized model input is one row per `area_id`, `year`, and `month`.
In the current handover assets, `area_id` is the same identifier as
`admin_code`. Keep both columns when possible:

| Field | Role |
| --- | --- |
| `area_id` | Canonical model identifier. Derive from `admin_code` for the current raw panel and forecast scaffold. |
| `admin_code` | Compatibility alias and source administrative code. |
| `lat`, `lon` | Audit and join coordinates. |
| `year`, `month` | Long monthly time index. Remote-sensing wide monthly outputs must be melted before they enter this contract. |

For current handover validation, the raw historical panel and forecast scaffold
are checked on `(admin_code, lat, lon, year, month)`. Once a model-ready export
is rebuilt, it should be checked on `(area_id, year, month)`.

## Monthly Production Scaffold

Production only needs the target month scaffold, not a multi-month scaffold.
The one-month scaffold is the input surface on which monthly feature workflows
append source values before the model-compatible table is produced.

Use:

```bash
python3 tools/build_monthly_ipcch_scaffold.py --year 2026 --month 4
```

When `--year` and `--month` are omitted, the tool writes the latest month found
in the reference scaffold. The current example is
`Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv`.

## Current Assets

| Asset | Shape | Required key | Role |
| --- | --- | --- | --- |
| `Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv` | Long historical panel | `admin_code`, `lat`, `lon`, `year`, `month` | Authoritative observed panel through 2026-04, including outcomes and source features. |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv` | One-month production scaffold example | `admin_code`, `lat`, `lon`, `year`, `month` | Default production scaffold example for a single target month. Outcomes are not required here. |
| `Outcome/ipcch_unified/interim/ipcch_scaffold_202501_202604.csv` | Multi-month reference scaffold | `admin_code`, `lat`, `lon`, `year`, `month` | Batch/reference scaffold retained for rebuilding one-month scaffolds and QA. It is not required as the monthly production input. |
| `Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv` | One row per area | `area_id` | Fixed/slow feature join asset generated from the historical panel. |

## Outcome Columns

Training or evaluation rows require the outcome columns to be present when
observed:

| Column | Requirement |
| --- | --- |
| `overall_phase` | Main IPC/CH phase target. |
| `phase1_percent` through `phase5_percent` | Phase-distribution outcomes/features used where available. |
| `estimated_population` | Population context attached to the outcome rows. |

Forecast scaffold rows may keep these columns absent or blank until observed
IPCCH outcomes are joined later.

For prediction runs, outcome columns are not part of the monthly input
requirement. They become observed outcomes later, after IPCCH releases are
available.

## Feature Families

The copied codebook is
`Outcome/ipcch_unified/metadata/variable_codebook_reorganized.csv`. The
machine-readable family summary is
`Outcome/ipcch_unified/schema/ipcch_feature_family_contract.csv`.

The G-05 base contract does not require downstream engineered lag, rolling, or
model-specific feature columns. Those belong to G-07. Model weights belong to
G-06. The eventual production model-compatible table must match the exported
model pipeline's expected columns. Current model-ready files under the source
`assembled_IPCCH/model_ready` folder can be used as references, but they are not
the canonical handover schema until G-06/G-07 are prepared.

## Legacy Split Files

Legacy files or scripts with `IPC` or `CH` in the name are transitional
compatibility artifacts. The production handover target is a unified IPCCH
input/output. Only generate split IPC/CH exports if a downstream consumer still
requires them explicitly.

## Validation

Run these checks after receiving or rebuilding the handover assets:

```bash
python3 tools/validate_ipcch_schema.py --mode historical-panel --csv Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv
python3 tools/validate_ipcch_schema.py --mode forecast-scaffold --csv Outcome/ipcch_unified/interim/ipcch_scaffold_202604.csv
python3 tools/validate_ipcch_schema.py --mode fixed-slow-area --csv Outcome/ipcch_unified/features/ipcch_fixed_slow_features_by_area.csv
```

The validator streams CSV rows and is intended for the large raw panel.
