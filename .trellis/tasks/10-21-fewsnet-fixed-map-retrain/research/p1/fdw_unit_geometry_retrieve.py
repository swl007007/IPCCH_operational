"""Retrieve FEWS NET CS unit geometry (per fnid) from the official FDW host for the crosswalk.

The HDX-registered CS resources are CSV tables without geometry, and the registered GeoJSON
maps are dissolved by phase. Geometry for each reported geographic unit therefore comes from
the same official FDW host's `ipcphase.geojson` endpoint, one request per reporting month.
These files are crosswalk evidence only; labels still come from the frozen HDX CSV freeze.

Usage: python fdw_unit_geometry_retrieve.py --out <staging>/fdw-geometry/<id> --months 2026-06 ...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from hdx_cs_retrieve import USER_AGENT, download, utc_now, write_json

BASE = "https://fdw.fews.net/api/ipcphase.geojson"


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = map(int, month.split("-"))
    nxt = f"{year + 1}-01" if mon == 12 else f"{year}-{mon + 1:02d}"
    return f"{month}-01", f"{nxt}-01"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--months", required=True, nargs="+")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    receipt: dict[str, object] = {"retrieval_id": args.out.name, "started_utc": utc_now(),
                                  "purpose": "crosswalk geometry evidence only", "months": {}}
    for month in args.months:
        start, end = month_bounds(month)
        url = (f"{BASE}?scenario=CS&preference=best&start_date={start}&end_date={end}")
        record = download(session, url, args.out / f"CS_{month}.geojson")
        receipt["months"][month] = record
        print(month, record.get("complete"), record.get("size_bytes"), flush=True)
    receipt["completed_utc"] = utc_now()
    write_json(args.out / "retrieval_receipt.json", receipt)


if __name__ == "__main__":
    main()
