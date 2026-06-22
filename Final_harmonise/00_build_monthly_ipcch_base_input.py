from __future__ import print_function

import argparse
import csv
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import workflow_config


UNIFIED_ROOT = PROJECT_ROOT / "Outcome" / "ipcch_unified"
DEFAULT_HISTORICAL_PANEL = UNIFIED_ROOT / "raw" / "IPCCH_2026_completed.csv"
DEFAULT_FIXED_SLOW = (
    UNIFIED_ROOT / "features" / "ipcch_fixed_slow_features_by_area.csv"
)
DEFAULT_OUTPUT_DIR = UNIFIED_ROOT / "model_input"
ID_COLUMNS = ["area_id", "admin_code", "lat", "lon", "year", "month"]
SOURCE_KEY_COLUMNS = {"area_id", "admin_code", "lat", "lon", "year", "month"}
ENGINEERED_MARKERS = [
    "__l",
    "__roll",
    "__slope",
    "__accel",
    "__hist_",
    "__forecast_sequence",
    "__delayed_control",
    "__x__",
    "_asof",
    "_lag",
    "lag1",
]


def fail(message):
    raise SystemExit("FAIL: {0}".format(message))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build one unified monthly IPCCH base model input table."
    )
    parser.add_argument("--year", type=int, help="Target four-digit year.")
    parser.add_argument("--month", type=int, help="Target month 1-12.")
    parser.add_argument(
        "--config",
        default="",
        help=(
            "Optional paths.ini. If omitted, IPCCH_CONFIG or config/paths.ini "
            "is used when present."
        ),
    )
    parser.add_argument("--scaffold", default="", help="One-month scaffold CSV.")
    parser.add_argument(
        "--historical-panel",
        default="",
        help="Unified historical/source panel CSV.",
    )
    parser.add_argument(
        "--fixed-slow-features",
        default="",
        help="Fixed/slow area feature CSV.",
    )
    parser.add_argument("--output", default="", help="Output monthly base input CSV.")
    parser.add_argument("--summary-output", default="", help="Output QA summary JSON.")
    return parser.parse_args()


def format_yyyymm(year, month):
    return "{0}{1}".format(year, str(month).zfill(2))


def default_scaffold_path(year, month):
    return UNIFIED_ROOT / "interim" / "ipcch_scaffold_{0}.csv".format(
        format_yyyymm(year, month)
    )


def default_output_path(year, month):
    return DEFAULT_OUTPUT_DIR / "ipcch_monthly_base_input_{0}.csv".format(
        format_yyyymm(year, month)
    )


def default_summary_path(year, month):
    return DEFAULT_OUTPUT_DIR / "ipcch_monthly_base_input_{0}_summary.json".format(
        format_yyyymm(year, month)
    )


def is_blank(value):
    return value is None or str(value).strip() == ""


def parse_int(value, label):
    if is_blank(value):
        fail("Missing integer value for {0}".format(label))
    try:
        return int(float(str(value).strip()))
    except ValueError:
        fail("Invalid integer value for {0}: {1}".format(label, value))


def normalize_area_id(value):
    if is_blank(value):
        return ""
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def validate_target_month(year, month):
    if year < 1900 or year > 2100:
        fail("Invalid target year: {0}".format(year))
    if month < 1 or month > 12:
        fail("Invalid target month: {0}".format(month))


def load_optional_config(config_arg):
    config_path = config_arg or os.environ.get("IPCCH_CONFIG", "")
    if config_path:
        return workflow_config.load_config(config_path)
    default_path = PROJECT_ROOT / "config" / "paths.ini"
    if default_path.exists():
        return workflow_config.load_config(str(default_path))
    return None


def config_value(config, section, option, default):
    if (
        config is not None
        and config.has_section(section)
        and config.has_option(section, option)
    ):
        return workflow_config.get_value(config, section, option)
    return default


def config_path(config, section, option, default):
    if (
        config is not None
        and config.has_section(section)
        and config.has_option(section, option)
    ):
        return Path(workflow_config.resolve_path(config, section, option))
    return Path(default)


def resolve_runtime_paths(args):
    config = load_optional_config(args.config)
    year = args.year
    month = args.month
    if year is None:
        year = parse_int(
            config_value(config, "production", "target_year", "2026"),
            "target_year",
        )
    if month is None:
        month = parse_int(
            config_value(config, "production", "target_month", "4"),
            "target_month",
        )
    validate_target_month(year, month)

    if args.scaffold:
        scaffold_path = Path(args.scaffold)
    elif (
        config is not None
        and config.has_section("paths")
        and config.has_option("paths", "scaffold_input")
    ):
        scaffold_path = Path(workflow_config.resolve_path(config, "paths", "scaffold_input"))
    else:
        scaffold_path = default_scaffold_path(year, month)

    historical_panel = (
        Path(args.historical_panel)
        if args.historical_panel
        else config_path(config, "paths", "historical_panel_input", DEFAULT_HISTORICAL_PANEL)
    )
    fixed_slow = (
        Path(args.fixed_slow_features)
        if args.fixed_slow_features
        else config_path(config, "paths", "fixed_slow_features_input", DEFAULT_FIXED_SLOW)
    )
    output = Path(args.output) if args.output else default_output_path(year, month)
    summary = (
        Path(args.summary_output)
        if args.summary_output
        else default_summary_path(year, month)
    )
    return year, month, scaffold_path, fixed_slow, historical_panel, output, summary


