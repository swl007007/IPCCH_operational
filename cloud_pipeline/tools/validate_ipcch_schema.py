import argparse
import csv
import sys
from pathlib import Path


OUTCOME_COLUMNS = [
    "overall_phase",
    "phase1_percent",
    "phase2_percent",
    "phase3_percent",
    "phase4_percent",
    "phase5_percent",
    "estimated_population",
]

FIXED_SLOW_FEATURE_COLUMNS = [
    "AEZ_4000",
    "AEZ_7000",
    "AEZ_9000",
    "AEZ_10000",
    "AEZ_12000",
    "AEZ_17000",
    "AEZ_19000",
    "AEZ_20000",
    "AEZ_25000",
    "AEZ_28000",
    "AEZ_30000",
    "AEZ_31000",
    "AEZ_32000",
    "AEZ_33000",
    "AEZ_34000",
    "AEZ_35000",
    "AEZ_36000",
    "AEZ_38000",
    "AEZ_40000",
    "AEZ_42000",
    "AEZ_43000",
    "crop",
    "range",
    "distance_to_river",
    "elevation",
    "ruggedness",
    "slope",
    "sg_cec_5-15cm",
    "sg_cfvo_5-15cm",
    "sg_nitrogen_5-15cm",
    "sg_phh2o_5-15cm",
    "sg_soc_5-15cm",
    "market_access",
    "market_distance",
    "popdensity",
    "coastline_dist",
]

