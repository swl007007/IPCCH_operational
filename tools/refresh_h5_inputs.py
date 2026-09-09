"""Refresh the approved April 2026 panels without overwriting source artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pycountry
from sklearn.metrics.pairwise import haversine_distances

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = "2026-04"
WFP_COLUMNS = ["WFP_Price", "WFP_Price_std"]
EVENT_TYPES = {"Battles": "battles", "Explosions/Remote violence": "explosions",
               "Violence against civilians": "violence"}
METRICS = [f"{kind}_{event}" for kind in ("event_count", "sum_fatalities")
           for event in EVENT_TYPES.values()]
CONFLICT_COLUMNS = [f"{metric}{suffix}" for suffix in ("", "_w5", "_w10")
                    for metric in METRICS] + ["distance_to_nearest_acled"]


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def country_iso3(name: str) -> str:
    aliases = {"Democratic Republic of the Congo": "COD", "Turkey": "TUR",
               "Iran (Islamic Republic of)": "IRN"}
    return aliases[name] if name in aliases else pycountry.countries.lookup(name).alpha_3


def periods(frame: pd.DataFrame) -> pd.Series:
    dates = (pd.to_datetime(frame["date"]) if "date" in frame else
             pd.to_datetime(dict(year=frame.year, month=frame.month, day=1)))
    return dates.dt.to_period("M").astype(str)


def source_iso3(frame: pd.DataFrame) -> pd.Series:
    if "ISO" in frame:
        return frame.ISO.map(lambda x: pycountry.countries.get(alpha_2=x).alpha_3)
    codes = frame.ISO3.copy()
    missing = codes.isna() | codes.astype(str).str.strip().eq("")
    if missing.any():
        codes.loc[missing] = frame.loc[missing, "country_en"].map(country_iso3)
    return codes


def monthly_price_change(frame: pd.DataFrame, keys: list[str], price: str) -> pd.DataFrame:
    """Join previous calendar month of the same market/commodity/unit series."""
    if frame.duplicated(keys + ["period"]).any():
        raise ValueError("duplicate WFP price-series month keys")
    previous = frame[keys + ["period", price]].copy()
    previous["period"] = (pd.PeriodIndex(previous.period, freq="M") + 1).astype(str)
    previous = previous.rename(columns={price: "previous_price"})
    joined = frame.merge(previous, on=keys + ["period"], how="inner", validate="one_to_one")
    joined["change"] = 100 * (joined[price] / joined.previous_price - 1)
    joined.loc[joined.previous_price.le(0), "change"] = np.nan
    joined["change"] = joined.change.replace([np.inf, -np.inf], np.nan)
    return joined


def wfp_aggregates(path: Path) -> tuple[dict[str, pd.DataFrame], dict]:
    raw = pd.read_csv(path)
    raw["period"] = pd.to_datetime(raw["Price Date"], format="%d/%m/%Y").dt.to_period("M").astype(str)
    frame = raw.loc[(raw.period <= CUTOFF) & raw["Data Type"].eq("Aggregated")].copy()
    frame["ISO3"] = frame.Country.map(country_iso3)
    for col in ["Price", "Trend"]:
        frame[col] = pd.to_numeric(frame[col], errors="raise")
    keys = ["Country", "Admin 1", "Admin 2", "Market Name", "Commodity",
            "Price Type", "Unit", "Currency"]
    changes = monthly_price_change(frame, keys, "Price")
    result = {}
    for name, values, column in [("fewsnet", changes, "change"), ("ipcch", frame, "Trend")]:
        agg = values.groupby(["ISO3", "period"])[column].agg(["mean", "std"])
        agg.columns = WFP_COLUMNS
        agg["WFP_Price"] += 100
        # Only supported indicator keys supersede historical values.
        result[name] = agg.dropna(subset=["WFP_Price"])
    report = {"raw_rows": len(raw), "observed_rows_through_cutoff": len(frame),
              "forecast_rows_excluded_through_cutoff": int(((raw.period <= CUTOFF) & raw["Data Type"].eq("Forecast")).sum()),
              "rows_after_cutoff": int((raw.period > CUTOFF).sum()),
              "source_period_min": raw.period.min(), "source_period_max": raw.period.max(),
              "fewsnet_formula": "100 + mean(100 * (Price(t)/Price(t-1)-1)); same market/commodity/type/unit/currency; calendar join",
              "ipcch_formula": "100 + mean(Trend)", "standard_deviation": "sample SD of respective unshifted indicator",
              "scaler": None, "country_month_keys": {k: len(v) for k, v in result.items()}}
    return result, report


def conflict_aggregates(path: Path) -> tuple[pd.DataFrame, dict]:
    """Same location pivot/admin hierarchy as ACLED/00_add_acled_features.py."""
    raw = pd.read_csv(path, low_memory=False)
    dates = pd.to_datetime(raw.event_date, format="%Y-%m-%d")
    frame = raw.loc[dates.dt.to_period("M").astype(str) <= CUTOFF].copy()
    frame["year"] = dates.loc[frame.index].dt.year
    frame["month"] = dates.loc[frame.index].dt.month
    locations = ["country", "admin1", "admin2", "admin3", "location", "latitude", "longitude", "year", "month"]
    agg = frame.groupby(["event_type"] + locations).agg(
        event_count=("event_type", "count"), sum_fatalities=("fatalities", "sum")).reset_index()
    agg["event_type"] = agg.event_type.replace(EVENT_TYPES)
    pivot = agg.pivot_table(index=locations, columns="event_type",
                            values=["event_count", "sum_fatalities"], fill_value=0)
    pivot.columns = ["_".join(col) for col in pivot.columns]
    pivot = pivot.reset_index().rename(columns={"latitude": "lat", "longitude": "lon"})
    if not set(METRICS).issubset(pivot.columns):
        raise ValueError("ACLED source lacks a required event family")
    # pandas groupby dropna=True intentionally preserves the legacy admin semantics.
    adm3 = pivot.groupby(["country", "admin1", "admin2", "admin3", "year", "month"]).agg(
        **{c: (c, "sum") for c in METRICS}, lat=("lat", "mean"), lon=("lon", "mean")).reset_index()
    for admins, suffix in [(["country", "admin1", "admin2"], "_w5"), (["country", "admin1"], "_w10")]:
        keys = admins + ["year", "month"]
        level = pivot.groupby(keys)[METRICS].sum().add_suffix(suffix).reset_index()
        adm3 = adm3.merge(level, on=keys, validate="many_to_one")
    adm3["period"] = periods(adm3)
    report = {"raw_rows": len(raw), "rows_through_cutoff": len(frame),
              "actual_date_min": str(dates.min().date()), "actual_date_max": str(dates.max().date()),
              "admin3_rows": len(adm3), "covered_months": sorted(adm3.period.unique()),
              "missing_location_key_rows_excluded_by_legacy_groupby": int(frame[locations].isna().any(axis=1).sum()),
              "event_type_counts": frame.event_type.value_counts().to_dict(),
              "matching": "same month, globally nearest admin3 mean point, haversine radius 6371km, <=500km"}
    return adm3, report


def replace_sources(frame: pd.DataFrame, wfp: pd.DataFrame, acled: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out = frame.copy()
    month = periods(out)
    codes = source_iso3(out)
    lookup = pd.MultiIndex.from_arrays([codes, month], names=["ISO3", "period"])
    covered = lookup.isin(wfp.index)
    new_values = wfp.reindex(lookup)
    for col in WFP_COLUMNS:
        out.loc[covered, col] = new_values.loc[covered, col].to_numpy()
    conflict_rows = 0
    for period, points in acled.groupby("period", sort=True):
        mask = month.eq(period)
        if not mask.any():
            continue
        idx = out.index[mask]; coords = out.loc[idx, ["lat", "lon"]].to_numpy(dtype=float)
        out.loc[idx, CONFLICT_COLUMNS] = np.nan
        valid = np.isfinite(coords).all(axis=1)
        point_coords = np.radians(points[["lat", "lon"]].to_numpy(dtype=float))
        # Bounded chunks preserve first-point ties without a large all-month matrix.
        for start in range(0, len(idx), 256):
            local = np.arange(start, min(start + 256, len(idx)))
            local = local[valid[local]]
            if not len(local):
                continue
            distance = haversine_distances(np.radians(coords[local]), point_coords) * 6371
            nearest = distance.argmin(axis=1); minimum = distance[np.arange(len(local)), nearest]
            accepted = minimum <= 500
            selected = idx[local[accepted]]
            out.loc[selected, CONFLICT_COLUMNS[:-1]] = points.iloc[nearest[accepted]][CONFLICT_COLUMNS[:-1]].to_numpy()
            out.loc[selected, "distance_to_nearest_acled"] = minimum[accepted]
        conflict_rows += int(mask.sum())
    changed = {}
    for col in WFP_COLUMNS + CONFLICT_COLUMNS:
        same = out[col].eq(frame[col]) | (out[col].isna() & frame[col].isna())
        changed[col] = {"changed_rows": int((~same).sum()), "missing_before": int(frame[col].isna().sum()), "missing_after": int(out[col].isna().sum())}
    preserved = [c for c in frame if c not in WFP_COLUMNS + CONFLICT_COLUMNS]
    pd.testing.assert_frame_equal(out[preserved], frame[preserved], check_exact=True)
    return out, {"rows": len(out), "wfp_covered_rows": int(covered.sum()),
                 "wfp_country_codes_resolved_from_name_rows": int(out.ISO3.isna().sum()) if "ISO3" in out else 0,
                 "acled_covered_rows": conflict_rows, "changed_columns": changed,
                 "non_source_columns_exactly_preserved": True}


def refresh(root: Path, fewsnet_panel: Path) -> None:
    inputs = root / "inputs"; inputs.mkdir(exist_ok=True)
    wfp, wfp_report = wfp_aggregates(root / "sources/wfp_data_7.22.26.csv")
    acled, acled_report = conflict_aggregates(root / "sources/ACLED Data_2026-07-22.csv")
    reports = {"wfp": wfp_report, "acled": acled_report, "inputs": {}}
    for system, source in [("fewsnet", fewsnet_panel), ("ipcch", ROOT / "Outcome/ipcch_unified/raw/IPCCH_2026_completed.csv"),
                            ("ipcch_april", ROOT / "Outcome/ipcch_unified/model_input/ipcch_monthly_base_input_202604.csv")]:
        print(f"Reading {system}", flush=True)
        before_hash = sha256(source)
        frame = pd.read_csv(source, low_memory=False, float_precision="round_trip",
                            dtype={"admin_code": "string", "area_id": "string"})
        frame = frame.loc[periods(frame) <= CUTOFF].reset_index(drop=True)
        refreshed, report = replace_sources(frame, wfp[system.split('_')[0]], acled)
        key = "FEWSNET_admin_code" if system == "fewsnet" else "admin_code"
        if pd.DataFrame({"id": refreshed[key], "month": periods(refreshed)}).duplicated().any():
            raise ValueError(f"duplicate {system} polygon-month")
        output = inputs / ("fewsnet_refreshed_raw.csv" if system == "fewsnet" else f"{system}_panel.csv")
        with output.open("x") as f:
            refreshed.to_csv(f, index=False)
        assert sha256(source) == before_hash, "baseline changed during read"
        report.update(source_path=str(source), source_sha256=before_hash, output_path=str(output.relative_to(root)), output_sha256=sha256(output))
        reports["inputs"][system] = report
        print(f"Saved {system}: {len(refreshed)} rows", flush=True)
        del frame, refreshed
    write_json(root / "reports/input_refresh.json", reports)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fewsnet-panel", type=Path, required=True)
    args = parser.parse_args()
    refresh(args.root, args.fewsnet_panel)
