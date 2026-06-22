from __future__ import print_function

import argparse
import os
import re

import pandas as pd


YYYY_MM_RE = re.compile(r"^([0-9]{4})_([0-9]{2})$")
YYYY_MMM_RE = re.compile(r"^([0-9]{4})\.M([0-9]{2})$")
YYYY_MM_BAND_RE = re.compile(r"^([0-9]{4})_([0-9]{2})_B([0-9]+)$")


def parse_month_column(column_name):
    """Return (year, month, band) for supported ArcPy wide date columns."""
    text = str(column_name)

    match = YYYY_MM_BAND_RE.match(text)
    if match:
        return int(match.group(1)), int(match.group(2)), "B" + match.group(3)

    match = YYYY_MM_RE.match(text)
    if match:
        return int(match.group(1)), int(match.group(2)), None

    match = YYYY_MMM_RE.match(text)
    if match:
        return int(match.group(1)), int(match.group(2)), None

    return None


def _prepare_area_ids(wide_df, id_column, mapping_df, mapping_region_column, mapping_area_column):
    if id_column not in wide_df.columns:
        raise ValueError("Missing id column in wide table: {0}".format(id_column))

    prepared = wide_df.copy()

    if mapping_df is None:
        prepared["area_id"] = prepared[id_column]
        return prepared

    required = [mapping_region_column, mapping_area_column]
    missing = [col for col in required if col not in mapping_df.columns]
    if missing:
        raise ValueError("Missing mapping columns: {0}".format(", ".join(missing)))

    duplicate_mapping = mapping_df[mapping_region_column].duplicated(keep=False)
    if duplicate_mapping.any():
        raise ValueError("Duplicate mapping values in {0}".format(mapping_region_column))

    mapping = mapping_df[required].rename(columns={
        mapping_region_column: id_column,
        mapping_area_column: "area_id",
    })

    prepared = prepared.merge(mapping, on=id_column, how="left", indicator=True)
    unmatched = prepared[prepared["_merge"] != "both"]
    if len(unmatched) > 0:
        raise ValueError("Unmatched region_id values: {0}".format(len(unmatched)))
    return prepared.drop(columns=["_merge"])


def reshape_wide_table(
    wide_df,
    feature_name,
    id_column="region_id",
    mapping_df=None,
    mapping_region_column="region_id",
    mapping_area_column="area_id",
):
    """Convert ArcPy wide extraction output to area_id/year/month feature rows."""
    prepared = _prepare_area_ids(
        wide_df,
        id_column,
        mapping_df,
        mapping_region_column,
        mapping_area_column,
    )

    parsed_columns = []
    for column in prepared.columns:
        parsed = parse_month_column(column)
        if parsed is not None:
            parsed_columns.append((column, parsed[0], parsed[1], parsed[2]))

    if not parsed_columns:
        raise ValueError("No supported monthly columns found")

    parsed_columns.sort(key=lambda item: (item[1], item[2], item[3] or ""))

    records_by_key = {}
    key_order = []

    for _, row in prepared.iterrows():
        area_id = row["area_id"]
        for column, year, month, band in parsed_columns:
            key = (area_id, year, month)
            if key not in records_by_key:
                records_by_key[key] = {
                    "area_id": area_id,
                    "year": year,
                    "month": month,
                }
                key_order.append(key)

            output_column = feature_name
            if band is not None:
                output_column = feature_name + "_" + band
            records_by_key[key][output_column] = row[column]

    records = [records_by_key[key] for key in key_order]
    result = pd.DataFrame(records)
    result = result.sort_values(["area_id", "year", "month"]).reset_index(drop=True)
    return result.astype(object).where(pd.notnull(result), None)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Reshape an ArcPy wide remote-sensing extraction CSV into area_id/year/month rows."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--feature-name", required=True)
    parser.add_argument("--id-column", default="region_id")
    parser.add_argument("--mapping-csv")
    parser.add_argument("--mapping-region-column", default="region_id")
    parser.add_argument("--mapping-area-column", default="area_id")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    wide_df = pd.read_csv(args.input_csv)
    mapping_df = pd.read_csv(args.mapping_csv) if args.mapping_csv else None

    result = reshape_wide_table(
        wide_df,
        args.feature_name,
        id_column=args.id_column,
        mapping_df=mapping_df,
        mapping_region_column=args.mapping_region_column,
        mapping_area_column=args.mapping_area_column,
    )

    output_folder = os.path.dirname(args.output_csv)
    if output_folder and not os.path.isdir(output_folder):
        os.makedirs(output_folder)
    result.to_csv(args.output_csv, index=False)
    print("Wrote {0} rows to {1}".format(len(result), args.output_csv))


if __name__ == "__main__":
    main()
