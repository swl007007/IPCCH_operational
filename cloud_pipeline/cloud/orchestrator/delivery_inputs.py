"""Assemble fixed-origin model inputs for the October delivery (CP3).

Inputs per system: the accepted September input panel (fixed/history reuse), the
prepared remote snapshot (``prepared_manifest.json`` + ``features/{system}/*.csv``)
and the operator's ACLED/WFP choices (CP1 ``apply_source_choices``).

Order, per spec section 5: add calendar rows through O, apply the source-family
choices, overlay remote features honouring the provider vintage (history values for
months after the provider's latest completed month are not observations and are
cleared; prepared extractions replace history for their months), then fill base
predictor series from the same area's past only (CP1 ``carry_forward_base_series``).
Label/target-derived columns are never filled; calendar lags, rolling windows and
normalisation are recomputed downstream by the existing system code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from cloud.batch.remote_sources import MODEL_COLUMN_MAPPING, SOURCE_CONTRACTS, SYSTEM_FAMILIES
from cloud.orchestrator.causal_fill import carry_forward_base_series
from fewsnet_partitioned_rf_pipeline.core.data import normalize_admin_code
from tools.refresh_h5_inputs import apply_source_choices

KEY = "admin_code"
MONTH = "month_key"  # YYYY-MM calendar key added for assembly; system month columns are left as they are

# FEWSNET raw-panel columns that are identity, labels/target-derived or derived by normalisation.
FEWSNET_IDENTITY = ("unit_name", "ADMIN0", "ADMIN1", "ADMIN2", "ADMIN3", "FEWSNET_admin_code", "ISO", "ISO3",
                    "lat", "lon", "month", "date")
FEWSNET_LABELS = ("fews_ipc", "fews_ipc_crisis", "fews_ha", "fews_proj_near", "fews_proj_near_ha", "fews_proj_med",
                  "fews_proj_med_ha", "fews_ipc_adjusted", "fews_proj_med_adjusted")
FEWSNET_DERIVED = ("Tair_zscore", "Rainf_zscore")
FEWSNET_FILL_WINDOW_MONTHS = 12  # longest calendar dependency at O (EVI lag 12, prior-12 windows, zscore window)


def month_range(start: str, end: str) -> list[str]:
    periods = pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M")
    return [str(period) for period in periods]


def family_model_columns(system: str) -> dict[str, list[str]]:
    """Model/raw-panel columns fed by each consumed remote family."""
    bands = {family: set(contract.bands) for family, contract in SOURCE_CONTRACTS.items()}
    columns: dict[str, list[str]] = {family: [] for family in SYSTEM_FAMILIES[system]}
    for column, stat in MODEL_COLUMN_MAPPING[system].items():
        band = stat.split("__")[0]
        family = next(f for f in SYSTEM_FAMILIES[system] if band in bands[f])
        columns[family].append(column)
    return columns


def add_calendar_rows(frame: pd.DataFrame, *, through: str, carry: Sequence[str],
                      from_month: str | None = None) -> pd.DataFrame:
    """Complete each area's calendar from its first month (or ``from_month`` if earlier) through ``through``.

    Interior gaps and months after the last row are added (so calendar lags/windows
    see every dependency month); only ``carry`` identity columns are copied.
    """
    first = frame.groupby(KEY)[MONTH].min()
    present = frame.groupby(KEY)[MONTH].agg(set)
    latest_rows = frame.sort_values(MONTH).groupby(KEY, sort=False).tail(1).set_index(KEY)
    additions = []
    for area, area_first in first.items():
        start = min(area_first, from_month) if from_month else area_first
        months = [month for month in month_range(start, through) if month not in present[area]]
        if not months:
            continue
        identity = latest_rows.loc[area, list(carry)]
        block = pd.DataFrame({column: [identity[column]] * len(months) for column in carry})
        block[KEY] = area
        block[MONTH] = months
        additions.append(block)
    if not additions:
        return frame.copy()
    return pd.concat([frame, *additions], ignore_index=True).sort_values([KEY, MONTH], kind="mergesort").reset_index(drop=True)


def remote_overlay(frame: pd.DataFrame, *, system: str, families: Mapping[str, Mapping],
                   features: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Apply the prepared snapshot's provider vintage and extracted months to a keyed frame.

    ``families`` is ``prepared_manifest["families"]``; ``features[family]`` is that
    family's prepared CSV for this system (``admin_code, month, {band}__{reducer}``).
    Prepared months with no calendar row (e.g. a provider vintage older than an
    area's panel start) are real observations: they are returned separately as
    ``extra`` (``admin_code, month_key`` + model columns) rather than dropped.
    """
    out = frame.copy()
    keys_index = pd.MultiIndex.from_arrays([out[KEY], out[MONTH]])  # positional lookup, no re-indexed copies
    report = {}
    extras = []
    for family, columns in family_model_columns(system).items():
        vintage = families[family]["provider_latest_completed_month"]
        # Months after the vintage are not observations; months the preparation planned
        # (incl. an explicit refresh window) are replaced even where new cells are missing.
        planned = families[family].get("system_months", {}).get(system, [])
        beyond = (out[MONTH] > vintage) | out[MONTH].isin(planned)
        cleared = int(out.loc[beyond, columns].notna().any(axis=1).sum())
        out.loc[beyond, columns] = np.nan
        prepared = features.get(family)
        replaced = 0
        if prepared is not None and len(prepared):
            stats = {column: MODEL_COLUMN_MAPPING[system][column] for column in columns}
            values = prepared.rename(columns={"month": MONTH})[[KEY, MONTH, *stats.values()]]
            values = values.rename(columns={stat: column for column, stat in stats.items()})
            if values.duplicated([KEY, MONTH]).any():
                raise ValueError(f"{family}: duplicate prepared area-months")
            positions = keys_index.get_indexer(pd.MultiIndex.from_frame(values[[KEY, MONTH]]))
            inside = positions >= 0
            for column in columns:
                out.iloc[positions[inside], out.columns.get_loc(column)] = values.loc[inside, column].to_numpy()
            replaced = int(inside.sum())
            inside = pd.Series(inside, index=values.index)
            outside = int((~inside).sum())
            if outside:
                extras.append(values.loc[~inside, [KEY, MONTH, *columns]])
        else:
            outside = 0
        report[family] = {"provider_vintage": vintage, "history_rows_cleared_after_vintage_or_planned": cleared,
                          "prepared_rows_applied": replaced, "prepared_rows_outside_panel_calendar": outside}
    extra = (pd.concat(extras, ignore_index=True).groupby([KEY, MONTH], as_index=False).first()
             if extras else pd.DataFrame(columns=[KEY, MONTH]))
    return out, report, extra


