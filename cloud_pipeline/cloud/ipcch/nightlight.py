"""IPCCH ``nightlight_mean`` monthly append through the existing VIIRS export/zonal contract (task 10-29; R32, R43, R64,
R65).

The delivered history equals the operational contract's ``avg_rad__sum`` (``remote_sources.MODEL_COLUMN_MAPPING
["ipcch"]["nightlight_mean"]``): on 124,516 shared non-zero keys (2024-01..2026-04) 97.0% are bit-equal and the ratio
quantiles (5/50/95%) are all 1.0 (research/cp3/nightlight-contract-check, executor 2026-10-30). New months therefore use
the shared contract unchanged: ``CloudSourceAcquirer.published_months`` (one image per month), ``start_exports`` (all
months submitted, cancelled together on a submission failure), ``acquire`` (create-only retained shards, mosaic),
``remote_sources.zonal_statistics(family="viirs")`` on the fixed roster geometry (``geography.roster_geometries``).

Every month after the last saved month through O is attempted (R43). A month the collection does not publish stays
absent and is reported as a source-level gap; nightlight is optional-missing (R65), so O itself unpublished is a gap,
not a block. Retrieval/extraction errors are processing failures that block after the months already saved. Saved values
are never rewritten (R8).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

from cloud.batch import remote_sources as rs
from cloud.ipcch import retained
from cloud.ipcch.stores import StoreError, VersionedTable

FAMILY = "viirs"
HISTORY_TABLE = "history__nightlight_mean"
COLUMN = rs.MODEL_COLUMN_MAPPING["ipcch"]["nightlight_mean"]             # avg_rad__sum
METHOD_ID = f"viirs-dnb-monthly-vcmcfg|{rs.EXTRACTION_CONTRACT_VERSION}|{COLUMN}|cell-centre"


class NightlightProcessingFailure(RuntimeError):
    """A VIIRS retrieval/extraction failure (not unavailability): blocks IPCCH generation."""


def update_nightlight(store, root, *, origin: str, roster: Iterable[str], geometries: Mapping[str, dict], acquirer,
                      run_id: str, workdir) -> dict[str, Any]:
    roster = [str(a) for a in roster]
    if list(geometries) != roster:
        raise StoreError("nightlight geometries must be exactly the roster in roster order (geography.roster_geometries)")
    history = VersionedTable(store, root, HISTORY_TABLE)
    retained.require_initialised(history)
    frame, _ = retained.read_series(history)
    if frame.empty:                                     # append-only histories are never emptied; nothing to anchor on
        raise StoreError(f"{HISTORY_TABLE} holds no saved month to append after")
    candidates = rs.months_between(max(frame["month"]), origin)
    report: dict[str, Any] = {"method_id": METHOD_ID, "origin": origin, "candidates": candidates, "saved": [], "gaps": []}
    if not candidates:
        report["coverage_end"] = max(frame["month"])
        return report
    try:
        published = acquirer.published_months(FAMILY, start_month=candidates[0], end_month=origin)
        published = {m: i for m, i in published.items() if m in set(candidates)}
        acquirer.start_exports(FAMILY, published, prepare_id=run_id)
    except Exception as exc:
        err = NightlightProcessingFailure(f"VIIRS discovery/export submission failed: {type(exc).__name__}: {exc}")
        err.nightlight_report = report
        raise err from exc
    report["gaps"] = [m for m in candidates if m not in published]           # source-level gaps (R43), optional (R65)
    for month in sorted(published):
        try:
            raster = acquirer.acquire(FAMILY, month, provider_id=published[month], prepare_id=run_id, workdir=workdir)
            stats = rs.zonal_statistics(raster.path, geometries, family=FAMILY, month=month)
        except Exception as exc:
            cancelled = acquirer.cancel_started() if hasattr(acquirer, "cancel_started") else []
            err = NightlightProcessingFailure(f"VIIRS {month}: {type(exc).__name__}: {exc}; cancelled {cancelled}")
            err.nightlight_report = report
            raise err from exc
        if list(stats["admin_code"]) != roster:
            raise NightlightProcessingFailure(f"VIIRS {month}: zonal output is not the roster")
        new = pd.DataFrame({"admin_code": stats["admin_code"], "month": month, "value": stats[COLUMN]})
        retained.append_months(history, new, method_id=METHOD_ID, roster=set(roster))
        report["saved"].append(month)
        report.setdefault("pixel_missing", {})[month] = int(new["value"].isna().sum())
    frame, _ = retained.read_series(history)
    finite = frame[frame["value"].notna()]
    report["coverage_end"] = max(finite["month"]) if len(finite) else None
    return report
