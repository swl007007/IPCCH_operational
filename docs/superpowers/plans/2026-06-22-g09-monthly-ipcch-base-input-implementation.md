# G-09 Monthly IPCCH Base Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one unified monthly IPCCH base input assembly path that outputs a long one-month table keyed by `area_id`, `year`, and `month`.

**Architecture:** Add a focused final assembly script under `Final_harmonise/` that reads the one-month scaffold, fixed/slow area features, and the unified historical panel. The script writes a base monthly input CSV plus QA JSON and leaves model weights, model pipeline, and G-07 engineered features outside this scope.

**Tech Stack:** Python 3 standard library (`argparse`, `csv`, `json`, `pathlib`, `unittest`), existing `workflow_config.py`, existing IPCCH CSV assets.

---

## File Structure

- Create: `tests/test_build_monthly_ipcch_base_input.py`
  - Unit tests using temporary CSV fixtures and `unittest`.
- Create: `Final_harmonise/00_build_monthly_ipcch_base_input.py`
  - Production CLI and reusable `build_monthly_base_input()` function.
- Modify: `.gitignore`
  - Ignore generated monthly model-input CSV/JSON files.
- Modify: `config/paths_template.ini`
  - Add model-input output folder and G-09 monthly base output paths.
- Modify: `docs/03_workflow_runbook.md`
  - Replace split final harmonise as the production path with unified monthly assembly.
- Modify: `docs/04_output_inventory.md`
  - List the G-09 monthly base input CSV and QA summary.
- Modify: `docs/05_weilun_handover_gap_list.md`
  - Mark G-09 resolved for base monthly assembly after implementation and keep G-06/G-07 deferred.
- Move: `Final_harmonise/00_combine_all_ch.py`, `Final_harmonise/00_combine_all_IPC.py`, `Final_harmonise/01_CH_final_process.py`, `Final_harmonise/01_IPC_final_process.py`
  - Move to `archive/legacy_final_harmonise/` with a manifest so new operators do not treat them as production.

### Task 1: Add Unit Tests For Unified Monthly Assembly

**Files:**
- Create: `tests/test_build_monthly_ipcch_base_input.py`

- [ ] **Step 1: Create the test file**

Create `tests/test_build_monthly_ipcch_base_input.py` with this content:

