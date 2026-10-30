"""IPCCH GOSIF-GPP v3 monthly append with the availability ledger (task 10-29; R9, R49, R54, R57, R65).

Units and missingness must match the delivered ``GPP_mean`` history (research task 10-27,
``staging/ipcch-gosif-v3-20261027/tools/extract_gpp_v3.py:5-8,31-32,123-133``; research/cp3/gpp-v3-units.md):

    GPP_mean[p, m] = sum(x_c for member cells c if x_c not in {65534, 65535}) / n_valid * 0.01     (g C m-2 month-1)

members = cells whose centre lies in the polygon (``rasterio.mask`` all_touched=False, one polygon at a time,
unweighted); true zeros are valid; ``n_valid == 0`` (no member cell, or only fill cells) -> NaN (per-area pixel
missingness, R49), never a fallback. The raster must be the provider's uint16 EPSG:4326 3600x7200 0.05-degree grid
with nodata unset or a fill code. This is an IPCCH-only adapter: the shared ``remote_sources`` contract (raw zonal
statistics, used by FEWS NET and the legacy entrypoint) is unchanged; acquisition reuses the existing v3 URL contract,
``CloudSourceAcquirer._head`` and ``_acquire_http`` (create-only retained copy, sha256).

``update_gpp``: candidates are every month after the last saved history month through O, plus months the ledger last
recorded as ``unpublished`` (R9 fill-only-unpublished). Per month: HEAD 200 -> download, extract, append the roster's
values immediately (saved values are never rewritten; NaN rows record pixel missingness) and record ``published``;
if that ledger write is interrupted, the adapter's saved rows (their ``method_id``) are the authoritative evidence on
retry: the ledger is repaired to ``published`` without re-fetching, so saved no-valid-pixel NaN rows are never filled;
404 -> ledger ``unpublished`` (the month stays absent, GPP is optional-missing, R65); anything else -> a
``GppProcessingFailure`` that blocks generation (R49) after the months already saved.
"""

from __future__ import annotations

import json
import math
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from cloud.batch import remote_sources as rs
from cloud.ipcch import retained
from cloud.ipcch.retained import GppProcessingFailure
from cloud.ipcch.stores import StoreError, VersionedTable

FILLS = (65534, 65535)
SCALE = 0.01
GRID = (3600, 7200, (0.05, 0.0, -180.0, 0.0, -0.05, 90.0))
FAMILY = "gosif_mean"
HISTORY_TABLE = "history__GPP_mean"
LEDGER_TABLE = "gpp_availability_ledger"
METHOD_ID = "gosif-gpp-v3-mean|fills65534,65535-masked|sum/n_valid*0.01|cell-centre-unweighted|research-10-27"


def zonal_gpp_mean(raster_path: str, geometries: Mapping[str, dict], *, grid=GRID) -> pd.DataFrame:
    """admin_code, value, n_valid, n_fill, n_zero for each geometry (research formula; see module docstring)."""
    import rasterio
    from rasterio.mask import mask

    rows = []
    with rasterio.open(raster_path) as ds:
        transform = tuple(ds.transform)[:6]
        if ds.count != 1 or ds.dtypes[0] != "uint16" or ds.crs is None or ds.crs.to_string() != "EPSG:4326" \
                or (ds.height, ds.width) != grid[:2] or not np.allclose(transform, grid[2], rtol=0, atol=1e-9):
            raise GppProcessingFailure(f"{raster_path}: not the GOSIF v3 uint16 EPSG:4326 grid {grid[:2]} "
                                       f"(got {ds.count} band(s) {ds.dtypes} {ds.crs} {ds.height}x{ds.width} {transform})")
        if ds.nodata is not None and ds.nodata not in FILLS:
            raise GppProcessingFailure(f"{raster_path}: unexpected nodata {ds.nodata}")
        for key, geometry in geometries.items():
            try:
                data, _ = mask(ds, [geometry], crop=True, all_touched=False, filled=False, indexes=1)
                x = np.ma.compressed(data).astype(np.int64)
            except ValueError as exc:
                if "overlap" not in str(exc).lower():
                    raise
                x = np.array([], dtype=np.int64)
            fill = np.isin(x, FILLS)
            valid = x[~fill]
            n = int(valid.size)
            value = float(valid.astype(np.float64).sum()) / n * SCALE if n else math.nan
            rows.append({"admin_code": str(key), "value": value, "n_valid": n, "n_fill": int(fill.sum()),
                         "n_zero": int((valid == 0).sum())})
    return pd.DataFrame(rows, columns=["admin_code", "value", "n_valid", "n_fill", "n_zero"])


