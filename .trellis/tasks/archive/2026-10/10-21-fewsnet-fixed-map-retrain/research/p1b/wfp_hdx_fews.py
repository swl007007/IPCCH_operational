"""FEWS WFP_Price/WFP_Price_std from the HDX "Global - Food Prices" 2026-10-19 files.

HDX rows are renamed to the September raw-export contract and passed unchanged to
`tools.refresh_h5_inputs.wfp_aggregates` (FEWS: 100 + country-month mean of same-series
calendar month-over-month % change; SD of those changes). Column mapping:
countryiso3->Country, admin1->Admin 1, admin2->Admin 2, market->Market Name,
commodity->Commodity, pricetype->Price Type, unit->Unit, currency->Currency,
price->Price, date->Price Date (dd/mm/YYYY). HDX publishes observed prices only
(priceflag actual/aggregate; no forecast rows), so every row is Data Type "Aggregated".
The bootstrap/training panels are compared country-month against the result.

Usage: python wfp_hdx_fews.py --runtime-root <cloud_pipeline> --raw <hdx dir> --out <dir> --cutoff 2026-09
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

RENAME = {"countryiso3": "Country", "admin1": "Admin 1", "admin2": "Admin 2", "market": "Market Name",
          "commodity": "Commodity", "pricetype": "Price Type", "unit": "Unit", "currency": "Currency",
          "price": "Price"}


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cutoff", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime_root))
    from tools.refresh_h5_inputs import wfp_aggregates

    args.out.mkdir(parents=True, exist_ok=True)
    files = sorted(args.raw.glob("wfp_food_prices_global_*.csv"))
    frames, inputs = [], {}
    for path in files:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        frame = frame[~frame["date"].str.startswith("#")]
        frames.append(frame)
        inputs[path.name] = {"sha256": sha256(path), "rows": len(frame)}
    raw = pd.concat(frames, ignore_index=True)
    converted = raw.rename(columns=RENAME)[list(RENAME.values())].copy()
    converted["Price Date"] = pd.to_datetime(raw["date"], format="%Y-%m-%d").dt.strftime("%d/%m/%Y")
    converted["Trend"] = pd.NA
    converted["Data Type"] = "Aggregated"
    converted_path = args.out / "wfp_hdx_converted_contract.csv"
    converted.to_csv(converted_path, index=False)
    result, report = wfp_aggregates(converted_path, cutoff=args.cutoff)
    fews = result["fewsnet"].reset_index()
    fews.to_csv(args.out / "fewsnet_wfp_country_month.csv", index=False)
    report["inputs"] = inputs
    report["converted_sha256"] = sha256(converted_path)
    report["fewsnet_sha256"] = sha256(args.out / "fewsnet_wfp_country_month.csv")
    report["priceflag_counts"] = raw["priceflag"].value_counts().to_dict()
    (args.out / "wfp_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({k: report[k] for k in ("observed_period_min", "observed_period_max", "country_month_keys")}))


if __name__ == "__main__":
    main()
