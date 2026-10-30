"""Retained-input semantics of the IPCCH v2 runtime (task 10-29) over ``stores.VersionedTable``.

* Monthly series (climate ensembles, GPP_mean, nightlight_mean, WFP_Price): ``append_months`` saves new
  (admin_code, month) keys only. A saved value is never rewritten (R8), including when another provider arrives later;
  reruns compute only unsaved months (R41/R43). The single exception is GPP (R9): a month the availability ledger records
  as ``unpublished`` may later be filled where the saved value is missing - never where a value exists.
* GPP availability ledger (R49): only a definitive not-found (HTTP 404 or absence from the authoritative listing) is
  ``unpublished``; timeouts, 5xx, read/decompression errors and checksum mismatches are processing failures that block.
* Research-prepared families (R59): refresh replaces exactly the declared [start, end] months and preserves everything
  outside; every refresh row must lie inside the declared interval; keep changes nothing; coverage end is reported.
* Reported-phase history snapshot (R62/FCC8): refresh replaces the whole snapshot atomically (records absent from the
  replacement are removed); its preparation cutoff expresses coverage; a cutoff before O is a warning, not a block.
A refused refresh raises before any write, so retained history is unchanged (R27)."""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from cloud.ipcch.stores import StoreError, VersionedTable

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SERIES_COLUMNS = ("admin_code", "month", "value", "method_id")
GPP_LEDGER_COLUMNS = ("month", "status", "checked_at", "evidence")
SNAPSHOT_COLUMNS = ("area_id", "report_month", "phase", "availability_month", "preparation_cutoff")


class GppProcessingFailure(RuntimeError):
    """A GPP retrieval outcome that is not a definitive not-found: blocks IPCCH generation (R49)."""


def strict_csv(text: str, label: str, columns: tuple[str, ...] | None = None) -> pd.DataFrame:
    """A refresh/batch CSV as text cells, refusing (before any write) a header other than ``columns`` and any ragged row:
    pandas would otherwise silently re-align a row with one extra field as an index, or pad a short row."""
    import csv
    import io
    records = list(csv.reader(io.StringIO(text)))
    if not records:
        raise StoreError(f"{label}: empty file")
    header = records[0]
    if columns is not None and tuple(header) != tuple(columns):
        raise StoreError(f"{label}: columns must be exactly {', '.join(columns)} (got {header})")
    if len(set(header)) != len(header):
        raise StoreError(f"{label}: duplicate column names")
    bad = [i for i, r in enumerate(records[1:], start=2) if len(r) != len(header)]
    if bad:
        raise StoreError(f"{label}: {len(bad)} ragged rows (e.g. line {bad[0]}) do not match the {len(header)}-field header")
    return pd.DataFrame(records[1:], columns=header, dtype=object)


def require_initialised(table: VersionedTable) -> None:
    """An accepted history exists iff its HEAD exists - an empty but committed table is initialised (R45)."""
    if table.head()[0] is None:
        raise StoreError(f"{table.table} is not initialised (R45)")


def _months(values: Iterable[Any], label: str) -> None:
    bad = sorted({str(v) for v in values if not isinstance(v, str) or _MONTH.fullmatch(v) is None})
    if bad:
        raise StoreError(f"{label}: months must be YYYY-MM: {bad[:5]}")