def ipcch_base_series(panel: pd.DataFrame, *, origin: str, prepared_families: Mapping, prepared_features: Mapping,
                      wfp=None, acled=None) -> tuple[pd.DataFrame, dict]:
    """IPCCH monthly base series through O (raw observations only; no filling yet).

    Takes ownership of ``panel`` (modified in place) to bound peak memory.
    """
    frame = panel
    frame[KEY] = frame[KEY].astype(str)
    frame[MONTH] = frame["year"].astype(int).astype(str).str.zfill(4) + "-" + frame["month"].astype(int).astype(str).str.zfill(2)
    after_origin = int((frame[MONTH] > origin).sum())
    frame = frame.loc[frame[MONTH] <= origin].reset_index(drop=True)
    # Identity needed by the WFP/ACLED overlays (ISO3, or country_en when ISO3 is blank; coordinates).
    carry = [column for column in ("area_id", "lat", "lon", "ISO3", "country_en") if column in frame]
    frame = add_calendar_rows(frame, through=origin, carry=carry)
    frame["year"] = frame[MONTH].str[:4].astype(int)
    frame["month"] = frame[MONTH].str[5:].astype(int)
    frame, choices = _source_choices(frame, "ipcch", wfp, acled)
    frame, overlay, extra = remote_overlay(frame, system="ipcch", families=prepared_families, features=prepared_features)
    overlay["rows_after_origin_dropped"] = after_origin
    if len(extra):  # older provider observations join the area's observation series
        frame = pd.concat([frame, extra], ignore_index=True).sort_values([KEY, MONTH], kind="mergesort").reset_index(drop=True)
    return frame, {"source_choices": _jsonable(choices), "remote_overlay": overlay}


