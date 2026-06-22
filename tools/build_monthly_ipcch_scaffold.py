import argparse
import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIFIED_ROOT = PROJECT_ROOT / "Outcome" / "ipcch_unified"
DEFAULT_REFERENCE_SCAFFOLD = (
    UNIFIED_ROOT / "interim" / "ipcch_scaffold_202501_202604.csv"
)
DEFAULT_AREA_LOOKUP = UNIFIED_ROOT / "spatial" / "unique_area_id_lat_lon.csv"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a one-month IPCCH production scaffold."
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Target four-digit year. Defaults to the latest month in reference scaffold.",
    )
    parser.add_argument(
        "--month",
        type=int,
        help="Target month 1-12. Defaults to the latest month in reference scaffold.",
    )
    parser.add_argument(
        "--reference-scaffold",
        default=str(DEFAULT_REFERENCE_SCAFFOLD),
        help="Optional multi-month scaffold to extract from when target month exists.",
    )
    parser.add_argument(
        "--area-lookup",
        default=str(DEFAULT_AREA_LOOKUP),
        help="Area lookup used when the target month is not in the reference scaffold.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output CSV. Defaults to Outcome/ipcch_unified/interim/ipcch_scaffold_YYYYMM.csv.",
    )
    return parser.parse_args()


def fail(message):
    raise SystemExit("FAIL: {0}".format(message))


def validate_month(year, month):
    if year is None or year < 1900 or year > 2100:
        fail("Invalid year: {0}".format(year))
    if month is None or month < 1 or month > 12:
        fail("Invalid month: {0}".format(month))


def parse_int(value):
    return int(float(value))


def latest_year_month(reference_scaffold):
    latest = None
    with reference_scaffold.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            value = (parse_int(row["year"]), parse_int(row["month"]))
            latest = value if latest is None else max(latest, value)
    if latest is None:
        fail("Reference scaffold has no rows: {0}".format(reference_scaffold))
    return latest


def extract_from_reference(reference_scaffold, year, month):
    rows = []
    with reference_scaffold.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"admin_code", "lat", "lon", "year", "month"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            fail("Reference scaffold missing columns: {0}".format(", ".join(missing)))
        for row in reader:
            if parse_int(row["year"]) == year and parse_int(row["month"]) == month:
                rows.append(
                    {
                        "admin_code": row["admin_code"],
                        "lat": row["lat"],
                        "lon": row["lon"],
                        "year": str(year),
                        "month": str(month),
                    }
                )
    return rows


def build_from_area_lookup(area_lookup, year, month):
    rows = []
    with area_lookup.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"area_id", "lat", "lon"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            fail("Area lookup missing columns: {0}".format(", ".join(missing)))
        for row in reader:
            rows.append(
                {
                    "admin_code": row["area_id"],
                    "lat": row["lat"],
                    "lon": row["lon"],
                    "year": str(year),
                    "month": str(month),
                }
            )
    return rows


def duplicate_count(rows):
    seen = set()
    duplicates = 0
    for row in rows:
        key = (row["admin_code"], row["lat"], row["lon"], row["year"], row["month"])
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def write_rows(rows, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["admin_code", "lat", "lon", "year", "month"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    reference_scaffold = Path(args.reference_scaffold)
    area_lookup = Path(args.area_lookup)

    if not reference_scaffold.exists():
        fail("Reference scaffold not found: {0}".format(reference_scaffold))
    if not area_lookup.exists():
        fail("Area lookup not found: {0}".format(area_lookup))

    year = args.year
    month = args.month
    if year is None or month is None:
        latest_year, latest_month = latest_year_month(reference_scaffold)
        year = latest_year if year is None else year
        month = latest_month if month is None else month
    validate_month(year, month)

    output = (
        Path(args.output)
        if args.output
        else UNIFIED_ROOT
        / "interim"
        / "ipcch_scaffold_{0}{1}.csv".format(year, str(month).zfill(2))
    )

    rows = extract_from_reference(reference_scaffold, year, month)
    source = "reference_scaffold"
    if not rows:
        rows = build_from_area_lookup(area_lookup, year, month)
        source = "area_lookup"

    duplicates = duplicate_count(rows)
    if duplicates:
        fail("Duplicate scaffold keys: {0}".format(duplicates))

    write_rows(rows, output)
    try:
        display_output = output.relative_to(PROJECT_ROOT)
    except ValueError:
        display_output = output
    print(
        "Wrote {0} rows to {1} using {2}".format(
            len(rows), display_output, source
        )
    )


if __name__ == "__main__":
    main()