```python
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "Final_harmonise" / "00_build_monthly_ipcch_base_input.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "build_monthly_ipcch_base_input", str(SCRIPT_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class MonthlyIPCCHBaseInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scaffold = self.root / "ipcch_scaffold_202604.csv"
        self.future_scaffold = self.root / "ipcch_scaffold_202605.csv"
        self.fixed = self.root / "fixed.csv"
        self.panel = self.root / "panel.csv"
        self.output = self.root / "ipcch_monthly_base_input_202604.csv"
        self.summary = self.root / "ipcch_monthly_base_input_202604_summary.json"
        self.future_output = self.root / "ipcch_monthly_base_input_202605.csv"
        self.future_summary = self.root / "ipcch_monthly_base_input_202605_summary.json"

        write_csv(
            self.scaffold,
            ["admin_code", "lat", "lon", "year", "month"],
            [
                {
                    "admin_code": "101.0",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "4",
                },
                {
                    "admin_code": "102",
                    "lat": "1.2",
                    "lon": "31.2",
                    "year": "2026",
                    "month": "4",
                },
            ],
        )
        write_csv(
            self.future_scaffold,
            ["admin_code", "lat", "lon", "year", "month"],
            [
                {
                    "admin_code": "101.0",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "5",
                }
            ],
        )
        write_csv(
            self.fixed,
            ["area_id", "admin_code", "lat", "lon", "crop", "elevation"],
            [
                {
                    "area_id": "101",
                    "admin_code": "101",
                    "lat": "1.1",
                    "lon": "31.1",
                    "crop": "1",
                    "elevation": "500",
                },
                {
                    "area_id": "102",
                    "admin_code": "102",
                    "lat": "1.2",
                    "lon": "31.2",
                    "crop": "0",
                    "elevation": "750",
                },
            ],
        )
        write_csv(
            self.panel,
            [
                "admin_code",
                "lat",
                "lon",
                "year",
                "month",
                "overall_phase",
                "EVI_mean",
                "Rainf_f_tavg_mean",
                "EVI_mean__l12",
            ],
            [
                {
                    "admin_code": "101",
                    "lat": "9.9",
                    "lon": "99.9",
                    "year": "2026",
                    "month": "4",
                    "overall_phase": "3",
                    "EVI_mean": "0.23",
                    "Rainf_f_tavg_mean": "12",
                    "EVI_mean__l12": "0.20",
                },
                {
                    "admin_code": "102",
                    "lat": "8.8",
                    "lon": "88.8",
                    "year": "2026",
                    "month": "4",
                    "overall_phase": "2",
                    "EVI_mean": "0.44",
                    "Rainf_f_tavg_mean": "15",
                    "EVI_mean__l12": "0.39",
                },
                {
                    "admin_code": "101",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "3",
                    "overall_phase": "1",
                    "EVI_mean": "0.11",
                    "Rainf_f_tavg_mean": "7",
                    "EVI_mean__l12": "0.08",
                },
            ],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_builds_base_input_for_observed_month(self):
        module = load_module()

        result = module.build_monthly_base_input(
            year=2026,
            month=4,
            scaffold_path=self.scaffold,
            fixed_slow_path=self.fixed,
            historical_panel_path=self.panel,
            output_path=self.output,
            summary_path=self.summary,
        )

        rows = read_csv(self.output)
        self.assertEqual(2, len(rows))
        self.assertEqual(
            ["area_id", "admin_code", "lat", "lon", "year", "month"],
            list(rows[0].keys())[:6],
        )
        self.assertEqual("101", rows[0]["area_id"])
        self.assertEqual("101.0", rows[0]["admin_code"])
        self.assertEqual("1", rows[0]["crop"])
        self.assertEqual("500", rows[0]["elevation"])
        self.assertEqual("3", rows[0]["overall_phase"])
        self.assertEqual("0.23", rows[0]["EVI_mean"])
        self.assertNotIn("EVI_mean__l12", rows[0])

        with self.summary.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertEqual(result["row_count"], summary["row_count"])
        self.assertEqual(2, summary["fixed_slow_join"]["matched_rows"])
        self.assertEqual(0, summary["fixed_slow_join"]["unmatched_rows"])
        self.assertEqual(2, summary["source_join"]["matched_rows"])
        self.assertEqual(0, summary["source_join"]["unmatched_rows"])
        self.assertTrue(summary["source_join"]["target_month_present_in_source"])

    def test_future_month_keeps_scaffold_and_fixed_features(self):
        module = load_module()

        module.build_monthly_base_input(
            year=2026,
            month=5,
            scaffold_path=self.future_scaffold,
            fixed_slow_path=self.fixed,
            historical_panel_path=self.panel,
            output_path=self.future_output,
            summary_path=self.future_summary,
        )

        rows = read_csv(self.future_output)
        self.assertEqual(1, len(rows))
        self.assertEqual("101", rows[0]["area_id"])
        self.assertEqual("1", rows[0]["crop"])
        self.assertEqual("", rows[0]["EVI_mean"])

        with self.future_summary.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertFalse(summary["source_join"]["target_month_present_in_source"])
        self.assertEqual(0, summary["source_join"]["matched_rows"])
        self.assertEqual(1, summary["source_join"]["unmatched_rows"])

    def test_duplicate_scaffold_key_fails(self):
        module = load_module()
        duplicate_scaffold = self.root / "duplicate_scaffold.csv"
        write_csv(
            duplicate_scaffold,
            ["admin_code", "lat", "lon", "year", "month"],
            [
                {
                    "admin_code": "101",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "4",
                },
                {
                    "admin_code": "101.0",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "4",
                },
            ],
        )

        with self.assertRaises(SystemExit) as raised:
            module.build_monthly_base_input(
                year=2026,
                month=4,
                scaffold_path=duplicate_scaffold,
                fixed_slow_path=self.fixed,
                historical_panel_path=self.panel,
                output_path=self.output,
                summary_path=self.summary,
            )
        self.assertIn("Duplicate scaffold keys", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail before implementation**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_build_monthly_ipcch_base_input.py' -v
```

Expected: FAIL or ERROR because `Final_harmonise/00_build_monthly_ipcch_base_input.py` does not exist yet.

### Task 2: Implement Unified Monthly Base Input Builder

**Files:**
- Create: `Final_harmonise/00_build_monthly_ipcch_base_input.py`
- Test: `tests/test_build_monthly_ipcch_base_input.py`

- [ ] **Step 1: Create the script**

