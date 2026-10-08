import numpy as np
import pandas as pd
import pytest

from cloud.orchestrator import delivery_inputs as di
from tools.refresh_h5_inputs import CONFLICT_COLUMNS, WFP_COLUMNS

SOURCE_REF = {"uri": "gs://bucket/inputs/base.csv", "generation": "3", "sha256": "b" * 64}
FAMILIES = {
    "evi": {"provider_latest_completed_month": "2026-08"},
    "fldas": {"provider_latest_completed_month": "2026-08"},
    "gosif_mean": {"provider_latest_completed_month": "2024-12"},
    "gosif_sd": {"provider_latest_completed_month": "2024-12"},
    "viirs": {"provider_latest_completed_month": "2026-08"},
}
IPCCH_RS = list(di.MODEL_COLUMN_MAPPING["ipcch"])


def _ipcch_panel():
    rows = []
    for area, iso in (("0", "NGA"), ("00", "NGA")):
        for year, month in ((2024, 12), (2026, 3), (2026, 4)):
            row = {"area_id": area, "admin_code": area, "year": year, "month": month, "lat": 9.0, "lon": 8.0,
                   "ISO3": iso, "country_en": "Nigeria", "CPI": float(month), "gini": 30.0}
            row.update({column: 1.0 for column in IPCCH_RS})
            row.update({column: 0.0 for column in WFP_COLUMNS + CONFLICT_COLUMNS})
            rows.append(row)
    panel = pd.DataFrame(rows)
    # Filled GPP after the provider vintage (2024-12) must not survive as observations.
    panel.loc[panel["year"].eq(2026), ["GPP_mean", "GPP_std"]] = 7.0
    panel.loc[(panel.admin_code == "00") & panel["year"].eq(2026) & panel["month"].eq(4), "CPI"] = np.nan
    return panel


def _prepared(month, value, areas=("0", "00")):
    return {"evi": pd.DataFrame({"admin_code": list(areas), "month": month, "EVI__mean": value, "EVI__std": value / 10})}


def test_remote_overlay_clears_history_after_vintage_and_applies_prepared_months():
    base, report = di.ipcch_base_series(_ipcch_panel(), origin="2026-10", prepared_families=FAMILIES,
                                        prepared_features=_prepared("2026-08", 5.0))

    by = base.set_index(["admin_code", "month_key"])
    assert by.loc[("0", "2024-12"), "GPP_mean"] == 1.0  # at the vintage: observation kept
    assert np.isnan(by.loc[("0", "2026-04"), "GPP_mean"])  # after it: cleared
    assert by.loc[("0", "2026-08"), "EVI_mean"] == 5.0 and by.loc[("0", "2026-08"), "EVI_std"] == 0.5
    assert sorted(base.loc[base.admin_code.eq("0"), "month_key"])[-1] == "2026-10"  # calendar rows through O
    assert by.loc[("0", "2026-09"), "ISO3"] == "NGA" and np.isnan(by.loc[("0", "2026-09"), "CPI"])
    assert report["remote_overlay"]["gosif_mean"]["history_rows_cleared_after_vintage_or_planned"] == 4
    assert report["remote_overlay"]["evi"]["prepared_rows_applied"] == 2
    assert report["source_choices"]["wfp_action"] == "keep"


def test_prepared_rows_outside_the_panel_calendar_are_returned_as_observations():
    base = _ipcch_panel().assign(month_key=lambda f: f.year.astype(str) + "-" + f.month.astype(str).str.zfill(2))

    _, report, extra = di.remote_overlay(base, system="ipcch", families=FAMILIES, features=_prepared("2024-06", 1.0))

    assert extra[["admin_code", "month_key", "EVI_mean"]].values.tolist() == [["0", "2024-06", 1.0], ["00", "2024-06", 1.0]]
    assert report["evi"]["prepared_rows_outside_panel_calendar"] == 2