def ipcch_origin_rows(base: pd.DataFrame, template: pd.DataFrame, *, origin: str, feature_columns: Sequence[str],
                      source_ref: Mapping[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """O rows: accepted template identity with each feature filled from its own area's past."""
    roster = template[KEY].astype(str).tolist()
    filled, audit = carry_forward_base_series(
        base[[KEY, MONTH, *feature_columns]], system="ipcch", id_column=KEY, month_column=MONTH,
        feature_columns=list(feature_columns), roster=roster, months=[origin], source_ref=source_ref)
    return _origin_rows(filled, template, origin=origin, feature_columns=feature_columns), audit


def _origin_rows(filled: pd.DataFrame, template: pd.DataFrame, *, origin: str,
                 feature_columns: Sequence[str]) -> pd.DataFrame:
    rows = template.copy()
    rows[KEY] = rows[KEY].astype(str)
    rows["year"], rows["month"] = int(origin[:4]), int(origin[5:])
    values = filled.set_index(KEY).loc[rows[KEY], list(feature_columns)].to_numpy()
    rows[list(feature_columns)] = values
    if "population_reference_period" in rows:
        # Output population provenance: each area's actual latest observation (estimate +
        # reference period) re-selected for O with the existing no-future builder.
        from model_pipeline.ipcch_launch_runtime.population import PopulationSnapshotBuilder

        builder = PopulationSnapshotBuilder(feature_year=int(origin[:4]), feature_month=int(origin[5:]))
        for area, period, value in zip(rows["area_id"], rows["population_reference_period"], rows["population_estimate"]):
            builder.add(area, int(str(period)[:4]), int(str(period)[5:7]), value)
        snapshot, _ = builder.build(rows["area_id"])
        for column in ("population_estimate", "population_reference_period", "population_imputation_method"):
            rows[column] = [snapshot[str(area).strip()][column] for area in rows["area_id"]]
    return rows


# --- Bounded-memory IPCCH assembly (memory only; identical semantics) -----------------------
# Every IPCCH base operation is area-local (calendar completion, source-choice row overlays,
# remote overlay per area-month, extras per area, own-past carry-forward), so the unchanged
# functions above run per contiguous sorted-area group. WFP/ACLED aggregation happens once,
# globally, before this (the caller passes the aggregated frames).


def _union_dtype(dtypes):
    """Whole-column dtype from per-chunk inferences, or None when only a whole-column re-read is exact."""
    kinds = list(dict.fromkeys(dtypes))
    if len(kinds) == 1:
        return kinds[0]
    # Only signed integers and floats widen to float64 as whole-column inference does; unsigned
    # mixes (and anything else) are decided by an exact whole-column re-read.
    signed = all(pd.api.types.is_float_dtype(d) or pd.api.types.is_signed_integer_dtype(d) for d in kinds)
    return np.dtype("float64") if signed else None


def _csv_records(path):
    """Exact raw text of each CSV record (quoted newlines kept inside their record)."""
    import csv

    with open(path, encoding="utf-8", newline="") as handle:
        pending = []

        def lines():
            for line in handle:
                pending.append(line)
                yield line

        for _ in csv.reader(lines()):
            yield "".join(pending)
            pending.clear()


def _merge_reports(left, right):
    """Combine per-group reports: counts add, equal labels stay, nested dicts merge; conflicts raise."""
    if left is None:
        return right
    if isinstance(left, dict) and isinstance(right, dict):
        return {key: (_merge_reports(left.get(key), right[key]) if key in right else left[key])
                for key in dict.fromkeys([*left, *right])} | {k: right[k] for k in right if k not in left}
    if isinstance(left, (int, np.integer)) and not isinstance(left, bool) and isinstance(right, (int, np.integer)):
        return int(left) + int(right)
    if left == right:
        return left
    raise ValueError(f"per-group reports disagree: {left!r} vs {right!r}")


def _month_keys(frame: pd.DataFrame) -> pd.Series:
    return frame["year"].astype(int).astype(str).str.zfill(4) + "-" + frame["month"].astype(int).astype(str).str.zfill(2)


def ipcch_assemble_chunked(panel_path, template: pd.DataFrame, *, origin: str, feature_columns: Sequence[str],
                           usecols: Sequence[str], prepared_families: Mapping, prepared_features: Mapping,
                           base_path, make_ref, work_dir, wfp=None, acled=None, groups: int = 8,
                           chunksize: int = 200_000) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    """Bounded-memory equivalent of ``ipcch_base_series`` (whole panel) + base CSV + ``ipcch_origin_rows``.

    Returns (O rows, base audit, assembly report, chunking report) and writes the base CSV
    byte-identically to the whole-panel path. ``make_ref(path)`` returns the CSV's immutable ref.
    """
    import heapq
    from pathlib import Path

    panel_path, base_path, work = Path(panel_path), Path(base_path), Path(work_dir)
    work.mkdir(parents=True, exist_ok=False)
    identity = {KEY: str, "area_id": str}  # exactly the whole-panel read's identity dtypes
    read = dict(usecols=list(usecols), dtype=identity)
    header = list(pd.read_csv(panel_path, nrows=0, **read).columns)
    # Pass A: per-chunk inference; columns whose chunks disagree non-numerically are re-read whole.
    seen, keys = {column: [] for column in header}, set()
    for chunk in pd.read_csv(panel_path, chunksize=chunksize, **read):
        for column in header:
            seen[column].append(chunk[column].dtype)
        keys.update(chunk[KEY].astype(str))
    final = {}
    for column in header:
        dtype = _union_dtype(seen[column]) if seen[column] else None
        if dtype is None:  # exact whole-column inference (e.g. numeric-looking text with leading zeros)
            dtype = pd.read_csv(panel_path, usecols=[column], low_memory=False,
                                dtype={k: v for k, v in identity.items() if k == column})[column].dtype
        final[column] = dtype
    prepared_keys = set()
    for frame in prepared_features.values():
        if frame is not None and len(frame):
            prepared_keys.update(frame[KEY].astype(str))
    universe = sorted(keys | prepared_keys | set(template[KEY].astype(str)))
    count = max(1, min(groups, len(universe)))
    group_of = {universe[i]: g for g, block in enumerate(np.array_split(np.arange(len(universe)), count)) for i in block}
    # Pass B: re-read with the final dtypes; spill each area group exactly (pickle) with source ordinals.
    parts = {g: [] for g in range(count)}
    offset = 0
    for index, chunk in enumerate(pd.read_csv(panel_path, chunksize=chunksize, usecols=list(usecols), dtype=final)):
        chunk["_row"] = np.arange(offset, offset + len(chunk), dtype="int64")
        offset += len(chunk)
        gid = chunk[KEY].astype(str).map(group_of).to_numpy()
        for g in np.unique(gid):
            path = work / f"panel_g{g}_p{index}.pkl"
            chunk.loc[gid == g].to_pickle(path)
            parts[int(g)].append(path)
        del chunk
    # Groups: unchanged base-series function on each group's areas.
    report, grew, columns, heads = None, {}, None, []
    for g in range(count):
        frame = (pd.concat([pd.read_pickle(path) for path in parts[g]], ignore_index=True) if parts[g] else
                 pd.DataFrame({column: pd.Series(dtype=final[column]) for column in header}).assign(
                     _row=pd.Series(dtype="int64")))
        within = int((_month_keys(frame) <= origin).sum()) if len(frame) else 0
        members = {key for key, value in group_of.items() if value == g}
        features = {family: (values.loc[values[KEY].astype(str).isin(members)]
                             if values is not None and len(values) else values)
                    for family, values in prepared_features.items()}
        base, part = ipcch_base_series(frame, origin=origin, prepared_families=prepared_families,
                                       prepared_features=features, wfp=wfp, acled=acled)
        del frame
        report = _merge_reports(report, part)
        grew[g] = len(base) > within  # calendar rows or extras were added, so the whole-panel path sorted
        if len(base):
            if columns is None:
                columns = list(base.columns)
            if list(base.columns) != columns:
                raise ValueError("per-group base series columns differ")
            heads.append(base.iloc[:0])
        base.to_pickle(work / f"base_g{g}.pkl")
        del base
    # The whole-panel path concatenates these pieces; pandas' concat common type (independent
    # of values, so empty heads give it exactly) is therefore the whole-path column dtype.
    out_dtypes = pd.concat(heads, ignore_index=True).dtypes.to_dict()
    written = [column for column in columns if column != "_row"]
    sorted_branch = any(grew.values())
    bodies = []
    for g in range(count):
        base = pd.read_pickle(work / f"base_g{g}.pkl")
        if not len(base):
            continue
        if sorted_branch and not grew[g]:  # restriction of the whole-panel stable (admin_code, month_key) sort
            base = base.sort_values([KEY, MONTH], kind="mergesort")
        body = work / f"body_g{g}.csv"
        base[written].astype({c: out_dtypes[c] for c in written}).to_csv(body, header=False, index=False,
                                                                          lineterminator="\n")
        bodies.append((body, None if sorted_branch else base["_row"].to_numpy(), len(base)))
        del base
    with base_path.open("w", encoding="utf-8", newline="") as target:
        target.write(pd.DataFrame(columns=written).to_csv(index=False, lineterminator="\n"))
        if sorted_branch:  # groups are contiguous sorted key ranges
            for body, _, _ in bodies:
                with body.open(encoding="utf-8", newline="") as handle:
                    target.writelines(handle)
        else:  # no row added anywhere: original row order, merged record-wise by source ordinal
            for body, _, size in bodies:
                if sum(1 for _ in _csv_records(body)) != size:
                    raise ValueError(f"{body.name}: CSV record count differs from its rows")
            streams = [zip(ordinals.tolist(), _csv_records(body)) for body, ordinals, _ in bodies]
            for _, record in heapq.merge(*streams, key=lambda item: item[0]):
                target.write(record)
    source_ref = make_ref(base_path)
    # Origin fill per group; audit order carried explicitly (feature-major, template roster order).
    roster = template[KEY].astype(str).tolist()
    # carry-forward converts each feature with pd.to_numeric, whose dtype is value-dependent. A feature
    # whose groups disagree beyond signed-int/float widening is filled once over the whole roster
    # (only its key/month/value columns in memory); every other feature is filled per group.
    kinds = {feature: set() for feature in feature_columns}
    for g in range(count):
        base = pd.read_pickle(work / f"base_g{g}.pkl")
        if len(base):
            for feature in feature_columns:
                kinds[feature].add(pd.to_numeric(base[feature], errors="raise").dtype)
        del base
    whole_numeric = [feature for feature, found in kinds.items() if len(found) > 1 and not all(
        pd.api.types.is_float_dtype(d) or pd.api.types.is_signed_integer_dtype(d) for d in found)]
    grouped = [feature for feature in feature_columns if feature not in whole_numeric]

    def fill(observations, members, features):
        return carry_forward_base_series(
            observations, system="ipcch", id_column=KEY, month_column=MONTH, feature_columns=features,
            roster=members, months=[origin], source_ref=source_ref)

    blocks = {}  # feature -> list of (members, audit rows for that feature in member order)
    filled_parts = []
    for g in range(count):
        members = [key for key in roster if group_of[key] == g]
        base = pd.read_pickle(work / f"base_g{g}.pkl")
        if not members and not len(base):
            continue
        observations = (base[[KEY, MONTH, *grouped]] if len(base) else pd.DataFrame(columns=[KEY, MONTH, *grouped]))
        del base
        filled, audit = fill(observations, members, grouped)
        del observations
        for index, feature in enumerate(grouped):
            blocks.setdefault(feature, []).append(audit.iloc[index * len(members):(index + 1) * len(members)])
        filled_parts.append(filled)
    filled = pd.concat(filled_parts, ignore_index=True).set_index(KEY).loc[roster].reset_index()
    for feature in whole_numeric:
        parts = [pd.read_pickle(work / f"base_g{g}.pkl")[[KEY, MONTH, feature]] for g in range(count)]
        values, audit = fill(pd.concat(parts, ignore_index=True), roster, [feature])
        filled[feature] = values[feature].to_numpy()
        blocks[feature] = [audit]
    filled = filled[[KEY, MONTH, *feature_columns]]
    # Whole-path audit order: feature-major, template roster order within each feature.
    audit_parts = []
    for feature in feature_columns:
        pieces = blocks[feature]
        part = pd.concat(pieces, ignore_index=True)
        for column in part.columns:  # an all-missing group piece must not widen the whole-path dtype
            found = {piece[column].dtype for piece in pieces if piece[column].notna().any()}
            if len(found) == 1 and part[column].dtype != next(iter(found)):
                part[column] = part[column].astype(next(iter(found)))
        if feature in grouped:
            order = {key: i for i, key in enumerate(part["polygon_id"].astype(str))}
            part = part.iloc[[order[key] for key in roster]].reset_index(drop=True)
        audit_parts.append(part)
    audit = pd.concat(audit_parts, ignore_index=True)
    rows = _origin_rows(filled, template, origin=origin, feature_columns=feature_columns)
    return rows, audit, report, {"groups": count, "rows_read": offset, "sorted_branch": sorted_branch,
                                 "groups_with_added_rows": sum(grew.values()),
                                 "whole_column_numeric_features": whole_numeric}


def fewsnet_base_panel(raw: pd.DataFrame, *, origin: str, prepared_families: Mapping, prepared_features: Mapping,
                       wfp=None, acled=None) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """FEWSNET raw panel extended through O with source choices and remote overlay (no filling yet)."""
    frame = raw.copy()
    frame[KEY] = frame["FEWSNET_admin_code"].map(normalize_admin_code)
    frame[MONTH] = pd.to_datetime(frame["date"], format="%Y-%m-%d").dt.strftime("%Y-%m")
    # Whole-panel normalisation statistics must only see rows at or before O.
    after_origin = int((frame[MONTH] > origin).sum())
    frame = frame.loc[frame[MONTH] <= origin].reset_index(drop=True)
    carry = [column for column in FEWSNET_IDENTITY if column in frame and column not in ("month", "date")]
    # Every area gets the full O-12..O dependency calendar even if its panel starts later;
    # such months stay missing (no backward fill) and reach the saved final-feature imputer.
    window_start = str(pd.Period(origin, "M") - FEWSNET_FILL_WINDOW_MONTHS)
    frame = add_calendar_rows(frame, through=origin, carry=carry, from_month=window_start)
    frame["date"] = frame[MONTH] + "-01"
    frame["month"] = frame[MONTH].str[5:].astype(int)
    frame, choices = _source_choices(frame, "fewsnet", wfp, acled)
    frame, overlay, extra = remote_overlay(frame, system="fewsnet", families=prepared_families, features=prepared_features)
    overlay["rows_after_origin_dropped"] = after_origin
    # Older provider observations are carry-forward sources only (third return value);
    # they are not inserted into the scoring panel (global normalisation uses panel rows).
    return frame, {"source_choices": _jsonable(choices), "remote_overlay": overlay}, extra


def fewsnet_fill_columns(frame: pd.DataFrame) -> list[str]:
    excluded = set(FEWSNET_IDENTITY) | set(FEWSNET_LABELS) | set(FEWSNET_DERIVED) | {KEY, MONTH}
    return [column for column in frame.columns if column not in excluded]


def fewsnet_fill_window(base: pd.DataFrame, *, origin: str, source_ref: Mapping[str, str],
                        extra_observations: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill base predictors for months O-12..O from each area's own past; observed values stay."""
    columns = fewsnet_fill_columns(base)
    start = str(pd.Period(origin, "M") - FEWSNET_FILL_WINDOW_MONTHS)
    window = month_range(start, origin)
    roster = sorted(base[KEY].unique())
    numeric = base[[KEY, MONTH, *columns]].copy()
    extra = extra_observations
    if extra is not None and len(extra):
        numeric = pd.concat([numeric, extra.reindex(columns=[KEY, MONTH, *columns])], ignore_index=True)
        numeric = numeric.groupby([KEY, MONTH], as_index=False, sort=False).first()
    for column in columns:
        numeric[column] = pd.to_numeric(numeric[column], errors="raise")
    filled, audit = carry_forward_base_series(
        numeric, system="fewsnet", id_column=KEY, month_column=MONTH, feature_columns=columns,
        roster=roster, months=window, source_ref=source_ref)
    out = base.set_index([KEY, MONTH])
    filled = filled.set_index([KEY, MONTH])
    missing_rows = filled.index.difference(out.index)
    if len(missing_rows):  # every window month must be a scoring-panel row so audit and matrix agree
        raise ValueError(f"fill window rows absent from the scoring panel, e.g. {list(missing_rows[:3])}")
    current = out.loc[filled.index, columns]
    out.loc[filled.index, columns] = current.where(current.notna(), filled[columns])
    return out.reset_index(), audit


def _source_choices(frame, system, wfp, acled):
    """CP1 ``apply_source_choices``; keep/keep is a no-op reported without full-frame copies."""
    if wfp is None and acled is None:
        return frame, {"system": system, "rows": len(frame), "wfp_action": "keep", "acled_action": "keep",
                       "changed_columns": {}}
    return apply_source_choices(frame, system, wfp, acled)


def _jsonable(report):
    return {key: (value if not isinstance(value, (np.integer,)) else int(value)) for key, value in report.items()}
