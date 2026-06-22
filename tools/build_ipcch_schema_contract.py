import csv
import hashlib
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_ROOT = PROJECT_ROOT / "Outcome" / "ipcch_unified"
RAW_PANEL = UNIFIED_ROOT / "raw" / "IPCCH_2026_completed.csv"
SCAFFOLD = UNIFIED_ROOT / "interim" / "ipcch_scaffold_202501_202604.csv"
FIXED_SLOW = UNIFIED_ROOT / "features" / "ipcch_fixed_slow_features_by_area.csv"
FIXED_SLOW_SUMMARY = (
    UNIFIED_ROOT / "features" / "ipcch_fixed_slow_features_summary.csv"
)
CODEBOOK = UNIFIED_ROOT / "metadata" / "variable_codebook_reorganized.csv"
SCHEMA_DIR = UNIFIED_ROOT / "schema"

OUTCOME_COLUMNS = [
    "overall_phase",
    "phase1_percent",
    "phase2_percent",
    "phase3_percent",
    "phase4_percent",
    "phase5_percent",
    "estimated_population",
]

CURRENT_KEY_COLUMNS = ["admin_code", "lat", "lon", "year", "month"]
CANONICAL_MODEL_KEY_COLUMNS = ["area_id", "year", "month"]
IDENTIFIER_COLUMNS = {
    "area_id",
    "admin_code",
    "lat",
    "lon",
    "year",
    "month",
    "ISO3",
    "country",
    "country_code",
    "country_en",
    "state",
    "address",
}
FIXED_SLOW_METADATA_COLUMNS = {
    "area_id",
    "admin_code",
    "lat",
    "lon",
    "ISO3",
    "country",
    "country_code",
    "country_en",
    "state",
    "source_row_count",
    "first_year_month",
    "last_year_month",
}
INTEGER_COLUMNS = {"year", "month", "overall_phase", "source_row_count"}
STRING_COLUMNS = {
    "area_id",
    "admin_code",
    "ISO3",
    "country",
    "country_code",
    "country_en",
    "state",
    "address",
    "first_year_month",
    "last_year_month",
}

