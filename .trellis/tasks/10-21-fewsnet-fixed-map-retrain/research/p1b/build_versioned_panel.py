"""Build the versioned FEWS source panel for the full-history refit (append/gap-fill only).

Base: the operational bootstrap history panel (= training panel + September WFP/ACLED
refresh). Changes, each recorded per (admin_code, month, column) in a change ledger:

* labels: clear the 2,632 proven `fillna(1)` targets (2025-10/2026-02), then attach the
  5,109 accepted strict-crosswalk HDX observations (fews_ipc = phase, fews_ipc_crisis =
  phase >= 3). Other label columns are untouched.
* calendar: add 2026-05..2026-09 rows per area. Identity and time-invariant columns (one
  value per area across the whole panel) are copied from the area; everything else starts
  missing.
* remote: pinned prepared snapshot `full-window-20261008c` values for appended months
  (EVI/FLDAS/VIIRS 2026-05..2026-08) and for panel cells that are missing; GOSIF v3 2025
  for missing gpp_mean. Existing panel values are kept; snapshot differences are reported.
  Exception: the April assembly forward-filled FLDAS into 2026-04 (every area equals its
  2026-03 value); those proven carry-forward cells take the snapshot's 2026-04 observation.
* WFP: HDX-derived FEWS MoM index for missing cells in the MoM-index era (>= 2025-02, the
  first month both the April training panel and the September refresh carry index-type
  values) and the appended months; existing values kept, differences reported. Earlier
  gaps are not filled: values there follow a different, level-type historical definition
  (e.g. ETH 2450.9, ZWE 4591.9), so they are counted and reported instead.
* ACLED (new API pull covers event dates from 2025-01-01; complete months <= 2025-09):
  rows of 2025-01..2025-06 whose whole conflict family is missing are filled from the
  complete-month aggregation, existing values kept and differences reported; 2025-07 was
  truncated (September export ended 2025-07-22) and is replaced; 2025-08/2025-09 are
  appended. Months <= 2024-12 are outside the new source and stay as they are.
Nothing is imputed: a cell without a source value stays missing.

Usage: python build_versioned_panel.py --config build_config.json --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["FEWSNET_admin_code", "month_key"]
REMOTE = {"evi": {"EVI": "EVI__mean"},
          "fldas": {"Rainf_f_tavg_mean": "Rainf_f_tavg__mean", "Tair_f_tavg_mean": "Tair_f_tavg__mean"},
          # The FEWS panel's nightlight is the VIIRS zonal SUM (panel/avg_rad__sum median ratio
          # 1.000 on 2025-10..2026-03), not the mean in remote_sources.MODEL_COLUMN_MAPPING.
          "viirs": {"nightlight": "avg_rad__sum", "nightlight_sd": "avg_rad__std"}}
CARRIED_FORWARD = {"2026-04": ("Rainf_f_tavg_mean", "Tair_f_tavg_mean")}
NEW_MONTHS = [f"2026-{m:02d}" for m in range(5, 10)]
FILLED_MONTHS = ("2025-10", "2026-02")
WFP_MOM_START = "2025-02"
ACLED_REPLACE = ("2025-07",)
ACLED_APPEND = ("2025-08", "2025-09")
ACLED_GAP_FILL = ("2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06")


def sha256(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class Ledger:
    def __init__(self):
        self.parts = []

    def record(self, frame, mask, column, new_values, reason):
        rows = frame.loc[mask, KEY].copy()
        rows["column"] = column
        rows["old"] = frame.loc[mask, column].to_numpy()
        rows["new"] = np.asarray(new_values)
        rows["reason"] = reason
        self.parts.append(rows)

    def frame(self):
        return pd.concat(self.parts, ignore_index=True) if self.parts else pd.DataFrame()


def _positional(a, b):
    """Numeric arrays compared by position only (never by pandas index alignment)."""
    a = pd.to_numeric(pd.Series(np.asarray(a, dtype=object)), errors="coerce").to_numpy(dtype=float)
    b = pd.to_numeric(pd.Series(np.asarray(b, dtype=object)), errors="coerce").to_numpy(dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"positional comparison length mismatch {a.shape} != {b.shape}")
    return a, b


def same(a, b):
    a, b = _positional(a, b)
    return (a == b) | (np.isnan(a) & np.isnan(b))


def diff_summary(old, new):
    old, new = _positional(old, new)
    both = ~np.isnan(old) & ~np.isnan(new)
    delta = np.abs(old[both] - new[both])
    return {"cells_both_present": int(both.sum()), "exact": int((delta == 0).sum()),
            "abs_diff_median": float(np.median(delta)) if delta.size else None,
            "abs_diff_p90": float(np.quantile(delta, 0.9)) if delta.size else None,
            "panel_only": int((~np.isnan(old) & np.isnan(new)).sum()),
            "source_only_filled": int((np.isnan(old) & ~np.isnan(new)).sum())}


def apply_fill(panel, ledger, values, column, months, reason, report):
    """Set ``column`` from ``values`` (indexed by KEY) only where the panel cell is missing."""
    idx = pd.MultiIndex.from_frame(panel[KEY])
    incoming = values.reindex(idx).to_numpy()
    in_scope = panel["month_key"].isin(months).to_numpy()
    current = panel[column].to_numpy()
    have = pd.notna(incoming) & in_scope
    fill = have & pd.isna(current)
    overlap = have & pd.notna(current)
    report[f"{column}:{reason}"] = {"filled": int(fill.sum()),
                                    **diff_summary(current[overlap], incoming[overlap])}
    ledger.record(panel, fill, column, incoming[fill], reason)
    panel.loc[fill, column] = incoming[fill]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    sys.path.insert(0, cfg["runtime_root"])
    from tools.refresh_h5_inputs import conflict_aggregates, replace_acled

    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    inputs = {name: {"path": path, "sha256": sha256(path)} for name, path in cfg["inputs"].items()}
    for name, expected in cfg.get("expected_sha256", {}).items():
        if inputs[name]["sha256"] != expected:
            raise ValueError(f"{name} sha256 {inputs[name]['sha256']} != expected {expected}")
    report: dict[str, object] = {"inputs": inputs}
    ledger = Ledger()

    panel = pd.read_csv(cfg["inputs"]["base_panel"], dtype={"FEWSNET_admin_code": str}, low_memory=False)
    columns = list(panel.columns)
    panel["month_key"] = panel["date"].str[:7]
    if panel.duplicated(KEY).any():
        raise ValueError("base panel has duplicate keys")
    base_rows = len(panel)

    # --- calendar rows 2026-05..2026-09 -----------------------------------------
    if panel["month_key"].max() != "2026-04":
        raise ValueError("base panel must end at 2026-04")
    nunique = panel.groupby("FEWSNET_admin_code").nunique(dropna=True)
    invariant = ["FEWSNET_admin_code"] + [
        c for c in columns
        if c not in ("FEWSNET_admin_code", "date", "month") and (nunique[c] <= 1).all()]
    last = panel.sort_values("month_key").groupby("FEWSNET_admin_code").tail(1).set_index("FEWSNET_admin_code")
    first_valid = panel.groupby("FEWSNET_admin_code")[invariant[1:]].first()
    blocks = []
    for month in NEW_MONTHS:
        block = pd.DataFrame(index=last.index)
        for c in invariant[1:]:
            block[c] = first_valid[c]
        block = block.reset_index()
        block["date"] = month + "-01"
        block["month"] = int(month[5:])
        block["month_key"] = month
        blocks.append(block)
    panel = pd.concat([panel, *blocks], ignore_index=True)[columns + ["month_key"]]
    panel = panel.sort_values(["FEWSNET_admin_code", "month_key"], kind="mergesort").reset_index(drop=True)
    report["calendar"] = {"base_rows": base_rows, "appended_rows": len(panel) - base_rows,
                          "appended_months": NEW_MONTHS, "copied_time_invariant_columns": invariant}

    # --- labels -----------------------------------------------------------------
    decisions = pd.read_csv(cfg["inputs"]["crosswalk_decisions"], dtype={"admin_code": str}, low_memory=False)
    proven = decisions[(decisions["production_label_source"] == "imputed_fill_proven")
                       & decisions["month"].isin(FILLED_MONTHS)]
    accepted = decisions[decisions["comparison"].isin(
        ["addition_no_production_label", "replaces_proven_imputed_fill"])]
    if len(proven) != 2632 or len(accepted) != 5109:
        raise ValueError(f"unexpected label counts proven={len(proven)} accepted={len(accepted)}")
    idx = pd.MultiIndex.from_frame(panel[KEY])
    clear = idx.isin(pd.MultiIndex.from_arrays([proven["admin_code"], proven["month"]]))
    if not ((panel.loc[clear, "fews_ipc"] == 1).all() and (panel.loc[clear, "fews_ipc_crisis"] == 0).all()):
        raise ValueError("proven fill cells are not exactly phase 1 / crisis 0")
    other_labels = ["fews_ha", "fews_ipc_adjusted", "fews_proj_near", "fews_proj_med"]
    report["labels"] = {"cleared_proven_fills": int(clear.sum()),
                        "cleared_rows_other_label_columns_nonnull": {
                            c: int(panel.loc[clear, c].notna().sum()) for c in other_labels if c in panel}}
    for column in ("fews_ipc", "fews_ipc_crisis"):
        ledger.record(panel, clear, column, np.full(int(clear.sum()), np.nan), "clear_proven_fillna1_target")
        panel.loc[clear, column] = np.nan
    phase = accepted.set_index(["admin_code", "month"])["accepted_phase"]
    incoming = phase.reindex(pd.MultiIndex.from_frame(panel[KEY])).to_numpy()
    attach = pd.notna(incoming)
    if int(attach.sum()) != 5109 or panel.loc[attach, "fews_ipc"].notna().any():
        raise ValueError("accepted labels must land on 5109 empty target cells")
    ledger.record(panel, attach, "fews_ipc", incoming[attach], "hdx_strict_crosswalk_observation")
    ledger.record(panel, attach, "fews_ipc_crisis", (incoming[attach] >= 3).astype(float),
                  "hdx_strict_crosswalk_observation")
    panel.loc[attach, "fews_ipc"] = incoming[attach]
    panel.loc[attach, "fews_ipc_crisis"] = (incoming[attach] >= 3).astype(float)
    report["labels"]["attached_observations_by_month"] = (
        panel.loc[attach, "month_key"].value_counts().sort_index().to_dict())

    # --- remote families ---------------------------------------------------------
    remote_report: dict[str, object] = {}
    for family, mapping in REMOTE.items():
        snap = pd.read_csv(cfg["inputs"][f"snapshot_{family}"], dtype={"admin_code": str})
        snap = snap.rename(columns={"admin_code": "FEWSNET_admin_code", "month": "month_key"}).set_index(KEY)
        months = sorted(snap.index.get_level_values("month_key").unique())
        for column, stat in mapping.items():
            apply_fill(panel, ledger, snap[stat], column, months, f"snapshot_{family}", remote_report)
    fldas = pd.read_csv(cfg["inputs"]["snapshot_fldas"], dtype={"admin_code": str})
    fldas = fldas.rename(columns={"admin_code": "FEWSNET_admin_code", "month": "month_key"}).set_index(KEY)
    for month, carried in CARRIED_FORWARD.items():
        previous = str(pd.Period(month, "M") - 1)
        prior = panel[panel["month_key"] == previous].set_index("FEWSNET_admin_code")
        rows = (panel["month_key"] == month).to_numpy()
        for column in carried:
            stat = REMOTE["fldas"][column]
            current = panel[column].to_numpy()
            prev_values = panel["FEWSNET_admin_code"].map(prior[column]).to_numpy()
            equal_prev = rows & pd.notna(current) & (current == prev_values)
            share = float(equal_prev[rows].mean())
            if share < 0.999:
                raise ValueError(f"{column} {month} is not a proven carry-forward (share {share})")
            incoming = fldas[stat].reindex(pd.MultiIndex.from_frame(panel[KEY])).to_numpy()
            replace = equal_prev & pd.notna(incoming)
            remote_report[f"{column}:replace_proven_carry_forward_{month}"] = {
                "rows_in_month": int(rows.sum()), "share_equal_to_previous_month": share,
                "replaced_with_observation": int(replace.sum()),
                "kept_carried_value_no_observation": int((equal_prev & pd.isna(incoming)).sum()),
                **diff_summary(current[replace], incoming[replace])}
            ledger.record(panel, replace, column, incoming[replace],
                          f"replace_proven_carry_forward_{month}")
            panel.loc[replace, column] = incoming[replace]
    gosif = pd.read_csv(cfg["inputs"]["gosif_v3_2025"], dtype={"admin_code": str})
    gosif = gosif.rename(columns={"admin_code": "FEWSNET_admin_code", "month": "month_key"}).set_index(KEY)
    apply_fill(panel, ledger, gosif["GPP_Mean__mean"], "gpp_mean",
               sorted(gosif.index.get_level_values("month_key").unique()), "gosif_v3_2025", remote_report)
    snap_gosif = pd.read_csv(cfg["inputs"]["snapshot_gosif_mean"], dtype={"admin_code": str})
    snap_gosif = snap_gosif.rename(columns={"admin_code": "FEWSNET_admin_code", "month": "month_key"}).set_index(KEY)
    apply_fill(panel, ledger, snap_gosif["GPP_Mean__mean"], "gpp_mean", ["2024-12"],
               "snapshot_gosif_v2", remote_report)
    remote_report["pending"] = {"EVI 2026-09": "provider published (EE 2026_09_01); extraction pending, cell missing"}
    report["remote"] = remote_report

    # --- WFP ---------------------------------------------------------------------
    wfp = pd.read_csv(cfg["inputs"]["wfp_fews_country_month"])
    wfp = wfp.rename(columns={"period": "month_key"})
    area_iso = panel.groupby("FEWSNET_admin_code")["ISO3"].first()
    keyed = panel[KEY].copy()
    keyed["ISO3"] = keyed["FEWSNET_admin_code"].map(area_iso)
    merged = keyed.merge(wfp, on=["ISO3", "month_key"], how="left")
    wfp_report: dict[str, object] = {}
    mom_months = sorted(m for m in panel["month_key"].unique() if m >= WFP_MOM_START)
    for column in ("WFP_Price", "WFP_Price_std"):
        values = pd.Series(merged[column].to_numpy(), index=pd.MultiIndex.from_frame(panel[KEY]))
        apply_fill(panel, ledger, values, column, mom_months, "hdx_wfp_fews_mom", wfp_report)
    early = (panel["month_key"] < WFP_MOM_START).to_numpy()
    early_gap = early & panel["WFP_Price"].isna().to_numpy() & merged["WFP_Price"].notna().to_numpy()
    wfp_report["not_filled_before_mom_era"] = {
        "reason": "historical WFP_Price before 2025-02 follows a different level-type definition "
                  "(April training panel e.g. ETH 2450.9, SSD 1943.4, YEM 551.0, ZWE 4591.9); "
                  "MoM index values would mix definitions within that era",
        "area_month_cells_with_hdx_value": int(early_gap.sum()),
        "country_months": int(merged.loc[early_gap, ["ISO3", "month_key"]].drop_duplicates().shape[0]),
        "month_range": [str(panel.loc[early_gap, "month_key"].min()),
                        str(panel.loc[early_gap, "month_key"].max())] if early_gap.any() else None}
    report["wfp"] = wfp_report

    # --- ACLED -------------------------------------------------------------------
    adm3, acled_meta = conflict_aggregates(Path(cfg["inputs"]["acled_raw"]), cutoff="2025-09")
    conflict_columns = [c for c in columns if c.startswith(("event_count_", "sum_fatalities_"))] + [
        "distance_to_nearest_acled"]
    acled_report: dict[str, object] = {"aggregation": {k: v for k, v in acled_meta.items()
                                                       if k != "covered_months"}}
    for months, mode in ((ACLED_GAP_FILL, "fill_gap_rows"), (ACLED_REPLACE, "replace_truncated"),
                         (ACLED_APPEND, "append_complete")):
        rows = panel["month_key"].isin(months).to_numpy()
        before = panel.loc[rows].reset_index(drop=True)
        frame = before.drop(columns=["month_key"])
        after, _ = replace_acled(frame, adm3[adm3["period"].isin(months)])
        if len(after) != len(before) or not after.index.equals(before.index):
            raise ValueError("replace_acled changed row order/length")
        if mode == "append_complete" and before[conflict_columns].notna().any(axis=None):
            raise ValueError("appended ACLED months must be empty in the base panel")
        gap_rows = before[conflict_columns].isna().all(axis=1).to_numpy()
        apply_rows = gap_rows if mode == "fill_gap_rows" else np.ones(len(before), dtype=bool)
        kept = ~apply_rows & before["distance_to_nearest_acled"].notna().to_numpy()
        acled_report[f"{mode}:{months[0]}..{months[-1]}"] = {
            "rows": int(rows.sum()),
            "rows_applied": int((apply_rows & after["distance_to_nearest_acled"].notna().to_numpy()).sum()),
            "rows_without_match_after": int((apply_rows & after["distance_to_nearest_acled"].isna().to_numpy()).sum()),
            "existing_rows_kept": int(kept.sum()),
            "kept_rows_revision_event_count_battles": diff_summary(
                before.loc[kept, "event_count_battles"], after.loc[kept, "event_count_battles"]),
            "kept_rows_revision_distance": diff_summary(
                before.loc[kept, "distance_to_nearest_acled"], after.loc[kept, "distance_to_nearest_acled"]),
            "by_month_rows_applied": pd.Series(before.loc[apply_rows & after["distance_to_nearest_acled"]
                                               .notna().to_numpy(), "month_key"]).value_counts().sort_index().to_dict()}
        positions = np.flatnonzero(rows)
        for c in conflict_columns:
            changed = apply_rows & ~same(before[c], after[c])
            mask = np.zeros(len(panel), dtype=bool)
            mask[positions[changed]] = True
            ledger.record(panel, mask, c, after[c].to_numpy()[changed], f"acled_{mode}")
            panel.loc[mask, c] = after[c].to_numpy()[changed]
    acled_report["not_filled"] = {"months_before_2025-01": "outside the new API pull (event dates from 2025-01-01)",
                                  "months_after_2025-09": "incomplete (2025-10 partial) or unavailable under the "
                                                          "account's ~12-month delay; left missing"}
    report["acled"] = acled_report

    # --- invariants and outputs ----------------------------------------------------
    if panel.duplicated(KEY).any() or panel["FEWSNET_admin_code"].nunique() != 5718:
        raise ValueError("versioned panel keys/areas invalid")
    changes = ledger.frame()
    original = pd.read_csv(cfg["inputs"]["base_panel"], dtype={"FEWSNET_admin_code": str}, low_memory=False)
    original["month_key"] = original["date"].str[:7]
    check = panel.merge(original, on=KEY, how="inner", suffixes=("", "__base"))
    changed_cells = set(zip(changes["FEWSNET_admin_code"], changes["month_key"], changes["column"]))
    unexplained: dict[str, int] = {}
    for c in columns:
        if c == "FEWSNET_admin_code":
            continue
        left, right = check[c], check[c + "__base"]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            diff = ~same(left, right)
        else:
            diff = ~((left.astype(str) == right.astype(str)).to_numpy() | (left.isna() & right.isna()).to_numpy())
        count = sum((code, month, c) not in changed_cells
                    for code, month in zip(check.loc[diff, "FEWSNET_admin_code"], check.loc[diff, "month_key"]))
        if count:
            unexplained[c] = count
    if unexplained:
        raise ValueError(f"base cells changed without a ledger entry: {unexplained}")
    report["invariants"] = {"rows": len(panel), "areas": int(panel["FEWSNET_admin_code"].nunique()),
                            "month_min": panel["month_key"].min(), "month_max": panel["month_key"].max(),
                            "base_cells_changed_without_ledger": 0,
                            "latest_label_month": panel.loc[panel["fews_ipc_crisis"].notna(), "month_key"].max(),
                            "label_rows": int(panel["fews_ipc_crisis"].notna().sum())}
    panel_path = out / "FEWSNET_versioned_source_panel_20261022.csv"
    panel[columns].to_csv(panel_path, index=False)
    changes.to_csv(out / "change_ledger.csv.gz", index=False)
    report["outputs"] = {"source_panel": {"path": str(panel_path), "sha256": sha256(panel_path),
                                          "rows": len(panel)},
                         "change_ledger": {"path": str(out / "change_ledger.csv.gz"),
                                           "sha256": sha256(out / "change_ledger.csv.gz"),
                                           "rows": len(changes),
                                           "by_reason_column": changes.groupby(["reason", "column"]).size()
                                           .rename("n").reset_index().to_dict("records")}}
    (out / "build_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report["invariants"], default=str))


if __name__ == "__main__":
    main()