def test_ipcch_origin_rows_fill_each_area_from_its_own_past():
    base, _ = di.ipcch_base_series(_ipcch_panel(), origin="2026-10", prepared_families=FAMILIES,
                                   prepared_features=_prepared("2026-08", 5.0))
    template = _ipcch_panel().query("year == 2026 and month == 4").reset_index(drop=True)

    rows, audit = di.ipcch_origin_rows(base, template, origin="2026-10", feature_columns=["EVI_mean", "GPP_mean", "CPI"],
                                       source_ref=SOURCE_REF)

    rows = rows.set_index("admin_code")
    assert (rows.loc["0", "year"], rows.loc["0", "month"]) == (2026, 10)
    assert rows.loc["0", "EVI_mean"] == 5.0 and rows.loc["0", "GPP_mean"] == 1.0  # GPP from the 2024-12 vintage
    assert rows.loc["0", "CPI"] == 4.0 and rows.loc["00", "CPI"] == 3.0  # never another area's value
    gpp = audit.set_index(["polygon_id", "source_feature"]).loc[("0", "GPP_mean")]
    assert (gpp["observation_month"], gpp["staleness_months"], gpp["fill_method"]) == ("2024-12", 22, "carry_forward")


def _fews_raw():
    rows = []
    for code in ("1.0", "2"):
        for month in ("2025-09", "2026-03", "2026-04"):
            rows.append({"unit_name": "u", "ADMIN0": "Kenya", "ADMIN1": "a", "ADMIN2": "b", "ADMIN3": "",
                         "FEWSNET_admin_code": code, "ISO": "KE", "ISO3": "KEN", "lat": 1.0, "lon": 36.0,
                         "month": int(month[5:]), "date": f"{month}-01", "EVI": 0.3, "nightlight": 2.0,
                         "nightlight_sd": 1.0, "gpp_mean": 9.0, "Rainf_f_tavg_mean": 1.0, "Tair_f_tavg_mean": 300.0,
                         "CPI": 100.0, "pop": 5.0, "fews_ipc": 2.0, "fews_ipc_crisis": 0.0, "fews_ha": 1.0,
                         "Tair_zscore": 0.1, "Rainf_zscore": 0.2,
                         **{column: 0.0 for column in WFP_COLUMNS + CONFLICT_COLUMNS}})
    return pd.DataFrame(rows)


def test_fewsnet_window_fill_leaves_labels_and_observed_values_untouched():
    base, report, extra = di.fewsnet_base_panel(_fews_raw(), origin="2026-10", prepared_families=FAMILIES,
                                                prepared_features={})

    filled, audit = di.fewsnet_fill_window(base, origin="2026-10", source_ref=SOURCE_REF)

    by = filled.set_index(["admin_code", "month_key"])
    assert set(filled["admin_code"]) == {"1", "2"}  # normalized native IDs
    assert by.loc[("1", "2026-10"), "date"] == "2026-10-01" and by.loc[("1", "2026-10"), "month"] == 10
    assert by.loc[("1", "2026-10"), "EVI"] == 0.3 and by.loc[("1", "2026-10"), "CPI"] == 100.0
    assert np.isnan(by.loc[("1", "2026-10"), "fews_ipc"]) and np.isnan(by.loc[("1", "2026-10"), "fews_ha"])
    assert np.isnan(by.loc[("1", "2026-10"), "Tair_zscore"])  # recomputed by normalisation, not filled
    assert np.isnan(by.loc[("1", "2026-10"), "gpp_mean"])  # history after the 2024-12 vintage was cleared
    assert np.isnan(by.loc[("1", "2025-09"), "gpp_mean"])  # 2025-09 is after the 2024-12 vintage too
    window = sorted(audit["feature_month"].unique())
    assert window[0] == "2025-10" and window[-1] == "2026-10"
    assert "fews_ipc" not in set(audit["source_feature"]) and "gpp_mean" in set(audit["source_feature"])
    assert report["remote_overlay"]["gosif_mean"]["history_rows_cleared_after_vintage_or_planned"] == 6


def _stage3_lags(frame, origin):
    """The same calendar joins Stage3 uses (add_calendar_lag / _add_calendar_rolling_sum) at O."""
    from fewsnet_partitioned_rf_pipeline.core.preprocessing import _add_calendar_rolling_sum, add_calendar_lag

    working = frame.assign(feature_month=pd.PeriodIndex(frame["month_key"], freq="M"))
    working["EVI"] = pd.to_numeric(working["EVI"])
    working["WFP_Price"] = pd.to_numeric(working["WFP_Price"])
    working = add_calendar_lag(working, "EVI", 12, "EVI_l12")
    working = _add_calendar_rolling_sum(working, "WFP_Price", 12, "WFP_Price_m12")
    return working.loc[working["month_key"].eq(origin)].set_index("admin_code")