GROUP_ROLE_OVERRIDES = {
    "01 Identifiers, location, and time": "key_or_identifier",
    "02 Geography and spatial linkage": "identifier_or_static_geography",
    "03 Terrain and physical geography": "fixed_slow_feature",
    "04 Agriculture, AEZ, and masks": "fixed_slow_feature",
    "05 FLDAS/GLDAS land-surface climate": "monthly_dynamic_feature",
    "06 Remote sensing vegetation and nightlights": "monthly_dynamic_feature",
    "07 SoilGrids soil attributes": "fixed_slow_feature",
    "08 Conflict events and fatalities": "monthly_dynamic_feature",
    "09 Food security / IPC": "outcome",
    "10 Demographic, socioeconomic, and macro": "slow_or_country_time_feature",
    "11 Food prices and inflation": "monthly_dynamic_feature",
    "12 Bloomberg commodities and fertilizer/energy": "deferred_source_feature",
    "13 Market access": "fixed_slow_feature",
    "99 Other / review": "deferred_source_feature",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_header(path):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


def read_codebook():
    rows = {}
    with CODEBOOK.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows[row["variable"]] = row
    return rows


def read_fixed_slow_features():
    header = read_header(FIXED_SLOW)
    return [column for column in header if column not in FIXED_SLOW_METADATA_COLUMNS]


def read_fixed_slow_families():
    families = {}
    with FIXED_SLOW_SUMMARY.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            families[row["feature"]] = row["family"]
    return families


def slugify_group(group):
    prefix = group.split(" ", 1)[0]
    text = group.split(" ", 1)[-1].lower()
    safe = []
    for char in text:
        if char.isalnum():
            safe.append(char)
        else:
            safe.append("_")
    while "__" in "".join(safe):
        safe = list("".join(safe).replace("__", "_"))
    return (prefix + "_" + "".join(safe).strip("_")).strip("_")


def infer_dtype(column):
    if column in INTEGER_COLUMNS:
        return "integer"
    if column in STRING_COLUMNS:
        return "string"
    return "numeric"


def format_rule(column):
    if column == "area_id":
        return "Canonical IPCCH area identifier; equals admin_code in current assets."
    if column == "admin_code":
        return "Current administrative identifier; source for area_id."
    if column == "lat":
        return "Decimal degrees; expected range [-90, 90]."
    if column == "lon":
        return "Decimal degrees; expected range [-180, 180]."
    if column == "year":
        return "Four-digit integer year."
    if column == "month":
        return "Integer month 1-12."
    if column == "overall_phase":
        return "IPC/CH phase; expected numeric phase where observed."
    if column.startswith("phase") and column.endswith("_percent"):
        return "Population percent by phase where observed."
    return ""


def role_for_column(column, group, fixed_slow_features):
    if column in CANONICAL_MODEL_KEY_COLUMNS:
        return "canonical_key"
    if column in CURRENT_KEY_COLUMNS or column in IDENTIFIER_COLUMNS:
        return "identifier"
    if column in OUTCOME_COLUMNS:
        return "outcome"
    if column in fixed_slow_features:
        return "fixed_slow_feature"
    if group:
        return GROUP_ROLE_OVERRIDES.get(group, "source_feature")
    return "source_feature"


def historical_requirement(column):
    if column == "area_id":
        return "derived from admin_code"
    if column in CURRENT_KEY_COLUMNS or column in OUTCOME_COLUMNS:
        return "required"
    if column in IDENTIFIER_COLUMNS:
        return "recommended"
    return "source-dependent"


def scaffold_requirement(column):
    if column == "area_id":
        return "derived from admin_code"
    if column in CURRENT_KEY_COLUMNS:
        return "required"
    if column in OUTCOME_COLUMNS:
        return "not required for forecast scaffold"
    return "not expected"


def model_input_requirement(column):
    if column in CANONICAL_MODEL_KEY_COLUMNS:
        return "required"
    if column == "admin_code":
        return "required compatibility alias"
    if column in {"lat", "lon", "ISO3", "country", "country_code", "country_en", "state"}:
        return "recommended for audit and joins"
    if column in OUTCOME_COLUMNS:
        return "required for training rows; optional/blank for forecast rows"
    return "optional feature column before downstream feature engineering"


def fixed_slow_requirement(column, fixed_slow_features):
    if column in {"area_id", "admin_code", "lat", "lon"}:
        return "required"
    if column in {"ISO3", "country", "country_code", "country_en", "state"}:
        return "recommended"
    if column in fixed_slow_features:
        return "required when using fixed/slow feature join"
    return "not expected"


def write_base_schema(raw_header, codebook, fixed_slow_features, fixed_slow_families):
    schema_columns = [
        "field_name",
        "role",
        "family",
        "codebook_group",
        "present_in_current_historical_panel",
        "historical_panel_requirement",
        "forecast_scaffold_requirement",
        "standardized_model_input_requirement",
        "fixed_slow_area_asset_requirement",
        "data_type",
        "format_or_allowed_values",
        "description",
        "statistic_or_measure",
        "notes",
    ]

    field_names = []
    for name in ["area_id"] + raw_header + sorted(codebook):
        if name not in field_names:
            field_names.append(name)

    rows = []
    for column in field_names:
        book = codebook.get(column, {})
        group = book.get("group", "")
        family = fixed_slow_families.get(column, slugify_group(group) if group else "")
        role = role_for_column(column, group, fixed_slow_features)
        notes = []
        if column == "area_id":
            notes.append("Canonical identifier for the unified IPCCH contract.")
        if column == "admin_code":
            notes.append("Current raw/scaffold assets use this as the area id.")
        if column in OUTCOME_COLUMNS:
            notes.append("Observed outcomes are sparse by design in the raw panel.")
        if column not in raw_header and column != "area_id":
            notes.append("In codebook but not in current raw handover panel.")
        rows.append(
            {
                "field_name": column,
                "role": role,
                "family": family,
                "codebook_group": group,
                "present_in_current_historical_panel": "yes"
                if column in raw_header
                else "derived" if column == "area_id" else "no",
                "historical_panel_requirement": historical_requirement(column),
                "forecast_scaffold_requirement": scaffold_requirement(column),
                "standardized_model_input_requirement": model_input_requirement(column),
                "fixed_slow_area_asset_requirement": fixed_slow_requirement(
                    column, fixed_slow_features
                ),
                "data_type": infer_dtype(column),
                "format_or_allowed_values": format_rule(column),
                "description": book.get("description", ""),
                "statistic_or_measure": book.get("statistic_or_measure", ""),
                "notes": " ".join(notes),
            }
        )

    out = SCHEMA_DIR / "ipcch_base_panel_schema.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=schema_columns)
        writer.writeheader()
        writer.writerows(rows)
    return out


def write_family_contract(raw_header, codebook, fixed_slow_features):
    raw_set = set(raw_header)
    codebook_groups = Counter(row["group"] for row in codebook.values())
    raw_groups = Counter(
        codebook[column]["group"]
        for column in raw_header
        if column in codebook and codebook[column].get("group")
    )
    fixed_groups = Counter(
        codebook[column]["group"]
        for column in fixed_slow_features
        if column in codebook and codebook[column].get("group")
    )

    rows = []
    for group in sorted(codebook_groups):
        role = GROUP_ROLE_OVERRIDES.get(group, "source_feature")
        if role == "outcome":
            requirement = "Outcome columns required for observed training rows; optional for forecast scaffold."
        elif role == "key_or_identifier":
            requirement = "Required or recommended identifier fields."
        elif role == "fixed_slow_feature":
            requirement = "Join from G-03 fixed/slow area asset where used."
        elif role == "deferred_source_feature":
            requirement = "Deferred until downstream feature engineering or source enrichment is handed over."
        else:
            requirement = "Optional source feature family in the base long panel."
        rows.append(
            {
                "codebook_group": group,
                "family_slug": slugify_group(group),
                "contract_role": role,
                "codebook_variable_count": codebook_groups[group],
                "current_historical_panel_column_count": raw_groups[group],
                "fixed_slow_area_asset_column_count": fixed_groups[group],
                "requirement_summary": requirement,
                "notes": "",
            }
        )

    missing_raw_codebook = sorted(raw_set - set(codebook))
    if missing_raw_codebook:
        rows.append(
            {
                "codebook_group": "not_in_codebook",
                "family_slug": "not_in_codebook",
                "contract_role": "review",
                "codebook_variable_count": 0,
                "current_historical_panel_column_count": len(missing_raw_codebook),
                "fixed_slow_area_asset_column_count": 0,
                "requirement_summary": "Present in raw panel but absent from copied codebook.",
                "notes": ";".join(missing_raw_codebook),
            }
        )

    out = SCHEMA_DIR / "ipcch_feature_family_contract.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "codebook_group",
            "family_slug",
            "contract_role",
            "codebook_variable_count",
            "current_historical_panel_column_count",
            "fixed_slow_area_asset_column_count",
            "requirement_summary",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out


def write_markdown_contract(raw_header, scaffold_header, fixed_header):
    out = SCHEMA_DIR / "ipcch_model_input_contract.md"
    text = """# Unified IPCCH Model Input Contract

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
"""
    with out.open("w", encoding="utf-8") as handle:
        handle.write(text)
    return out


def write_manifest(outputs):
    rows = []
    for path in outputs:
        rows.append((path.relative_to(UNIFIED_ROOT), sha256_file(path)))

    out = SCHEMA_DIR / "MANIFEST.md"
    with out.open("w", encoding="utf-8") as handle:
        handle.write("# G-05 Unified IPCCH Schema\n\n")
        handle.write(
            "This folder defines the standardized base IPCCH model input "
            "contract for handover.\n\n"
        )
        handle.write("## Files\n\n")
        handle.write("| File | SHA-256 |\n| --- | --- |\n")
        for relative_path, digest in rows:
            handle.write("| `{0}` | `{1}` |\n".format(relative_path, digest))
        handle.write("\n## Generator\n\n")
        handle.write("```bash\npython3 tools/build_ipcch_schema_contract.py\n```\n")
    return out


def main():
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    raw_header = read_header(RAW_PANEL)
    scaffold_header = read_header(SCAFFOLD)
    fixed_header = read_header(FIXED_SLOW)
    codebook = read_codebook()
    fixed_slow_features = read_fixed_slow_features()
    fixed_slow_families = read_fixed_slow_families()

    outputs = [
        write_base_schema(raw_header, codebook, fixed_slow_features, fixed_slow_families),
        write_family_contract(raw_header, codebook, fixed_slow_features),
        write_markdown_contract(raw_header, scaffold_header, fixed_header),
    ]
    manifest = write_manifest(outputs)
    print("Wrote:")
    for path in outputs + [manifest]:
        print("  {0}".format(path.relative_to(PROJECT_ROOT)))


if __name__ == "__main__":
    main()