def require_file(path, label):
    if not Path(path).is_file():
        fail("Missing {0}: {1}".format(label, path))


def open_reader(path):
    handle = Path(path).open("r", newline="", encoding="utf-8-sig")
    reader = csv.DictReader(handle)
    if not reader.fieldnames:
        handle.close()
        fail("CSV has no header: {0}".format(path))
    return handle, reader


def require_columns(header, required, label):
    missing = [column for column in required if column not in header]
    if missing:
        fail("{0} missing columns: {1}".format(label, ", ".join(missing)))


def is_engineered_column(column):
    lowered = column.lower()
    return any(marker in lowered for marker in ENGINEERED_MARKERS)


def load_scaffold(path, year, month):
    require_file(path, "scaffold")
    handle, reader = open_reader(path)
    required = ["admin_code", "lat", "lon", "year", "month"]
    require_columns(reader.fieldnames, required, "Scaffold")

    rows = []
    seen = set()
    duplicate_count = 0
    observed_months = set()
    with handle:
        for row in reader:
            row_year = parse_int(row.get("year"), "scaffold year")
            row_month = parse_int(row.get("month"), "scaffold month")
            observed_months.add((row_year, row_month))
            if row_year != year or row_month != month:
                continue
            area_id = normalize_area_id(row.get("admin_code"))
            if not area_id:
                fail("Scaffold row has blank admin_code")
            output_row = OrderedDict()
            output_row["area_id"] = area_id
            output_row["admin_code"] = row.get("admin_code", "")
            output_row["lat"] = row.get("lat", "")
            output_row["lon"] = row.get("lon", "")
            output_row["year"] = str(year)
            output_row["month"] = str(month)
            key = (area_id, str(year), str(month))
            if key in seen:
                duplicate_count += 1
            else:
                seen.add(key)
            rows.append(output_row)

    if len(observed_months) != 1:
        fail(
            "Scaffold must contain exactly one month; found {0}".format(
                sorted(observed_months)
            )
        )
    if observed_months and (year, month) not in observed_months:
        fail(
            "Scaffold month does not match target {0}-{1}".format(
                year, str(month).zfill(2)
            )
        )
    if not rows:
        fail("Scaffold has no rows for target {0}-{1}".format(year, str(month).zfill(2)))
    if duplicate_count:
        fail("Duplicate scaffold keys: {0}".format(duplicate_count))
    return rows


def load_fixed_slow(path):
    require_file(path, "fixed/slow features")
    handle, reader = open_reader(path)
    require_columns(reader.fieldnames, ["area_id"], "Fixed/slow features")
    feature_columns = [
        column
        for column in reader.fieldnames
        if column not in {"area_id", "admin_code", "lat", "lon"}
    ]
    by_area = {}
    duplicate_count = 0
    with handle:
        for row in reader:
            area_id = normalize_area_id(row.get("area_id"))
            if not area_id:
                fail("Fixed/slow features row has blank area_id")
            if area_id in by_area:
                duplicate_count += 1
                continue
            by_area[area_id] = row
    if duplicate_count:
        fail("Fixed/slow asset has duplicate area_id rows: {0}".format(duplicate_count))
    return feature_columns, by_area


def load_source_slice(path, year, month, excluded_columns):
    require_file(path, "historical panel")
    handle, reader = open_reader(path)
    require_columns(reader.fieldnames, ["admin_code", "year", "month"], "Historical panel")
    source_columns = [
        column
        for column in reader.fieldnames
        if column not in SOURCE_KEY_COLUMNS
        and column not in excluded_columns
        and not is_engineered_column(column)
    ]
    by_key = {}
    duplicate_count = 0
    scanned_rows = 0
    matched_month_rows = 0
    with handle:
        for row in reader:
            scanned_rows += 1
            row_year = parse_int(row.get("year"), "historical panel year")
            row_month = parse_int(row.get("month"), "historical panel month")
            if row_year != year or row_month != month:
                continue
            matched_month_rows += 1
            area_id = normalize_area_id(row.get("admin_code"))
            key = (area_id, str(year), str(month))
            if key in by_key:
                duplicate_count += 1
                continue
            by_key[key] = row
    return source_columns, by_key, {
        "scanned_rows": scanned_rows,
        "target_month_rows": matched_month_rows,
        "duplicate_rows": duplicate_count,
        "target_month_present_in_source": matched_month_rows > 0,
    }


