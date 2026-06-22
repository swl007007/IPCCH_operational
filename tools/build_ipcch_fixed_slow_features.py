import argparse
import csv
import hashlib
import sys
from collections import defaultdict


KEY_COLUMNS = ["admin_code", "lat", "lon"]
IDENTIFIER_COLUMNS = ["ISO3", "country", "country_code", "country_en", "state"]
DEFAULT_COASTLINE_SOURCE = (
    "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Google fund/Analysis/"
    "1.Source Data/Coastline_distance_NOAA/"
    "IPCCH_2026_price_completed_unique_lat_lon_coastline_dist.csv"
)
COASTLINE_FEATURE = "coastline_dist"
COASTLINE_FAMILY = "coastline_distance"
COORD_ROUND_DIGITS = 10

FIXED_SLOW_FEATURES = {
    "asap_land_cover": ["crop", "range"],
    "river_distance": ["distance_to_river"],
    "terrain": ["elevation", "ruggedness", "slope"],
    "isric_soilgrids": [
        "sg_cec_5-15cm",
        "sg_cfvo_5-15cm",
        "sg_nitrogen_5-15cm",
        "sg_phh2o_5-15cm",
        "sg_soc_5-15cm",
    ],
    "market_access": ["market_access", "market_distance"],
    "population_context": ["popdensity"],
}

AEZ_FAMILY = "aez"
AEZ_PREFIX = "AEZ_"
EMPTY_VALUES = {"", "NA", "N/A", "NaN", "nan", "None", "null"}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build a unified IPCCH fixed/slow-moving feature handover asset "
            "from the historical IPCCH panel."
        )
    )
    parser.add_argument(
        "--source",
        default="Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv",
        help="Source unified historical IPCCH panel.",
    )
    parser.add_argument(
        "--output",
        default=(
            "Outcome/ipcch_unified/features/"
            "ipcch_fixed_slow_features_by_area.csv"
        ),
        help="Output one-row-per-area fixed/slow-moving feature CSV.",
    )
    parser.add_argument(
        "--summary",
        default=(
            "Outcome/ipcch_unified/features/"
            "ipcch_fixed_slow_features_summary.csv"
        ),
        help="Output feature-level validation summary CSV.",
    )
    parser.add_argument(
        "--coastline-source",
        default=DEFAULT_COASTLINE_SOURCE,
        help=(
            "Lat/lon coastline distance source CSV with columns "
            "lat, lon, coastline_dist."
        ),
    )
    return parser.parse_args()


def fail(message):
    print("FAIL: " + message)
    return 1


def is_missing(value):
    return value is None or value.strip() in EMPTY_VALUES


def year_month_key(row):
    try:
        return int(row["year"]), int(row["month"])
    except (KeyError, TypeError, ValueError):
        return -1, -1


def year_month_text(key):
    year, month = key
    if year < 0 or month < 0:
        return ""
    return "{0:04d}-{1:02d}".format(year, month)


def source_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def coord_key(lat, lon):
    return (
        round(float(lat), COORD_ROUND_DIGITS),
        round(float(lon), COORD_ROUND_DIGITS),
    )


def load_coastline_lookup(path):
    lookup = {}
    with open(path, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader.fieldnames or [], ["lat", "lon", COASTLINE_FEATURE])
        for row in reader:
            value = row.get(COASTLINE_FEATURE, "")
            if is_missing(value):
                continue
            try:
                lookup[coord_key(row["lat"], row["lon"])] = value
            except (TypeError, ValueError):
                continue
    return lookup


def ordered_features(header):
    aez_columns = sorted(
        [column for column in header if column.startswith(AEZ_PREFIX)],
        key=lambda column: int(column.split("_", 1)[1]),
    )
    features = [(column, AEZ_FAMILY) for column in aez_columns]
    for family, columns in FIXED_SLOW_FEATURES.items():
        features.extend((column, family) for column in columns)
    return [(column, family) for column, family in features if column in header]


def require_columns(header, columns):
    missing = [column for column in columns if column not in header]
    if missing:
        raise ValueError("Missing required columns: {0}".format(", ".join(missing)))


def update_area(area, row, features):
    date_key = year_month_key(row)
    area["source_row_count"] += 1
    if area["first_date"] is None or date_key < area["first_date"]:
        area["first_date"] = date_key
    if area["last_date"] is None or date_key > area["last_date"]:
        area["last_date"] = date_key

    for column in KEY_COLUMNS + IDENTIFIER_COLUMNS:
        value = row.get(column, "")
        if not is_missing(value):
            area["latest_ids"][column] = (date_key, value)

    for column, _family in features:
        value = row.get(column, "")
        if is_missing(value):
            area["missing_counts"][column] += 1
            continue
        area["distinct_values"][column].add(value)
        area["nonmissing_counts"][column] += 1
        current = area["latest_features"].get(column)
        if current is None or date_key >= current[0]:
            area["latest_features"][column] = (date_key, value)