Create `Final_harmonise/00_build_monthly_ipcch_base_input.py` with this content:

```python
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
        help="Optional paths.ini. If omitted, IPCCH_CONFIG or config/paths.ini is used when present.",
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
    if config is not None and config.has_section(section) and config.has_option(section, option):
        return workflow_config.get_value(config, section, option)
    return default


def config_path(config, section, option, default):
    if config is not None and config.has_section(section) and config.has_option(section, option):
        return Path(workflow_config.resolve_path(config, section, option))
    return Path(default)


def resolve_runtime_paths(args):
    config = load_optional_config(args.config)
    year = args.year
    month = args.month
    if year is None:
        year = parse_int(config_value(config, "production", "target_year", "2026"), "target_year")
    if month is None:
        month = parse_int(config_value(config, "production", "target_month", "4"), "target_month")
    validate_target_month(year, month)

    if args.scaffold:
        scaffold_path = Path(args.scaffold)
    elif config is not None and config.has_section("paths") and config.has_option("paths", "scaffold_input"):
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
        fail("Scaffold must contain exactly one month; found {0}".format(sorted(observed_months)))
    if observed_months and (year, month) not in observed_months:
        fail("Scaffold month does not match target {0}-{1}".format(year, str(month).zfill(2)))
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
        column for column in reader.fieldnames if column not in {"area_id", "admin_code", "lat", "lon"}
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
```

- [ ] **Step 2: Run the unit tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_build_monthly_ipcch_base_input.py' -v
```

Expected: PASS for the three tests.

- [ ] **Step 3: Compile the script**

Run:

```bash
python3 -m py_compile Final_harmonise/00_build_monthly_ipcch_base_input.py tests/test_build_monthly_ipcch_base_input.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit Task 1 and Task 2**

Run:

```bash
git add Final_harmonise/00_build_monthly_ipcch_base_input.py tests/test_build_monthly_ipcch_base_input.py
git commit -m "feat: add monthly IPCCH base input builder"
```

Expected: commit includes only the new script and test file.

### Task 3: Update Config, Docs, And Legacy Script Location

**Files:**
- Modify: `.gitignore`
- Modify: `config/paths_template.ini`
- Modify: `docs/03_workflow_runbook.md`
- Modify: `docs/04_output_inventory.md`
- Modify: `docs/05_weilun_handover_gap_list.md`
- Create: `archive/legacy_final_harmonise/MANIFEST.md`
- Move: `Final_harmonise/00_combine_all_ch.py`
- Move: `Final_harmonise/00_combine_all_IPC.py`
- Move: `Final_harmonise/01_CH_final_process.py`
- Move: `Final_harmonise/01_IPC_final_process.py`

- [ ] **Step 1: Ignore generated monthly model-input outputs**

Append this block to `.gitignore`:

```gitignore

# Generated monthly IPCCH model-input handover outputs
Outcome/ipcch_unified/model_input/*.csv
Outcome/ipcch_unified/model_input/*.json
```

- [ ] **Step 2: Add G-09 paths to the config template**

In `config/paths_template.ini`, add this line under `[paths]` after `fixed_slow_features_input`:

```ini
model_input_output_folder = ${PROJECT_ROOT}\Outcome\ipcch_unified\model_input
```

In `config/paths_template.ini`, add these lines under `[production]` after `monthly_model_input_output`:

```ini
monthly_base_input_output = ${PROJECT_ROOT}\Outcome\ipcch_unified\model_input\ipcch_monthly_base_input_202604.csv
monthly_base_input_summary = ${PROJECT_ROOT}\Outcome\ipcch_unified\model_input\ipcch_monthly_base_input_202604_summary.json
```

- [ ] **Step 3: Replace the production final harmonise runbook section**

In `docs/03_workflow_runbook.md`, replace the current `## Final Harmonise` section with:

````markdown
## Final Monthly IPCCH Assembly

Production uses one unified IPCCH monthly assembly path. It does not produce
separate CH and IPC model inputs.

For the current handover month:

```bash
python3 Final_harmonise/00_build_monthly_ipcch_base_input.py --year 2026 --month 4
python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
```

Expected outputs:

- `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv`
- `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json`

The output is a long monthly table keyed by `area_id`, `year`, and `month`.
It starts from the one-month scaffold, joins fixed/slow area features, and
joins same-month source-level fields from the unified historical panel when
the target month exists there.