def missingness(rows, columns):
    result = OrderedDict()
    row_count = len(rows)
    for column in columns:
        missing_count = sum(1 for row in rows if is_blank(row.get(column)))
        result[column] = {
            "missing_count": missing_count,
            "missing_rate": 0 if row_count == 0 else float(missing_count) / row_count,
        }
    return result


def write_csv(path, rows, header):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def build_monthly_base_input(
    year,
    month,
    scaffold_path,
    fixed_slow_path,
    historical_panel_path,
    output_path,
    summary_path,
):
    validate_target_month(year, month)
    scaffold_rows = load_scaffold(scaffold_path, year, month)
    fixed_columns, fixed_by_area = load_fixed_slow(fixed_slow_path)
    source_columns, source_by_key, source_stats = load_source_slice(
        historical_panel_path, year, month, set(fixed_columns)
    )

    output_header = list(ID_COLUMNS)
    output_header.extend(column for column in fixed_columns if column not in output_header)
    output_header.extend(column for column in source_columns if column not in output_header)

    output_rows = []
    fixed_matched = 0
    source_matched = 0
    duplicate_final_keys = 0
    final_seen = set()
    for scaffold_row in scaffold_rows:
        area_id = scaffold_row["area_id"]
        key = (area_id, str(year), str(month))
        if key in final_seen:
            duplicate_final_keys += 1
        else:
            final_seen.add(key)

        output_row = OrderedDict((column, "") for column in output_header)
        for column in ID_COLUMNS:
            output_row[column] = scaffold_row.get(column, "")

        fixed_row = fixed_by_area.get(area_id)
        if fixed_row is not None:
            fixed_matched += 1
            for column in fixed_columns:
                output_row[column] = fixed_row.get(column, "")

        source_row = source_by_key.get(key)
        if source_row is not None:
            source_matched += 1
            for column in source_columns:
                output_row[column] = source_row.get(column, "")

        output_rows.append(output_row)

    if duplicate_final_keys:
        fail("Duplicate final output keys: {0}".format(duplicate_final_keys))

    summary = OrderedDict()
    summary["target_year"] = year
    summary["target_month"] = month
    summary["input_paths"] = {
        "scaffold": str(scaffold_path),
        "fixed_slow_features": str(fixed_slow_path),
        "historical_panel": str(historical_panel_path),
    }
    summary["output_path"] = str(output_path)
    summary["summary_path"] = str(summary_path)
    summary["row_count"] = len(output_rows)
    summary["column_count"] = len(output_header)
    summary["key_columns"] = ["area_id", "year", "month"]
    summary["fixed_slow_join"] = {
        "matched_rows": fixed_matched,
        "unmatched_rows": len(output_rows) - fixed_matched,
        "feature_columns": len(fixed_columns),
    }
    summary["source_join"] = {
        "matched_rows": source_matched,
        "unmatched_rows": len(output_rows) - source_matched,
        "feature_columns": len(source_columns),
        "scanned_rows": source_stats["scanned_rows"],
        "target_month_rows": source_stats["target_month_rows"],
        "duplicate_rows": source_stats["duplicate_rows"],
        "target_month_present_in_source": source_stats["target_month_present_in_source"],
    }
    summary["missingness"] = missingness(output_rows, output_header)

    write_csv(output_path, output_rows, output_header)
    write_json(summary_path, summary)
    return summary


def main():
    args = parse_args()
    (
        year,
        month,
        scaffold_path,
        fixed_slow_path,
        historical_panel_path,
        output_path,
        summary_path,
    ) = resolve_runtime_paths(args)

    summary = build_monthly_base_input(
        year=year,
        month=month,
        scaffold_path=scaffold_path,
        fixed_slow_path=fixed_slow_path,
        historical_panel_path=historical_panel_path,
        output_path=output_path,
        summary_path=summary_path,
    )
    print(
        "Wrote {0} rows and {1} columns to {2}".format(
            summary["row_count"], summary["column_count"], output_path
        )
    )
    print("Wrote QA summary to {0}".format(summary_path))
    if summary["source_join"]["unmatched_rows"]:
        print(
            "WARNING: source join unmatched rows: {0}".format(
                summary["source_join"]["unmatched_rows"]
            )
        )
    if summary["fixed_slow_join"]["unmatched_rows"]:
        print(
            "WARNING: fixed/slow join unmatched rows: {0}".format(
                summary["fixed_slow_join"]["unmatched_rows"]
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
