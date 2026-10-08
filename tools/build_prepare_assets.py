"""Export pinned preparation assets for one system from existing accepted inputs.

Reuses fixed assets as-is (user instruction 2026-10-07): the repository native
geometry (explicit ``admin_code``) and the accepted September input panel. Each
consumed remote family's history is written in the current extraction layout
``admin_code, month, {band}__{reducer}`` by inverting ``MODEL_COLUMN_MAPPING``;
statistics the system's panel does not carry stay blank. Panel values are copied,
not reinterpreted: preparation applies the provider-vintage boundary, so filled
rows after the provider's latest month never become observations.

    python tools/build_prepare_assets.py --system ipcch \
        --geometry Outcome/ipcch_unified/spatial/ipcch_admin_geometry.shp \
        --panel .../inputs/ipcch_panel.csv --limit-month 2026-04 --out-dir /tmp/assets/ipcch
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud.batch.remote_sources import (  # noqa: E402
    MODEL_COLUMN_MAPPING,
    NATIVE_KEY,
    SOURCE_CONTRACTS,
    SYSTEM_FAMILIES,
)
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code  # noqa: E402

PANEL_KEYS = {
    # FEWSNET panel identity is FEWSNET_admin_code normalized exactly as the FEWS pipeline does.
    "fewsnet": {"id": "FEWSNET_admin_code", "time": ["date"]},
    "ipcch": {"id": "admin_code", "time": ["year", "month"]},
}


def family_columns(family: str) -> list[str]:
    contract = SOURCE_CONTRACTS[family]
    return [f"{band}__{reducer}" for band in contract.bands for reducer in contract.reducers]


def panel_usecols(system: str) -> list[str]:
    keys = PANEL_KEYS[system]
    return [keys["id"], *keys["time"], *MODEL_COLUMN_MAPPING[system]]


def history_snapshots(panel: pd.DataFrame, system: str, *, roster: list[str], limit_month: str,
                      since_month: str | None = None) -> dict[str, pd.DataFrame]:
    """Per consumed family: current-layout history from the system panel, since <= months <= limit."""
    keys = PANEL_KEYS[system]
    ids = panel[keys["id"]].map(normalize_admin_code) if system == "fewsnet" else panel[keys["id"]].astype(str)
    if ids.eq("").any():
        raise ValueError(f"{system} panel has blank native IDs")
    if system == "fewsnet":
        months = pd.to_datetime(panel["date"], format="%Y-%m-%d").dt.strftime("%Y-%m")
    else:
        months = panel["year"].astype(int).astype(str).str.zfill(4) + "-" + panel["month"].astype(int).astype(str).str.zfill(2)
    unknown = sorted(set(ids) - set(roster))
    if unknown:
        raise ValueError(f"{system} panel IDs outside the roster: {unknown[:5]}")
    keyed = pd.DataFrame({NATIVE_KEY: ids, "month": months})
    if keyed.duplicated().any():
        raise ValueError(f"{system} panel has duplicate admin_code-month rows")
    inverse = {stat: column for column, stat in MODEL_COLUMN_MAPPING[system].items()}
    selected = keyed["month"] <= limit_month
    if since_month:
        selected &= keyed["month"] >= since_month
    snapshots = {}
    for family in SYSTEM_FAMILIES[system]:
        frame = keyed.loc[selected].copy()
        for stat in family_columns(family):
            frame[stat] = pd.to_numeric(panel.loc[selected, inverse[stat]], errors="raise") if stat in inverse else float("nan")
        snapshots[family] = frame.sort_values([NATIVE_KEY, "month"]).reset_index(drop=True)
    return snapshots


def native_geometry(path: str | Path, system: str):
    import geopandas as gpd

    frame = gpd.read_file(path)
    if NATIVE_KEY not in frame:
        raise ValueError(f"{path} lacks {NATIVE_KEY}")
    if frame.crs is None:
        # A missing .prj must not be relabelled geographic; projected coordinates would be misplaced.
        raise ValueError(f"{path} has no CRS")
    frame = frame.to_crs("EPSG:4326") if frame.crs.to_epsg() != 4326 else frame
    codes = frame[NATIVE_KEY].map(normalize_admin_code) if system == "fewsnet" else frame[NATIVE_KEY].astype(str)
    if codes.eq("").any() or codes.duplicated().any():
        raise ValueError(f"{path} {NATIVE_KEY} must be unique and non-blank")
    return gpd.GeoDataFrame({NATIVE_KEY: codes}, geometry=frame.geometry, crs="EPSG:4326")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--system", choices=sorted(PANEL_KEYS), required=True)
    parser.add_argument("--geometry", required=True)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--limit-month", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--admin-codes", help="comma-separated subset for a bounded smoke run")
    parser.add_argument("--since-month", help="first history month kept (prepare baseline only needs recent months)")
    args = parser.parse_args(argv)

    geometry = native_geometry(args.geometry, args.system)
    if args.admin_codes:
        subset = args.admin_codes.split(",")
        missing = sorted(set(subset) - set(geometry[NATIVE_KEY]))
        if missing:
            raise ValueError(f"subset IDs not in geometry: {missing}")
        geometry = geometry.loc[geometry[NATIVE_KEY].isin(subset)]
    roster = geometry[NATIVE_KEY].tolist()
    panel = pd.read_csv(args.panel, usecols=panel_usecols(args.system), low_memory=False,
                        dtype={PANEL_KEYS[args.system]["id"]: str})
    if args.admin_codes:
        ids = panel[PANEL_KEYS[args.system]["id"]]
        ids = ids.map(normalize_admin_code) if args.system == "fewsnet" else ids.astype(str)
        panel = panel.loc[ids.isin(roster)]
    snapshots = history_snapshots(panel, args.system, roster=roster, limit_month=args.limit_month,
                                  since_month=args.since_month)

    out = Path(args.out_dir)
    (out / "history").mkdir(parents=True, exist_ok=False)
    pd.DataFrame({NATIVE_KEY: roster}).to_csv(out / "roster.csv", index=False, lineterminator="\n")
    (out / "geometry.geojson").write_text(geometry.to_json(drop_id=True), encoding="utf-8")
    summary = {"system": args.system, "areas": len(roster), "families": {}}
    for family, frame in snapshots.items():
        frame.to_csv(out / "history" / f"{family}.csv", index=False, lineterminator="\n")
        values = frame[family_columns(family)]
        observed = frame.loc[values.notna().any(axis=1), "month"]
        summary["families"][family] = {"rows": len(frame), "last_month_with_values": observed.max() if len(observed) else None}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
