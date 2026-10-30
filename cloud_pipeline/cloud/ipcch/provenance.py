"""Row/section temporal provenance of an IPCCH feature batch - the new-contract feature-fill sidecar (task 10-29; R13,
R43, R47, R59, R62, R65 and the Supervisor CP4 ruling: actual no-fill/missingness/provenance, no fabricated imputation,
no aggregate counts in place of row/section temporal provenance).

One row per (polygon, section): the 527 features are grouped into the sections the assembly computes them from; for
each, the feature month O, the dependency window actually read (series: the area's saved history through O, ACLED
through A = O - 1; seasons: completed by O; reports: dated <= O), the latest actual observation inside it for THIS area
(month, season or report month; empty when the area has none), the number of the section's features that are missing
in each horizon's row, the retained table and version the values came from, and the fill semantics: nothing is filled
or imputed (``fill_method = none``; NaN is passed to XGBoost, ``nan_passthrough_no_imputation``).
"""

from __future__ import annotations

import re
from typing import Any, Mapping

import numpy as np
import pandas as pd

from cloud.ipcch import climate as cl
from cloud.ipcch.vendor import ipcch_compact as cp

COLUMNS = ("system", "polygon_id", "section", "observation_kind", "feature_count", "missing_h02", "missing_h08",
           "missing_h14", "feature_month", "dependency_start", "dependency_end", "latest_observation", "source_table",
           "source_version", "source_sha256", "fill_method", "feature_value_method", "imputation_rule")
_INTERIM = {"bbg_staple_food": "bbg_staple_food__composite_mean", "bbg_oilgas": "bbg_oilgas__composite_mean",
            "bbg_soybean_oil": "bbg_soybean_oil__composite_mean", "bbg_global_food": "bbg_global_food__composite_mean"}


def _ord(month: str) -> int:
    y, m = (int(x) for x in month.split("-"))
    return y * 12 + m - 1


def _label(o) -> str:
    o = int(o)
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def section_of(feature: str, static: set[str]) -> tuple[str, str]:
    if feature in static:
        return "static29", "static"
    if re.fullmatch(r"ae\d+_(mean|sd)_A\d+", feature):
        return "alphaearth_2017", "static"
    if feature in ("lat", "lon") or re.fullmatch(r"(month|year)_\d+", feature):
        return "identifiers", "target_identifiers"
    if feature.startswith(("gs_last1", "gs_last2")):
        return "growing_seasons", "completed_season"
    if feature.startswith("overall_phase_history"):
        return "reported_phase_history", "report_month"
    if feature.startswith("idp_admin0"):
        return "idp_national", "report_month"
    if feature.startswith("idp_ipcch"):
        return "idp_local", "month"
    prefix = feature.split("__", 1)[0]
    if prefix.startswith("acled_agg_"):
        return prefix, "month_lag1"
    return prefix, "month"


def _series(inputs, section: str):
    """(frame admin_code/month/value, retained table) behind a monthly section."""
    if section.endswith("_month_ensmean"):
        base = section[: -len("_month_ensmean")]
        return inputs.climate_monthly[base], cl.table_name(base, cl.MONTHLY)
    if section == "idp_local":
        return inputs.idp_local, "history__idp_local"
    if section.startswith("acled_agg_"):
        f = inputs.acled
        return f[["admin_code", "month", section]].rename(columns={section: "value"}), "acled_agg_weekly"
    family = _INTERIM.get(section, section)
    return inputs.interim[family], f"history__{family}"


def section_provenance(inputs, frames: Mapping[int, pd.DataFrame], ledger: pd.DataFrame, *, order, origin: str,
                       roster, retained_refs: Mapping[str, Any]) -> pd.DataFrame:
    """The sidecar for one batch (see module docstring). ``ledger`` is the assembly ledger of any horizon (the origin-
    side columns are horizon-independent); ``retained_refs`` maps retained table -> {version, sha256}."""
    static = set(order[:29])
    sections: dict[str, list[str]] = {}
    kinds: dict[str, str] = {}
    for f in order:
        s, k = section_of(f, static)
        sections.setdefault(s, []).append(f)
        kinds[s] = k
    areas = [str(a) for a in roster]
    O = _ord(origin)
    led = ledger.assign(admin_code=ledger["admin_code"].astype(str)).set_index("admin_code").reindex(areas)
    rows = []
    for s, feats in sections.items():
        kind = kinds[s]
        miss = {h: frames[h].set_index(frames[h]["admin_code"].astype(str))[feats].isna().sum(axis=1).reindex(areas)
                for h in (2, 8, 14)}
        start = end = latest = None
        table = None
        if kind in ("month", "month_lag1"):
            frame, table = _series(inputs, s)
            end_ord = O - 1 if kind == "month_lag1" else O
            f = frame[frame["value"].notna()].assign(admin_code=frame["admin_code"].astype(str))
            f = f[f["month"].map(_ord) <= end_ord]
            g = f.groupby("admin_code")["month"]
            start, latest = g.min().reindex(areas), g.max().reindex(areas)
            end = pd.Series(_label(end_ord), index=areas)
        elif kind == "completed_season":
            table = "history__climate_gs_* (13 bases)"
            cutoff = led["season_cutoff_date"].astype(str)
            end = cutoff
            w = inputs.season_windows.assign(admin_code=inputs.season_windows["admin_code"].astype(str))
            w = w[w["gs_end_date_exclusive"].astype(str) <= w["admin_code"].map(cutoff).astype(str)]
            last = w.sort_values(["gs_end_date_exclusive", "season_year", "season"]).groupby("admin_code").tail(1)
            latest = (last.set_index("admin_code")["season_year"].astype(str) + "-"
                      + last.set_index("admin_code")["season"]).reindex(areas)
        elif kind == "report_month":
            col = "history_1_source_ord" if s == "reported_phase_history" else "idp_report_ord"
            table = "history__history_snapshot" if s == "reported_phase_history" else "history__idp_national"
            latest = led[col].map(lambda v: _label(v) if pd.notna(v) and float(v) >= 0 else None)
            end = pd.Series(origin, index=areas)
        ref = retained_refs.get(table or "", {})
        for a in areas:
            rows.append({"system": "ipcch", "polygon_id": a, "section": s, "observation_kind": kind,
                         "feature_count": len(feats), "missing_h02": int(miss[2][a]), "missing_h08": int(miss[8][a]),
                         "missing_h14": int(miss[14][a]), "feature_month": origin,
                         "dependency_start": None if start is None or pd.isna(start[a]) else start[a],
                         "dependency_end": None if end is None else end[a],
                         "latest_observation": None if latest is None or pd.isna(latest[a]) else latest[a],
                         "source_table": table, "source_version": ref.get("version"), "source_sha256": ref.get("sha256"),
                         "fill_method": "none", "feature_value_method": "nan_passthrough_no_imputation",
                         "imputation_rule": "none"})
    out = pd.DataFrame(rows, columns=list(COLUMNS))
    if out.duplicated(["polygon_id", "section"]).any():
        raise ValueError("feature provenance has duplicate (polygon, section) rows")
    return out