def new_area():
    return {
        "source_row_count": 0,
        "first_date": None,
        "last_date": None,
        "latest_ids": {},
        "latest_features": {},
        "distinct_values": defaultdict(set),
        "nonmissing_counts": defaultdict(int),
        "missing_counts": defaultdict(int),
    }


def attach_coastline_distances(areas, coastline_lookup):
    for area in areas.values():
        lat_entry = area["latest_ids"].get("lat")
        lon_entry = area["latest_ids"].get("lon")
        if not lat_entry or not lon_entry:
            continue
        try:
            value = coastline_lookup.get(coord_key(lat_entry[1], lon_entry[1]))
        except (TypeError, ValueError):
            continue
        if is_missing(value):
            continue
        area["latest_features"][COASTLINE_FEATURE] = (area["last_date"], value)
        area["distinct_values"][COASTLINE_FEATURE].add(value)
        area["nonmissing_counts"][COASTLINE_FEATURE] = 1


def build_assets(source, output, summary, coastline_source=DEFAULT_COASTLINE_SOURCE):
    coastline_lookup = load_coastline_lookup(coastline_source)
    with open(source, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        require_columns(header, KEY_COLUMNS + IDENTIFIER_COLUMNS + ["year", "month"])
        features = ordered_features(header)
        features.append((COASTLINE_FEATURE, COASTLINE_FAMILY))
        if not features:
            raise ValueError("No fixed/slow-moving feature columns found")

        areas = defaultdict(new_area)
        source_rows = 0
        for row in reader:
            source_rows += 1
            admin_code = row.get("admin_code", "")
            if is_missing(admin_code):
                continue
            update_area(areas[admin_code], row, features)

    attach_coastline_distances(areas, coastline_lookup)

    feature_columns = [column for column, _family in features]
    output_columns = (
        ["area_id"]
        + KEY_COLUMNS
        + IDENTIFIER_COLUMNS
        + ["source_row_count", "first_year_month", "last_year_month"]
        + feature_columns
    )

    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_columns)
        writer.writeheader()
        for admin_code in sorted(areas, key=lambda value: int(value)):
            area = areas[admin_code]
            row = {
                "area_id": admin_code,
                "admin_code": admin_code,
                "source_row_count": area["source_row_count"],
                "first_year_month": year_month_text(area["first_date"]),
                "last_year_month": year_month_text(area["last_date"]),
            }
            for column in KEY_COLUMNS + IDENTIFIER_COLUMNS:
                row[column] = area["latest_ids"].get(column, ("", ""))[1]
            for column in feature_columns:
                row[column] = area["latest_features"].get(column, ("", ""))[1]
            writer.writerow(row)

    source_hash = source_sha256(source)
    coastline_hash = source_sha256(coastline_source)
    output_hash = source_sha256(output)

    summary_columns = [
        "feature",
        "family",
        "source_file",
        "source_sha256",
        "output_file",
        "output_sha256",
        "selected_value_rule",
        "areas_total",
        "areas_with_value",
        "missing_area_count",
        "source_nonmissing_rows",
        "max_distinct_values_per_area",
        "varying_area_count",
        "classification",
    ]

    with open(summary, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_columns)
        writer.writeheader()
        for column, family in features:
            feature_source = coastline_source if column == COASTLINE_FEATURE else source
            feature_hash = coastline_hash if column == COASTLINE_FEATURE else source_hash
            value_rule = (
                "coordinate match by rounded lat/lon"
                if column == COASTLINE_FEATURE
                else "latest nonmissing value by year/month"
            )
            areas_with_value = 0
            source_nonmissing_rows = 0
            max_distinct = 0
            varying_area_count = 0
            for area in areas.values():
                distinct_count = len(area["distinct_values"][column])
                nonmissing_count = area["nonmissing_counts"][column]
                if nonmissing_count:
                    areas_with_value += 1
                    source_nonmissing_rows += nonmissing_count
                max_distinct = max(max_distinct, distinct_count)
                if distinct_count > 1:
                    varying_area_count += 1
            if max_distinct <= 1:
                classification = "verified_static_in_source_panel"
            else:
                classification = "slow_or_varying_in_source_panel"
            writer.writerow(
                {
                    "feature": column,
                    "family": family,
                    "source_file": feature_source,
                    "source_sha256": feature_hash,
                    "output_file": output,
                    "output_sha256": output_hash,
                    "selected_value_rule": value_rule,
                    "areas_total": len(areas),
                    "areas_with_value": areas_with_value,
                    "missing_area_count": len(areas) - areas_with_value,
                    "source_nonmissing_rows": source_nonmissing_rows,
                    "max_distinct_values_per_area": max_distinct,
                    "varying_area_count": varying_area_count,
                    "classification": classification,
                }
            )

    print(
        "PASS: source_rows={0} areas={1} features={2}".format(
            source_rows, len(areas), len(feature_columns)
        )
    )
    print("OUTPUT: {0}".format(output))
    print("SUMMARY: {0}".format(summary))


def main():
    args = parse_args()
    try:
        build_assets(args.source, args.output, args.summary, args.coastline_source)
    except (OSError, csv.Error, UnicodeError, ValueError) as error:
        return fail(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