def test_fewsnet_interior_dependency_months_enter_the_scoring_panel():
    base, _, extra = di.fewsnet_base_panel(_fews_raw(), origin="2026-10", prepared_families=FAMILIES,
                                           prepared_features={})

    filled, audit = di.fewsnet_fill_window(base, origin="2026-10", source_ref=SOURCE_REF, extra_observations=extra)

    months = sorted(filled.loc[filled.admin_code.eq("1"), "month_key"])
    assert months == di.month_range("2025-09", "2026-10")  # interior gap 2025-10..2026-02 completed
    at_origin = _stage3_lags(filled, "2026-10")
    assert at_origin.loc["1", "EVI_l12"] == 0.3  # 2025-10 dependency exists and is the audited carry-forward
    assert at_origin.loc["1", "WFP_Price_m12"] == 0.0
    evi_oct = audit.set_index(["polygon_id", "source_feature", "feature_month"]).loc[("1", "EVI", "2025-10")]
    assert (evi_oct["fill_method"], evi_oct["observation_month"]) == ("carry_forward", "2025-09")
    by = filled.set_index(["admin_code", "month_key"])
    assert np.isnan(by.loc[("1", "2025-10"), "fews_ipc_crisis"])  # truth labels stay blank


def test_older_provider_vintage_is_a_carry_forward_source_not_a_panel_row():
    prepared = {"gosif_mean": pd.DataFrame({"admin_code": ["1", "2"], "month": "2024-12", "GPP_Mean__mean": [8.0, 6.0]})}
    base, report, extra = di.fewsnet_base_panel(_fews_raw(), origin="2026-10", prepared_families=FAMILIES,
                                                prepared_features=prepared)

    filled, audit = di.fewsnet_fill_window(base, origin="2026-10", source_ref=SOURCE_REF, extra_observations=extra)

    assert "2024-12" not in set(filled["month_key"])  # scoring panel not extended backwards
    by = filled.set_index(["admin_code", "month_key"])
    assert by.loc[("1", "2026-10"), "gpp_mean"] == 8.0 and by.loc[("2", "2026-10"), "gpp_mean"] == 6.0
    gpp = audit.set_index(["polygon_id", "source_feature", "feature_month"]).loc[("1", "gpp_mean", "2026-10")]
    assert (gpp["observation_month"], gpp["staleness_months"]) == ("2024-12", 22)
    assert report["remote_overlay"]["gosif_mean"]["prepared_rows_outside_panel_calendar"] == 2


def test_ipcch_older_provider_vintage_joins_the_observation_series():
    panel = _ipcch_panel().query("year == 2026").reset_index(drop=True)  # panel starts after the 2024-12 vintage
    prepared = {"gosif_mean": pd.DataFrame({"admin_code": ["0", "00"], "month": "2024-12", "GPP_Mean__mean": [8.0, 6.0]})}
    base, _ = di.ipcch_base_series(panel, origin="2026-10", prepared_families=FAMILIES, prepared_features=prepared)

    rows, audit = di.ipcch_origin_rows(base, panel.query("month == 4").reset_index(drop=True), origin="2026-10",
                                       feature_columns=["GPP_mean"], source_ref=SOURCE_REF)

    assert rows.set_index("admin_code")["GPP_mean"].to_dict() == {"0": 8.0, "00": 6.0}
    assert set(audit["observation_month"]) == {"2024-12"}


def test_planned_refresh_months_replace_history_even_where_new_cells_are_missing():
    families = {**FAMILIES, "evi": {"provider_latest_completed_month": "2026-08",
                                    "system_months": {"ipcch": ["2026-03", "2026-04"]}}}
    prepared = {"evi": pd.DataFrame({"admin_code": ["0", "00"], "month": "2026-03", "EVI__mean": [5.0, np.nan],
                                     "EVI__std": [0.5, np.nan]})}

    base, report = di.ipcch_base_series(_ipcch_panel(), origin="2026-10", prepared_families=families,
                                        prepared_features=prepared)

    by = base.set_index(["admin_code", "month_key"])
    assert by.loc[("0", "2026-03"), "EVI_mean"] == 5.0
    assert np.isnan(by.loc[("00", "2026-03"), "EVI_mean"])  # history 1.0 replaced by the missing new cell
    assert np.isnan(by.loc[("0", "2026-04"), "EVI_mean"])  # planned but not extracted (not published)
    assert by.loc[("0", "2024-12"), "EVI_mean"] == 1.0  # outside the window: untouched