def _unique(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    dup = frame.duplicated(keys, keep=False)
    if dup.any():
        raise StoreError(f"{label}: duplicate keys {frame.loc[dup, keys].drop_duplicates().head(5).to_dict('records')}")


def _roster(frame: pd.DataFrame, roster: set[str], label: str) -> None:
    unknown = sorted(set(frame["admin_code"]) - roster)
    if unknown:
        raise StoreError(f"{label}: unknown modeled-area identifiers {unknown[:5]} (fixed roster, R32)")


# --------------------------------------------------------------------------- monthly series


def read_series(table: VersionedTable) -> tuple[pd.DataFrame, str]:
    """(series, HEAD generation) of one consistent snapshot; commits CAS from exactly this generation."""
    frame, _, generation = table.read({"admin_code": str, "month": str, "method_id": str})
    if frame is None:
        frame = pd.DataFrame({c: pd.Series(dtype="float64" if c == "value" else "object") for c in SERIES_COLUMNS})
    return frame, generation


def append_months(table: VersionedTable, new: pd.DataFrame, *, method_id: str, roster: set[str],
                  gpp_unpublished_months: set[str] | None = None) -> dict[str, Any]:
    """Save new monthly values; refuse any attempt to rewrite a saved value (R8). ``gpp_unpublished_months`` (GPP only)
    lists ledger-unpublished months whose saved missing values may be filled (R9)."""
    label = table.table
    if set(new.columns) - {"admin_code", "month", "value"} or not {"admin_code", "month", "value"} <= set(new.columns):
        raise StoreError(f"{label}: new rows need exactly admin_code, month, value")
    new = new.assign(admin_code=new["admin_code"].astype(str), value=pd.to_numeric(new["value"], errors="raise"))
    if not np.isfinite(new["value"].dropna().to_numpy()).all():
        raise StoreError(f"{label}: infinite values")
    _months(new["month"], label)
    _unique(new, ["admin_code", "month"], label)
    _roster(new, roster, label)
    old, generation = read_series(table)
    merged = old.merge(new, on=["admin_code", "month"], how="inner", suffixes=("_old", ""))
    fill_keys = pd.DataFrame(columns=["admin_code", "month"])
    if len(merged):
        allowed = (merged["value_old"].isna() & merged["month"].isin(gpp_unpublished_months or set()))
        if not allowed.all():
            bad = merged.loc[~allowed, ["admin_code", "month"]].head(5).to_dict("records")
            raise StoreError(f"{label}: saved values are never rewritten (R8/R9): {bad}")
        fill_keys = merged[["admin_code", "month"]]
    keep_old = old.merge(fill_keys, on=["admin_code", "month"], how="left", indicator=True)
    keep_old = keep_old[keep_old["_merge"] == "left_only"].drop(columns="_merge")
    added = new.assign(method_id=method_id)
    frame = pd.concat([keep_old, added], ignore_index=True)[list(SERIES_COLUMNS)].sort_values(
        ["month", "admin_code"], kind="mergesort").reset_index(drop=True)
    record = {"method_id": method_id, "rows_added": int(len(new) - len(fill_keys)), "filled_unpublished": int(len(fill_keys)),
              "months": sorted(set(new["month"]))}
    return table.commit(frame, record, expected_generation=generation)


def saved_months(table: VersionedTable) -> set[str]:
    frame, _ = read_series(table)
    return set(frame["month"])


# --------------------------------------------------------------------------- GPP availability ledger


def classify_gpp_probe(*, http_status: int | None = None, listed: bool | None = None, error: str | None = None) -> str:
    """``published`` | ``unpublished``; anything that is not a definitive outcome raises (R49)."""
    if error is not None:
        raise GppProcessingFailure(f"GPP retrieval failed ({error}); a processing failure, not unpublished")
    if http_status is not None and http_status not in (200, 404):
        raise GppProcessingFailure(f"GPP retrieval returned HTTP {http_status}: a processing failure whatever the listing")
    if (http_status == 404 and listed is True) or (http_status == 200 and listed is False):
        raise GppProcessingFailure(f"contradictory GPP probe: HTTP {http_status} with listed={listed}")
    if http_status == 404 or (http_status is None and listed is False):
        return "unpublished"
    if http_status == 200 or (http_status is None and listed is True):
        return "published"
    raise GppProcessingFailure(f"GPP probe outcome http={http_status} listed={listed} is not definitive")


def record_gpp_checks(table: VersionedTable, checks: list[Mapping[str, Any]]) -> dict[str, Any]:
    frame, _, generation = table.read({"month": str, "status": str})
    new = pd.DataFrame(checks, columns=list(GPP_LEDGER_COLUMNS))
    _months(new["month"], table.table)
    if not new["status"].isin(["published", "unpublished"]).all():
        raise StoreError("GPP ledger status must be published or unpublished")
    frame = new if frame is None else pd.concat([frame, new], ignore_index=True)
    return table.commit(frame, {"checks": len(new)}, expected_generation=generation)


def latest_gpp_status(table: VersionedTable) -> dict[str, str]:
    frame, _, _ = table.read({"month": str, "status": str})
    if frame is None:
        return {}
    return frame.drop_duplicates("month", keep="last").set_index("month")["status"].to_dict()


# --------------------------------------------------------------------------- research-prepared families (R59)


def refresh_interval(table: VersionedTable, new: pd.DataFrame, *, start: str, end: str, roster: set[str],
                     source_ref: Mapping[str, str]) -> dict[str, Any]:
    """Replace exactly months [start, end] of a family with ``new`` (admin_code, month, value); keep the rest."""
    label = table.table
    _months([start, end], label)
    if start > end:
        raise StoreError(f"{label}: declared interval is reversed")
    if list(new.columns) != ["admin_code", "month", "value"]:
        raise StoreError(f"{label}: refresh rows need exactly admin_code, month, value")
    new = new.assign(admin_code=new["admin_code"].astype(str), value=pd.to_numeric(new["value"], errors="raise"))
    _months(new["month"], label)
    outside = new[(new["month"] < start) | (new["month"] > end)]
    if len(outside):
        raise StoreError(f"{label}: {len(outside)} refresh rows lie outside the declared interval {start}..{end}")
    if not np.isfinite(new["value"].dropna().to_numpy()).all():
        raise StoreError(f"{label}: infinite values")
    _unique(new, ["admin_code", "month"], label)
    _roster(new, roster, label)
    old, generation = read_series(table)
    kept = old[(old["month"] < start) | (old["month"] > end)]
    frame = pd.concat([kept, new.assign(method_id=f"refresh:{source_ref.get('sha256', '')[:16]}")], ignore_index=True)
    frame = frame[list(SERIES_COLUMNS)].sort_values(["month", "admin_code"], kind="mergesort").reset_index(drop=True)
    record = {"action": "refresh", "start": start, "end": end, "source": dict(source_ref),
              "replaced_rows": int(len(old) - len(kept)), "rows": int(len(new)), "coverage_end": coverage_end(frame)}
    return table.commit(frame, record, expected_generation=generation)


def coverage_end(frame: pd.DataFrame) -> str | None:
    present = frame.loc[frame["value"].notna(), "month"]
    return None if present.empty else str(present.max())


# --------------------------------------------------------------------------- reported-phase history snapshot (R62)


def validate_snapshot(snapshot: pd.DataFrame, label: str) -> tuple[pd.DataFrame, str]:
    """(validated snapshot, its single preparation cutoff): the rules shared by refresh and initialisation (R62)."""
    if list(snapshot.columns) != list(SNAPSHOT_COLUMNS):
        raise StoreError(f"{label}: snapshot columns must be exactly {SNAPSHOT_COLUMNS}")
    snap = snapshot.assign(area_id=snapshot["area_id"].astype(str))
    for c in ("report_month", "availability_month", "preparation_cutoff"):
        _months(snap[c], f"{label}.{c}")
    cutoffs = set(snap["preparation_cutoff"])
    if len(cutoffs) != 1:
        raise StoreError(f"{label}: one preparation cutoff per snapshot, got {sorted(cutoffs)[:5]}")
    cutoff = cutoffs.pop()
    if (snap["report_month"] > cutoff).any() or (snap["availability_month"] > cutoff).any():
        raise StoreError(f"{label}: records after the preparation cutoff {cutoff}")
    phase = pd.to_numeric(snap["phase"], errors="raise")
    if not phase.isin([1, 2, 3, 4, 5]).all():
        raise StoreError(f"{label}: phases must be 1..5")
    _unique(snap, ["area_id", "report_month"], label)
    return snap, cutoff


def snapshot_record(action: str, snap: pd.DataFrame, cutoff: str, source_ref: Mapping[str, Any]) -> dict[str, Any]:
    """HEAD metadata of a saved snapshot; ``snapshot_warning`` reads its preparation cutoff."""
    return {"action": action, "preparation_cutoff": cutoff, "source": dict(source_ref), "rows": int(len(snap))}


def replace_snapshot(table: VersionedTable, snapshot: pd.DataFrame, *, source_ref: Mapping[str, str]) -> dict[str, Any]:
    """Atomic full replacement by a complete snapshot through its preparation cutoff (FCC8)."""
    snap, cutoff = validate_snapshot(snapshot, table.table)
    _, generation = table.head()
    return table.commit(snap, snapshot_record("refresh", snap, cutoff, source_ref), expected_generation=generation)


def snapshot_warning(head: Mapping[str, Any] | None, feature_origin: str) -> str | None:
    """R62: an older-than-O snapshot is a warning for the summary/metadata, never a block."""
    if head is None:
        return "no reported-phase history snapshot saved"
    cutoff = head["record"]["preparation_cutoff"]
    return None if cutoff >= feature_origin else f"reported-phase snapshot prepared through {cutoff}, before O {feature_origin}"