def _probe(acquirer, url: str) -> str:
    try:
        status = acquirer._head(url)
    except Exception as exc:
        return retained.classify_gpp_probe(error=f"{type(exc).__name__}: {exc}")
    return retained.classify_gpp_probe(http_status=status)


def update_gpp(store, root, *, origin: str, roster: Iterable[str], geometries: Mapping[str, dict], acquirer,
               run_id: str, workdir, checked_at: str, grid=GRID) -> dict[str, Any]:
    roster = [str(a) for a in roster]
    if list(geometries) != roster:
        raise StoreError("GPP geometries must be exactly the roster in roster order (geography.roster_geometries)")
    history, ledger = VersionedTable(store, root, HISTORY_TABLE), VersionedTable(store, root, LEDGER_TABLE)
    frame, _ = retained.read_series(history)
    if frame.empty:
        raise StoreError(f"{HISTORY_TABLE} is not initialised (R45/R54)")
    status = retained.latest_gpp_status(ledger)
    unpublished = {m for m, s in status.items() if s == "unpublished"}
    adapter_months = set(frame.loc[frame["method_id"] == METHOD_ID, "month"])
    unledgered = {m for m in adapter_months if status.get(m) != "published"}      # interrupted ledger writes
    candidates = sorted(set(rs.months_between(max(frame["month"]), origin)) | {m for m in unpublished if m <= origin}
                        | unledgered)
    first = rs.SOURCE_CONTRACTS[FAMILY].first_month
    if candidates and candidates[0] < first:
        raise GppProcessingFailure(f"GPP months {candidates[0]}.. precede the v3 contract start {first}")
    template = rs.SOURCE_CONTRACTS[FAMILY].export["url"]
    report: dict[str, Any] = {"method_id": METHOD_ID, "origin": origin, "candidates": candidates, "saved": [],
                              "unpublished": [], "pixel_missing": {}}
    for month in candidates:
        url = rs.gosif_url(template, month)
        adapter_rows = frame[(frame["month"] == month) & (frame["method_id"] == METHOD_ID)]
        if len(adapter_rows):
            # Authoritative evidence that this month was published and saved (incl. no-valid-pixel NaN rows) by an
            # earlier run whose ledger write did not complete: repair the ledger, never re-fetch or overwrite (R8/R9).
            if status.get(month) != "published":
                retained.record_gpp_checks(ledger, [{"month": month, "status": "published", "checked_at": checked_at,
                                                     "evidence": json.dumps({"url": url, "repaired_from": "saved adapter rows",
                                                                             "rows": int(len(adapter_rows))})}])
                report.setdefault("ledger_repaired", []).append(month)
            continue
        try:
            outcome = _probe(acquirer, url)
        except GppProcessingFailure as exc:
            exc.gpp_report = report
            raise
        if outcome == "unpublished":
            retained.record_gpp_checks(ledger, [{"month": month, "status": "unpublished", "checked_at": checked_at,
                                                 "evidence": json.dumps({"url": url, "http": 404})}])
            report["unpublished"].append(month)
            continue
        try:
            raster = acquirer._acquire_http(FAMILY, month, url, run_id, workdir)
            values = zonal_gpp_mean(raster.path, geometries, grid=grid)
        except GppProcessingFailure as exc:
            exc.gpp_report = report
            raise
        except Exception as exc:                      # download/decompression/read errors block (R49)
            err = GppProcessingFailure(f"GPP {month}: {type(exc).__name__}: {exc}")
            err.gpp_report = report
            raise err from exc
        saved = frame[(frame["month"] == month) & (frame["value"].notna() | (frame["method_id"] == METHOD_ID))]["admin_code"]
        new = values.loc[~values["admin_code"].isin(set(saved)), ["admin_code", "value"]].assign(month=month)
        retained.append_months(history, new, method_id=METHOD_ID, roster=set(roster), gpp_unpublished_months=unpublished)
        retained.record_gpp_checks(ledger, [{"month": month, "status": "published", "checked_at": checked_at,
                                             "evidence": json.dumps({"url": url, **raster.source}, sort_keys=True)}])
        frame, _ = retained.read_series(history)
        report["saved"].append(month)
        report["pixel_missing"][month] = int(values["value"].isna().sum())
    finite = frame[frame["value"].notna()]
    report["coverage_end"] = max(finite["month"]) if len(finite) else None
    return report
