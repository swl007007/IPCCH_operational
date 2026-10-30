"""IPCCH ``WFP_Price`` keep/refresh (task 10-29; R27-R29, R59 semantics, R64 as corrected by the Supervisor on 2026-10-30).

The trained ``WFP_Price`` is the research HDX series (``staging/ipcch-update-202610/tools/build_wfp_hdx.py``;
research/cp3/wfp-price-provenance.md): 100 + the year-on-year % change of local-currency staple prices from the nearest
market with data within 100 km of the area, per area-month, no fill. The operational WFP ``Trend`` country-mean
converter is a different source/definition and is NOT used for IPCCH (FEWS NET and the legacy entrypoint keep it).

* keep: the saved history is used unchanged (initial accepted history untouched).
* refresh ``{action, file, start, end}``: a research-prepared processed CSV ``admin_code, month, value`` produced by the
  existing research build, pinned by ``{uri, generation, sha256}`` and read by the caller; it replaces exactly the
  declared [start, end] months via ``retained.refresh_interval`` (rows outside the interval or the roster, duplicates,
  non-canonical months, unparseable text or infinities refuse the whole refresh before any write, so history stays
  intact, R27); a successful refresh becomes the keep baseline (R28). Months beyond coverage stay missing
  (optional-missing, R65); there is no carry-forward and no operational fetcher. An operator covers revisions of recent
  months (the research build's centred outlier filter) only by declaring them inside the interval.
"""

from __future__ import annotations

import io
import math
from typing import Any, Iterable, Mapping

import pandas as pd

from cloud.ipcch import retained
from cloud.ipcch.stores import StoreError, VersionedTable

HISTORY_TABLE = "history__WFP_Price"
METHOD = ("research HDX food prices: 100 + YoY % change of local-currency staple prices (maize, sorghum, rice, wheat, "
          "vegetable oil), nearest market with data < 100 km, no fill (build_wfp_hdx.py)")


def parse_refresh(text: str, label: str = "ipcch.wfp refresh") -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    if list(raw.columns) != ["admin_code", "month", "value"]:
        raise StoreError(f"{label}: columns must be exactly admin_code, month, value (got {list(raw.columns)})")
    values = []
    for area, v in zip(raw["admin_code"], raw["value"]):
        s = v.strip()
        if s == "" or s.lower() == "nan":
            values.append(math.nan)
            continue
        try:
            x = float(s)
        except ValueError:
            raise StoreError(f"{label}: unparseable value {v!r} for area {area}") from None
        if math.isinf(x):
            raise StoreError(f"{label}: infinite value for area {area}")
        values.append(x)
    if not raw["admin_code"].str.fullmatch(r"\d+").all():
        raise StoreError(f"{label}: admin_code must be integral identifiers")
    return pd.DataFrame({"admin_code": raw["admin_code"], "month": raw["month"], "value": values})


def apply(store, root, choice: Mapping[str, Any], *, roster: Iterable[Any], text: str | None = None) -> dict[str, Any]:
    """Keep or refresh the retained WFP_Price history; returns the batch-report entry (method, provenance, coverage)."""
    table = VersionedTable(store, root, HISTORY_TABLE)
    frame, _ = retained.read_series(table)
    if frame.empty:
        raise StoreError(f"{HISTORY_TABLE} is not initialised (R45)")
    if choice["action"] == "keep":
        return {"action": "keep", "method": METHOD, "coverage_end": retained.coverage_end(frame)}
    if text is None:
        raise StoreError("a WFP refresh needs the pinned processed file content")
    rows = parse_refresh(text)
    head = retained.refresh_interval(table, rows, start=choice["start"], end=choice["end"],
                                     roster={str(a) for a in roster}, source_ref=choice["file"])
    return {"action": "refresh", "method": METHOD, "source": dict(choice["file"]), "interval": [choice["start"], choice["end"]],
            "replaced_rows": head["record"]["replaced_rows"], "rows": head["record"]["rows"],
            "coverage_end": head["record"]["coverage_end"]}