Legacy split CH/IPC final harmonise scripts are archived under
`archive/legacy_final_harmonise/`. They are compatibility references, not the
production monthly IPCCH input path.
````

- [ ] **Step 4: Update the smoke-test row for final assembly**

In `docs/03_workflow_runbook.md`, replace the smoke-test table row that starts
with `| Final harmonise |` with:

```markdown
| Final monthly IPCCH assembly | One-month scaffold plus fixed/slow fixture and a small historical-panel slice | Unified monthly base input has one row per `area_id`, `year`, `month`; summary JSON reports join coverage and missingness. |
```

- [ ] **Step 5: Add the G-09 output to the output inventory**

In `docs/04_output_inventory.md`, in the workflow output contract table, replace
the `Unified IPCCH monthly model input` row with:

```markdown
| Unified IPCCH monthly model input | `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_YYYYMM.csv` plus `_summary.json` | `area_id`, `year`, `month` | Long monthly base input surface | Combined with exported model weights, model pipeline, and G-07 transformations when those assets are exported. |
```

In `docs/04_output_inventory.md`, add this validation example after the G-05
schema examples:

````markdown
Unified G-09 monthly base input example:

```bash
python3 Final_harmonise/00_build_monthly_ipcch_base_input.py --year 2026 --month 4
python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
```
````

- [ ] **Step 6: Mark G-09 resolved for base assembly**

In `docs/05_weilun_handover_gap_list.md`, update the G-09 table row to:

```markdown
| G-09 | Final monthly model-input assembly refactor | Resolved for base assembly | Added unified monthly IPCCH base input builder that starts from the one-month scaffold, joins fixed/slow features and same-month source-level fields, and writes one long IPCCH monthly table plus QA summary. G-06 model weights/pipeline and G-07 model-specific transformations remain deferred. |
```

In the `## G-09 Open: Final Monthly Model-Input Assembly Refactor` section,
change the heading to:

```markdown
## G-09 Resolution: Final Monthly Base Input Assembly
```

Then replace the section body with:

