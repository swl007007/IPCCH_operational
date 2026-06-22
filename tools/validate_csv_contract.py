import argparse
import csv
import re
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate simple IPC-CH CSV contracts."
    )
    parser.add_argument("--csv", required=True, help="CSV file to validate")
    parser.add_argument(
        "--key",
        action="append",
        default=[],
        help="Key column. Repeat for composite keys.",
    )
    parser.add_argument(
        "--required-column",
        action="append",
        default=[],
        help="Required column. Repeat as needed.",
    )
    parser.add_argument(
        "--monthly-regex",
        default="",
        help="Regex used to count monthly columns",
    )
    parser.add_argument("--min-monthly-columns", type=int, default=0)
    return parser.parse_args()


def read_header_and_rows(path):
    with open(path, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return reader.fieldnames or [], rows


def fail(message):
    print("FAIL: " + message)
    return 1


def validate(args):
    if args.min_monthly_columns > 0 and not args.monthly_regex:
        return fail("--min-monthly-columns requires --monthly-regex")

    header, rows = read_header_and_rows(args.csv)
    header_set = set(header)

    if not rows:
        return fail("CSV has no data rows: {0}".format(args.csv))

    for column in args.required_column:
        if column not in header_set:
            return fail("Missing required column: {0}".format(column))

    for column in args.key:
        if column not in header_set:
            return fail("Missing key column: {0}".format(column))

    if args.key:
        seen = set()
        duplicate_count = 0
        for row in rows:
            key = tuple(row.get(column, "") for column in args.key)
            if key in seen:
                duplicate_count += 1
            seen.add(key)
        if duplicate_count:
            return fail("Duplicate key rows: {0}".format(duplicate_count))

    if args.monthly_regex:
        pattern = re.compile(args.monthly_regex)
        monthly_count = sum(1 for column in header if pattern.match(column))
        print("Monthly columns: {0}".format(monthly_count))
        if monthly_count < args.min_monthly_columns:
            return fail(
                "Monthly column count {0} is less than required {1}".format(
                    monthly_count, args.min_monthly_columns
                )
            )

    print("PASS: rows={0} columns={1}".format(len(rows), len(header)))
    return 0


def main():
    try:
        return validate(parse_args())
    except (OSError, csv.Error, re.error, UnicodeError) as error:
        return fail(str(error))


if __name__ == "__main__":
    sys.exit(main())
