"""Country-month WFP range audit and streamed source-preservation checks."""
import argparse
import sys
from itertools import zip_longest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import pycountry
from tools.refresh_h5_inputs import WFP_COLUMNS, CONFLICT_COLUMNS, periods, source_iso3, sha256, wfp_aggregates, write_json


def stats(values):
    values = pd.to_numeric(values, errors="raise")
    finite = values.dropna()
    return {"nonmissing": len(finite), "missing": int(values.isna().sum()),
            **{k: float(finite.quantile(q)) if len(finite) else None
               for k, q in [("min", 0), ("p1", .01), ("median", .5), ("p99", .99), ("max", 1)]}}


def audit(root):
    refresh = __import__("json").loads((root / "reports/input_refresh.json").read_text())
    new, _ = wfp_aggregates(root / "sources/wfp_data_7.22.26.csv")
    results = {}
    for system in ["fewsnet", "ipcch"]:
        source = Path(refresh["inputs"][system]["source_path"])
        usecols = ["ISO", "date"] if system == "fewsnet" else ["ISO3", "country_en", "year", "month"]
        base = pd.read_csv(source, usecols=usecols + WFP_COLUMNS, float_precision="round_trip")
        base["period"] = periods(base)
        base["ISO3"] = source_iso3(base)
        base = base.loc[base.period <= "2026-04", ["ISO3", "period", *WFP_COLUMNS]].drop_duplicates()
        result = {"unit": "percentage change +100" if system == "fewsnet" else "Trend +100", "columns": {}}
        for col in WFP_COLUMNS:
            old = base[["ISO3", "period", col]].drop_duplicates()
            counts = old.groupby(["ISO3", "period"])[col].nunique(dropna=False)
            conflicts = counts[counts > 1].index
            unique = old.loc[~pd.MultiIndex.from_frame(old[["ISO3", "period"]]).isin(conflicts)]
            pairs = unique.merge(new[system][[col]], on=["ISO3", "period"], suffixes=("_old", "_new"), validate="one_to_one")
            pairs["difference"] = pairs[f"{col}_new"] - pairs[f"{col}_old"]
            pairs["ratio"] = pairs[f"{col}_new"] / pairs[f"{col}_old"].replace(0, np.nan)
            pairs.to_csv(root / f"reports/wfp_{system}_{col}_comparison.csv", index=False)
            conflict_rows = old.loc[pd.MultiIndex.from_frame(old[["ISO3", "period"]]).isin(conflicts)]
            conflict_rows.to_csv(root / f"reports/wfp_{system}_{col}_multivalue.csv", index=False)
            result["columns"][col] = {"old_unique_country_months": stats(unique[col]),
                "old_2025plus_unique_country_months": stats(unique.loc[unique.period >= "2025-01", col]),
                "new_aggregate": stats(new[system][col]), "new_before_offset": stats(new[system][col] - (100 if col == "WFP_Price" else 0)),
                "multivalue_country_month_keys": len(conflicts), "overlap_keys": len(pairs),
                "paired_nonmissing": int(pairs[[f"{col}_old", f"{col}_new"]].notna().all(axis=1).sum()),
                "difference": stats(pairs.difference), "ratio_nonzero_old": stats(pairs.ratio)}
        results[system] = result
    write_json(root / "reports/wfp_final_range_audit.json", {"status": "passed", "scaler": None,
        "definitions_evidence": "reports/wfp_scale_audit.json", "country_month_unweighted": True,
        "multi_value_policy": "Report every distinct old value separately; exclude ambiguous keys from paired differences.",
        "basket_changes": ["Burundi vegetable oil -> palm oil", "South Sudan and Tajikistan vegetable oil absent in new export"],
        "models": results})
    # Compare actual saved CSVs, not just the pre-write objects used by refresh.
    preserved = {}
    for system, item in refresh["inputs"].items():
        source, output = Path(item["source_path"]), root / item["output_path"]
        assert sha256(source) == item["source_sha256"]
        assert sha256(output) == item["output_sha256"]
        columns = [c for c in pd.read_csv(source, nrows=0).columns if c not in WFP_COLUMNS + CONFLICT_COLUMNS]
        options = dict(usecols=columns, chunksize=20000, float_precision="round_trip", low_memory=False)
        rows = 0
        for before, after in zip_longest(pd.read_csv(source, **options), pd.read_csv(output, **options)):
            assert before is not None and after is not None
            pd.testing.assert_frame_equal(before, after, check_exact=True, check_dtype=False)
            assert (periods(after) <= "2026-04").all()
            rows += len(after)
        preserved[system] = {"rows": rows, "non_source_columns": len(columns), "saved_values_exactly_preserved": True}
    # The required FEWS normalization recomputes two climate derivations and reserializes floats.
    from fewsnet_partitioned_rf_pipeline.core.normalization import CLIMATE_DERIVATIONS
    source, output = root / "inputs/fewsnet_refreshed_raw.csv", root / "inputs/fewsnet_panel.csv"
    max_errors = {}; rows = 0
    opts = dict(chunksize=20000, float_precision="round_trip", low_memory=False)
    for before, after in zip_longest(pd.read_csv(source, **opts), pd.read_csv(output, **opts)):
        assert before is not None and after is not None
        for col in before:
            if pd.api.types.is_numeric_dtype(before[col]) and pd.api.types.is_numeric_dtype(after[col]):
                a, b = before[col].to_numpy(dtype=float), after[col].to_numpy(dtype=float)
                np.testing.assert_allclose(a, b, rtol=1e-10, atol=1e-10, equal_nan=True, err_msg=col)
                finite = np.isfinite(a) & np.isfinite(b)
                max_errors[col] = max(max_errors.get(col, 0), float(np.max(np.abs(a[finite]-b[finite]), initial=0)))
            else:
                pd.testing.assert_series_equal(before[col], after[col], check_dtype=False)
        rows += len(after)
    write_json(root / "reports/saved_input_preservation.json", {"status": "passed", "refresh": preserved,
        "normalization_rows": rows, "normalization_numeric_tolerance": {"rtol": 1e-10, "atol": 1e-10},
        "normalization_derivations": CLIMATE_DERIVATIONS, "normalization_max_absolute_difference_by_column": max_errors})
    print("PASS: saved source columns preserved; WFP country-month range audit; normalization preservation", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    audit(parser.parse_args().root)