MODE_CONFIG = {
    "historical-panel": {
        "required_columns": [
            "admin_code",
            "lat",
            "lon",
            "year",
            "month",
        ]
        + OUTCOME_COLUMNS,
        "nonblank_columns": ["admin_code", "lat", "lon", "year", "month"],
        "key_columns": ["admin_code", "lat", "lon", "year", "month"],
        "require_outcome_nonmissing": True,
        "check_area_id_equals_admin_code": False,
    },
    "forecast-scaffold": {
        "required_columns": ["admin_code", "lat", "lon", "year", "month"],
        "nonblank_columns": ["admin_code", "lat", "lon", "year", "month"],
        "key_columns": ["admin_code", "lat", "lon", "year", "month"],
        "require_outcome_nonmissing": False,
        "check_area_id_equals_admin_code": False,
    },
    "fixed-slow-area": {
        "required_columns": [
            "area_id",
            "admin_code",
            "lat",
            "lon",
        ]
        + FIXED_SLOW_FEATURE_COLUMNS,
        "nonblank_columns": ["area_id", "admin_code", "lat", "lon"],
        "key_columns": ["area_id"],
        "require_outcome_nonmissing": False,
        "check_area_id_equals_admin_code": True,
    },
    "model-input-training": {
        "required_columns": ["area_id", "year", "month"] + OUTCOME_COLUMNS,
        "nonblank_columns": ["area_id", "year", "month"] + OUTCOME_COLUMNS,
        "key_columns": ["area_id", "year", "month"],
        "require_outcome_nonmissing": True,
        "check_area_id_equals_admin_code": False,
    },
    "model-input-forecast": {
        "required_columns": ["area_id", "year", "month"],
        "nonblank_columns": ["area_id", "year", "month"],
        "key_columns": ["area_id", "year", "month"],
        "require_outcome_nonmissing": False,
        "check_area_id_equals_admin_code": False,
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate unified IPCCH schema contracts with streaming CSV reads."
    )
    parser.add_argument("--csv", required=True, help="CSV file to validate")
    parser.add_argument(
        "--mode",
        required=True,
        choices=sorted(MODE_CONFIG),
        help="Schema mode to validate.",
    )
    parser.add_argument(
        "--max-duplicate-examples",
        type=int,
        default=5,
        help="Maximum duplicate key examples to print.",
    )
    return parser.parse_args()


def fail(message):
    print("FAIL: {0}".format(message))
    return 1


def is_blank(value):
    return value is None or value == ""


def parse_int(value):
    if is_blank(value):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_float(value):
    if is_blank(value):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def validate_row_values(row, row_number, problems, stats):
    parsed_year = None
    parsed_month = None
    if "year" in row:
        year = parse_int(row["year"])
        if year is None:
            problems.append("row {0}: invalid year".format(row_number))
        else:
            parsed_year = year

    if "month" in row:
        month = parse_int(row["month"])
        if month is None or month < 1 or month > 12:
            problems.append("row {0}: invalid month".format(row_number))
        else:
            parsed_month = month

    if parsed_year is not None and parsed_month is not None:
        year_month = (parsed_year, parsed_month)
        stats["min_year_month"] = (
            year_month
            if stats["min_year_month"] is None
            else min(stats["min_year_month"], year_month)
        )
        stats["max_year_month"] = (
            year_month
            if stats["max_year_month"] is None
            else max(stats["max_year_month"], year_month)
        )

    if "lat" in row and not is_blank(row.get("lat")):
        lat = parse_float(row["lat"])
        if lat is None or lat < -90 or lat > 90:
            problems.append("row {0}: invalid lat".format(row_number))

    if "lon" in row and not is_blank(row.get("lon")):
        lon = parse_float(row["lon"])
        if lon is None or lon < -180 or lon > 180:
            problems.append("row {0}: invalid lon".format(row_number))


def validate(args):
    path = Path(args.csv)
    mode = MODE_CONFIG[args.mode]

    if not path.exists():
        return fail("CSV not found: {0}".format(path))

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        header_set = set(header)

        missing = [
            column for column in mode["required_columns"] if column not in header_set
        ]
        if missing:
            return fail("Missing required columns: {0}".format(", ".join(missing)))

        key_columns = mode["key_columns"]
        missing_keys = [column for column in key_columns if column not in header_set]
        if missing_keys:
            return fail("Missing key columns: {0}".format(", ".join(missing_keys)))

        seen = set()
        duplicate_count = 0
        duplicate_examples = []
        empty_required_counts = {column: 0 for column in mode["required_columns"]}
        outcome_nonmissing = {
            column: 0 for column in OUTCOME_COLUMNS if column in header_set
        }
        row_count = 0
        problems = []
        stats = {
            "min_year_month": None,
            "max_year_month": None,
        }
        area_id_mismatch_count = 0

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            for column in mode["nonblank_columns"]:
                if is_blank(row.get(column)):
                    empty_required_counts[column] += 1

            key = tuple(row.get(column, "") for column in key_columns)
            if key in seen:
                duplicate_count += 1
                if len(duplicate_examples) < args.max_duplicate_examples:
                    duplicate_examples.append(key)
            else:
                seen.add(key)

            for column in outcome_nonmissing:
                if not is_blank(row.get(column)):
                    outcome_nonmissing[column] += 1

            if mode["check_area_id_equals_admin_code"]:
                if row.get("area_id") != row.get("admin_code"):
                    area_id_mismatch_count += 1

            if len(problems) < 10:
                validate_row_values(row, row_number, problems, stats)

    if row_count == 0:
        return fail("CSV has no data rows: {0}".format(path))

    empty_required = {
        column: count for column, count in empty_required_counts.items() if count
    }
    if empty_required:
        return fail("Blank values in nonblank columns: {0}".format(empty_required))

    if duplicate_count:
        return fail(
            "Duplicate key rows: {0}; examples: {1}".format(
                duplicate_count, duplicate_examples
            )
        )

    if problems:
        return fail("; ".join(problems[:10]))

    if area_id_mismatch_count:
        return fail(
            "area_id/admin_code mismatch rows: {0}".format(area_id_mismatch_count)
        )

    if mode["require_outcome_nonmissing"]:
        missing_outcomes = [
            column for column, count in outcome_nonmissing.items() if count == 0
        ]
        if missing_outcomes:
            return fail(
                "Outcome columns have no nonmissing values: {0}".format(
                    ", ".join(missing_outcomes)
                )
            )

    print("PASS: mode={0} rows={1} columns={2}".format(args.mode, row_count, len(header)))
    if stats["min_year_month"] is not None:
        min_year, min_month = stats["min_year_month"]
        max_year, max_month = stats["max_year_month"]
        print(
            "Date coverage observed in file: {0}-{1} through {2}-{3}".format(
                min_year,
                str(min_month).zfill(2),
                max_year,
                str(max_month).zfill(2),
            )
        )
    if outcome_nonmissing:
        print("Outcome nonmissing counts:")
        for column in OUTCOME_COLUMNS:
            if column in outcome_nonmissing:
                print("  {0}: {1}".format(column, outcome_nonmissing[column]))
    return 0


def main():
    try:
        return validate(parse_args())
    except (OSError, csv.Error, UnicodeError) as error:
        return fail(str(error))


if __name__ == "__main__":
    sys.exit(main())