def test_rows_after_origin_never_reach_whole_panel_statistics():
    raw = pd.concat([_fews_raw(), _fews_raw().assign(date="2026-12-01", month=12)], ignore_index=True)

    base, report, _ = di.fewsnet_base_panel(raw, origin="2026-10", prepared_families=FAMILIES, prepared_features={})

    assert base["month_key"].max() == "2026-10"
    assert report["remote_overlay"]["rows_after_origin_dropped"] == 6


def test_area_starting_inside_the_window_gets_missing_dependency_rows_not_an_error():
    raw = _fews_raw().query("date >= '2026-01-01'").reset_index(drop=True)
    base, _, extra = di.fewsnet_base_panel(raw, origin="2026-10", prepared_families=FAMILIES, prepared_features={})

    filled, audit = di.fewsnet_fill_window(base, origin="2026-10", source_ref=SOURCE_REF, extra_observations=extra)

    by = filled.set_index(["admin_code", "month_key"])
    assert np.isnan(by.loc[("1", "2025-10"), "EVI"]) and np.isnan(by.loc[("1", "2025-10"), "fews_ipc_crisis"])
    assert by.loc[("1", "2026-05"), "EVI"] == 0.3  # forward from its own first observation only
    early = audit.set_index(["polygon_id", "source_feature", "feature_month"]).loc[("1", "EVI", "2025-10")]
    assert early["fill_method"] == "no_eligible_history" and pd.isna(early["observation_month"])
    assert _stage3_lags(filled, "2026-10").loc["1", "EVI_l12"] != _stage3_lags(filled, "2026-10").loc["1", "EVI_l12"]


def test_origin_rows_rederive_population_method_for_the_origin():
    from model_pipeline.ipcch_launch_runtime.population import validate_population_contract

    base, _ = di.ipcch_base_series(_ipcch_panel(), origin="2026-10", prepared_families=FAMILIES, prepared_features={})
    template = _ipcch_panel().query("year == 2026 and month == 4").reset_index(drop=True).assign(
        population_estimate=[100.0, 50.0], population_reference_period=["2026-04", "2025-01"],
        population_imputation_method=["observed_feature_month", "last_observation_carried_forward"])

    rows, _ = di.ipcch_origin_rows(base, template, origin="2026-10", feature_columns=["CPI"], source_ref=SOURCE_REF)

    assert rows["population_imputation_method"].tolist() == ["last_observation_carried_forward"] * 2
    assert rows["population_estimate"].tolist() == [100.0, 50.0]  # estimate and reference period kept
    assert validate_population_contract(rows, feature_month="2026-10")["last_observation_carried_forward"] == 2


def _population_template(periods, values=(100.0, 50.0)):
    return _ipcch_panel().query("year == 2026 and month == 4").reset_index(drop=True).assign(
        population_estimate=list(values), population_reference_period=list(periods),
        population_imputation_method="observed_feature_month")


def test_population_same_month_reference_stays_observed():
    from model_pipeline.ipcch_launch_runtime.population import validate_population_contract

    base, _ = di.ipcch_base_series(_ipcch_panel(), origin="2026-10", prepared_families=FAMILIES, prepared_features={})
    rows, _ = di.ipcch_origin_rows(base, _population_template(["2026-10", "2026-04"]), origin="2026-10",
                                   feature_columns=["CPI"], source_ref=SOURCE_REF)

    assert rows["population_imputation_method"].tolist() == ["observed_feature_month", "last_observation_carried_forward"]
    assert rows["population_reference_period"].tolist() == ["2026-10", "2026-04"]  # never relabelled
    assert validate_population_contract(rows, feature_month="2026-10") == {
        "observed_feature_month": 1, "last_observation_carried_forward": 1}


def test_population_reference_after_origin_fails():
    from model_pipeline.ipcch_launch_runtime.population import PopulationSelectionError

    base, _ = di.ipcch_base_series(_ipcch_panel(), origin="2026-10", prepared_families=FAMILIES, prepared_features={})

    with pytest.raises(PopulationSelectionError, match="no current or prior population"):
        di.ipcch_origin_rows(base, _population_template(["2026-11", "2026-04"]), origin="2026-10",
                             feature_columns=["CPI"], source_ref=SOURCE_REF)