```markdown
Generated assets after running the 2026-04 smoke test:

| File | Role |
| --- | --- |
| `Final_harmonise/00_build_monthly_ipcch_base_input.py` | Unified monthly base input builder. |
| `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv` | One-month IPCCH base input surface keyed by `area_id`, `year`, and `month`. |
| `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json` | QA summary with row counts, join coverage, duplicate counts, and missingness. |

The builder is intentionally conservative. It does not copy
`assembled_IPCCH/model_ready/*`, does not create lag/rolling/scope-specific
model features, and does not require model weights or the exported model
pipeline. Those remain G-06 and G-07.

Legacy split CH/IPC final harmonise scripts are archived under
`archive/legacy_final_harmonise/` as compatibility references only.
```

- [ ] **Step 7: Move legacy final harmonise scripts into archive**

Run:

```bash
mkdir -p archive/legacy_final_harmonise
mv Final_harmonise/00_combine_all_ch.py archive/legacy_final_harmonise/00_combine_all_ch.py
mv Final_harmonise/00_combine_all_IPC.py archive/legacy_final_harmonise/00_combine_all_IPC.py
mv Final_harmonise/01_CH_final_process.py archive/legacy_final_harmonise/01_CH_final_process.py
mv Final_harmonise/01_IPC_final_process.py archive/legacy_final_harmonise/01_IPC_final_process.py
```

Create `archive/legacy_final_harmonise/MANIFEST.md` with:

```markdown
# Legacy Final Harmonise Scripts

These scripts are archived compatibility references from the pre-G-09 split
CH/IPC workflow. They are not the production path for monthly IPCCH model input.

Use `Final_harmonise/00_build_monthly_ipcch_base_input.py` for the unified
monthly base input assembly.

| File | Legacy role |
| --- | --- |
| `00_combine_all_ch.py` | Combined CH source workflow outputs into a legacy CH panel. |
| `00_combine_all_IPC.py` | Combined IPC source workflow outputs into a legacy IPC panel. |
| `01_CH_final_process.py` | Legacy CH final processing. |
| `01_IPC_final_process.py` | Legacy IPC final processing. |
```

- [ ] **Step 8: Run tests and compile after docs/archive changes**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_build_monthly_ipcch_base_input.py' -v
python3 -m py_compile Final_harmonise/00_build_monthly_ipcch_base_input.py tests/test_build_monthly_ipcch_base_input.py
```

Expected: tests pass and compile exits with code 0.

- [ ] **Step 9: Commit config, docs, and archive changes**

Run:

```bash
git add .gitignore config/paths_template.ini docs/03_workflow_runbook.md docs/04_output_inventory.md docs/05_weilun_handover_gap_list.md archive/legacy_final_harmonise Final_harmonise
git commit -m "docs: document unified monthly IPCCH assembly"
```

Expected: commit contains config/docs/archive changes and the legacy script moves, without adding generated `Outcome/ipcch_unified/model_input/*.csv` or `*.json`.

### Task 4: Run The 2026-04 Smoke Test On Real Assets

**Files:**
- Generate local data: `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv`
- Generate local data: `Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json`

- [ ] **Step 1: Run the unified monthly assembly**

Run:

```bash
python3 Final_harmonise/00_build_monthly_ipcch_base_input.py --year 2026 --month 4
```

Expected for the current 2026-04 handover assets:

```text
Wrote 6227 rows and 147 columns to Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
Wrote QA summary to Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json
WARNING: source join unmatched rows: 39
```

- [ ] **Step 2: Validate the generated model-input row grain**

Run:

```bash
python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
```

Expected:

```text
PASS: mode=model-input-forecast rows=6227 columns=147
Date coverage observed in file: 2026-04 through 2026-04
```

- [ ] **Step 3: Inspect the QA summary**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path

path = Path("Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json")
summary = json.loads(path.read_text(encoding="utf-8"))
print("rows", summary["row_count"])
print("columns", summary["column_count"])
print("fixed_slow_join", summary["fixed_slow_join"])
print("source_join", summary["source_join"])
PY
```

Expected:

```text
rows 6227
columns 147
fixed_slow_join {'feature_columns': 43, 'matched_rows': 6227, 'unmatched_rows': 0}
source_join {'duplicate_rows': 0, 'feature_columns': 98, 'matched_rows': 6188, 'scanned_rows': 1219868, 'target_month_present_in_source': True, 'target_month_rows': 6188, 'unmatched_rows': 39}
```

- [ ] **Step 4: Confirm generated data remains untracked**

Run:

```bash
git status --short -- Outcome/ipcch_unified/model_input
```

Expected: no output because generated CSV/JSON files are ignored.

### Task 5: Final Verification And Handoff Summary

**Files:**
- No new files beyond earlier tasks.

- [ ] **Step 1: Run full G-09 verification commands**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_build_monthly_ipcch_base_input.py' -v
python3 -m py_compile Final_harmonise/00_build_monthly_ipcch_base_input.py tests/test_build_monthly_ipcch_base_input.py tools/validate_ipcch_schema.py workflow_config.py
python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
```

Expected: unit tests pass, compile command exits with code 0, and schema validator prints `PASS`.

- [ ] **Step 2: Review changed paths**

Run:

```bash
git status --short
```

Expected:

- G-09 code/docs/test files are either committed or shown as staged/modified for this task.
- Generated `Outcome/ipcch_unified/model_input/*.csv` and `*.json` files do not appear.
- Pre-existing unrelated handover refactor changes remain untouched.

- [ ] **Step 3: Report completion**

In the final handoff message, include:

```text
Implemented G-09 unified monthly IPCCH base input assembly.

Key outputs:
- Final_harmonise/00_build_monthly_ipcch_base_input.py
- Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
- Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604_summary.json

Verification:
- python3 -m unittest discover -s tests -p 'test_build_monthly_ipcch_base_input.py' -v
- python3 -m py_compile Final_harmonise/00_build_monthly_ipcch_base_input.py tests/test_build_monthly_ipcch_base_input.py tools/validate_ipcch_schema.py workflow_config.py
- python3 tools/validate_ipcch_schema.py --mode model-input-forecast --csv Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv
```

## Self-Review Notes

- Spec coverage: Tasks 1 and 2 implement the assembly flow, key validation, source-column exclusion, soft warnings through summary JSON, and future-month behavior. Task 3 updates docs/config and archives legacy split scripts. Task 4 verifies the 2026-04 sample. Task 5 verifies the final state.
- G-06 and G-07 boundaries are preserved: the implementation does not use model weights, model pipeline assets, or `assembled_IPCCH/model_ready/*` files.
- Generated monthly CSV/JSON outputs are local data artifacts and are ignored by Git.
