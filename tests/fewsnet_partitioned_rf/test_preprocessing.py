import re
import warnings
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import fewsnet_partitioned_rf_pipeline.core.preprocessing as preprocessing
from fewsnet_partitioned_rf_pipeline.core.preprocessing import Stage3FeatureBuilder


APPROVED_REFERENCE_FEATURES = (
    "FEWSNET_admin_code",
    "lat",
    "lon",
    "month",
    "fews_ha",
    "fews_ipc_crisis_lag_4",
    "fews_ipc_lag_12",
    "WFP_Price_m4",
    "WFP_Price_m12",
    "nightlight_m12",
    "EVI_l12",
)


def raw_panel_fixture() -> pd.DataFrame:
    rows = []
    configurations = (
        (20, "ZZ", {pd.Period("2020-05", freq="M")}),
        (10, "AA", set()),
    )
    for admin_code, iso, missing_months in configurations:
        for feature_month in pd.period_range("2020-01", "2021-03", freq="M"):
            if feature_month in missing_months:
                continue
            ordinal = feature_month.ordinal - pd.Period("2020-01", freq="M").ordinal
            rows.append(
                {
                    "unit_name": f"area-{admin_code}",
                    "ADMIN0": f"country-{iso}",
                    "ADMIN1": "admin-1",
                    "ADMIN2": "admin-2",
                    "ADMIN3": "admin-3",
                    "FEWSNET_admin_code": admin_code,
                    "ISO": iso,
                    "lat": float(admin_code),
                    "lon": float(-admin_code),
                    "month": feature_month.month,
                    "AEZ_9000": "True" if admin_code == 10 else "False",
                    "WFP_Price": float(ordinal + 1),
                    "nightlight": float(100 + ordinal),
                    "EVI": float(1000 + ordinal),
                    "fews_ipc": float((ordinal % 5) + 1),
                    "fews_ipc_crisis": float(ordinal % 2),
                    "date": feature_month.start_time,
                    "fews_ha": float(ordinal + admin_code),
                    "fews_proj_med": 3.0,
                    "ISO3": f"{iso}X",
                    "fews_ipc_adjusted": 2.0,
                    "fews_proj_med_adjusted": 3.0,
                    "fews_proj_near": 2.0,
                    "fews_proj_near_ha": 100.0,
                    "fews_proj_med_ha": 200.0,
                }
            )
    return pd.DataFrame(rows)


def _row(frame: pd.DataFrame, admin_code: str, feature_month: str) -> pd.Series:
    selected = frame.loc[
        (frame["admin_code"] == admin_code)
        & (frame["feature_month"] == pd.Period(feature_month, freq="M"))
    ]
    assert len(selected) == 1
    return selected.iloc[0]


def test_feature_builder_preserves_approved_reference_predictors_and_calendar_lags():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()

    contract = builder.fit(panel)
    frame = builder.transform(panel, contract)

    for name in APPROVED_REFERENCE_FEATURES:
        assert name in contract.feature_columns
    assert "fews_ipc_crisis" not in contract.feature_columns
    assert "fews_ipc" not in contract.feature_columns
    assert "fews_proj_med" not in contract.feature_columns
    assert not any(re.search(r"_lag(?:0|6|12)m$", name) for name in contract.feature_columns)

    june = _row(frame, "20", "2020-06")
    february = _row(frame, "20", "2020-02")
    january = _row(frame, "20", "2020-01")
    assert june["fews_ipc_crisis_lag_4"] == february["fews_ipc_crisis"]
    assert june["fews_ipc_crisis_lag_4"] != january["fews_ipc_crisis"]
    assert pd.isna(june["WFP_Price_m4"])
    assert pd.isna(june["EVI_l1"])

    assert frame.columns.tolist() == [
        "admin_code",
        "feature_month",
        "fews_ipc_crisis",
        *contract.feature_columns,
    ]
    assert frame["feature_month"].dtype == pd.PeriodDtype(freq="M")


def test_fit_records_sorted_encodings_float_schema_and_approved_exclusions():
    panel = raw_panel_fixture()

    contract = Stage3FeatureBuilder().fit(panel)

    assert contract.schema_version == "fewsnet-feature-contract-v1"
    assert contract.transformation_version == "stage3-direct-alignment-v1"
    assert contract.iso_mapping == {"AA": 0, "ZZ": 1}
    assert set(contract.feature_dtypes) == {"float64"}
    assert len(contract.feature_columns) == len(contract.feature_dtypes)
    assert len(contract.source_columns_sha256) == 64
    assert len(contract.feature_schema_sha256) == 64
    assert tuple(name for name in contract.feature_columns if name.startswith("year_")) == (
        "year_2020",
        "year_2021",
    )
    assert tuple(name for name in contract.feature_columns if name.startswith("month_")) == tuple(
        f"month_{month}" for month in range(1, 13)
    )
    for excluded in (
        "unit_name",
        "ADMIN0",
        "ADMIN1",
        "ADMIN2",
        "ADMIN3",
        "ISO",
        "ISO3",
        "date",
        "fews_ipc_crisis",
        "fews_ipc",
        "fews_proj_med",
        "AEZ_group",
        "ISO_encoded",
        "AEZ_country_group",
    ):
        assert excluded not in contract.feature_columns


def test_transform_rejects_missing_required_raw_inputs_and_ignores_extra_sources():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)

    with pytest.raises(ValueError, match="lat"):
        builder.transform(panel.drop(columns=["lat"]), contract)

    expected = builder.transform(panel, contract)
    actual = builder.transform(panel.assign(undeclared_new_source=999), contract)
    assert_frame_equal(actual, expected)


def test_transform_rejects_duplicate_unknown_or_missing_frozen_feature_names():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)

    duplicate = replace(
        contract,
        feature_columns=contract.feature_columns + ("lat",),
        feature_dtypes=contract.feature_dtypes + ("float64",),
    )
    with pytest.raises(ValueError, match="duplicate.*lat"):
        builder.transform(panel, duplicate)

    unknown_columns = list(contract.feature_columns)
    unknown_columns[unknown_columns.index("lat")] = "invented_feature"
    unknown = replace(contract, feature_columns=tuple(unknown_columns))
    with pytest.raises(ValueError, match="invented_feature|feature schema checksum"):
        builder.transform(panel, unknown)

    lat_index = contract.feature_columns.index("lat")
    missing = replace(
        contract,
        feature_columns=contract.feature_columns[:lat_index]
        + contract.feature_columns[lat_index + 1 :],
        feature_dtypes=contract.feature_dtypes[:lat_index]
        + contract.feature_dtypes[lat_index + 1 :],
    )
    with pytest.raises(ValueError, match="lat|feature schema checksum"):
        builder.transform(panel, missing)


def test_transform_rejects_tampered_contract_checksums():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)

    with pytest.raises(ValueError, match="source column checksum"):
        builder.transform(panel, replace(contract, source_columns_sha256="0" * 64))
    with pytest.raises(ValueError, match="feature schema checksum"):
        builder.transform(panel, replace(contract, feature_schema_sha256="0" * 64))


def test_transform_rejects_unseen_iso_year_and_month_categories():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)

    unseen_iso = panel.copy()
    unseen_iso.loc[unseen_iso.index[0], "ISO"] = "MM"
    with pytest.raises(ValueError, match="MM"):
        builder.transform(unseen_iso, contract)

    unseen_year = panel.copy()
    unseen_year.loc[unseen_year.index[0], "date"] = pd.Timestamp("2022-01-01")
    with pytest.raises(ValueError, match="year.*2022|2022"):
        builder.transform(unseen_year, contract)

    no_december = panel.loc[pd.to_datetime(panel["date"]).dt.month != 12].copy()
    no_december_contract = builder.fit(no_december)
    with pytest.raises(ValueError, match="month.*12|month_12"):
        builder.transform(panel, no_december_contract)


def test_transform_converts_infinity_to_nan_and_rejects_noncoercible_predictors():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)

    infinite = panel.copy()
    infinite.loc[infinite.index[0], "lat"] = np.inf
    infinite.loc[infinite.index[1], "lon"] = -np.inf
    transformed = builder.transform(infinite, contract)
    assert pd.isna(transformed.loc[0, "lat"])
    assert pd.isna(transformed.loc[1, "lon"])

    invalid = panel.copy()
    invalid["lat"] = invalid["lat"].astype(object)
    invalid.loc[invalid.index[0], "lat"] = "not-a-number"
    with pytest.raises(ValueError, match="lat"):
        builder.transform(invalid, contract)


def test_transform_normalizes_aez_booleans_without_scaling_predictors():
    panel = raw_panel_fixture()
    missing_aez_index = panel.index[-1]
    panel.loc[missing_aez_index, "AEZ_9000"] = np.nan
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)

    frame = builder.transform(panel, contract)

    first_admin_10 = _row(frame, "10", "2020-01")
    first_admin_20 = _row(frame, "20", "2020-01")
    assert first_admin_10["AEZ_9000"] == 1.0
    assert first_admin_20["AEZ_9000"] == 0.0
    assert first_admin_10["FEWSNET_admin_code"] == 10.0
    assert first_admin_20["lat"] == 20.0
    assert first_admin_20["lon"] == -20.0
    assert pd.isna(frame.loc[missing_aez_index, "AEZ_9000"])


def test_transform_rejects_duplicate_area_month_keys():
    panel = raw_panel_fixture()
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)
    duplicate_panel = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate.*admin_code.*feature_month"):
        builder.transform(duplicate_panel, contract)


def test_transform_sorts_canonical_keys_before_derivation_and_restores_input_order(
    monkeypatch,
):
    panel = raw_panel_fixture().sample(frac=1, random_state=5).reset_index(drop=True)
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)
    observed_derivation_keys: list[list[tuple[str, pd.Period]]] = []
    original_add_calendar_lag = preprocessing.add_calendar_lag
    original_add_calendar_rolling_sum = preprocessing._add_calendar_rolling_sum

    def record_lag_keys(frame, value_column, months, output_column):
        observed_derivation_keys.append(
            list(zip(frame["admin_code"], frame["feature_month"], strict=True))
        )
        return original_add_calendar_lag(
            frame,
            value_column,
            months,
            output_column,
        )

    def record_rolling_keys(frame, value_column, window, output_column):
        observed_derivation_keys.append(
            list(zip(frame["admin_code"], frame["feature_month"], strict=True))
        )
        return original_add_calendar_rolling_sum(
            frame,
            value_column,
            window,
            output_column,
        )

    monkeypatch.setattr(preprocessing, "add_calendar_lag", record_lag_keys)
    monkeypatch.setattr(
        preprocessing,
        "_add_calendar_rolling_sum",
        record_rolling_keys,
    )

    result = builder.transform(panel, contract)

    assert observed_derivation_keys
    for keys in observed_derivation_keys:
        assert keys == sorted(keys)
    expected_identity = pd.DataFrame(
        {
            "admin_code": panel["FEWSNET_admin_code"].astype(str),
            "feature_month": pd.to_datetime(panel["date"]).dt.to_period("M"),
        }
    )
    assert_frame_equal(
        result[["admin_code", "feature_month"]],
        expected_identity,
    )


def test_transform_does_not_emit_dataframe_fragmentation_warnings():
    panel = raw_panel_fixture().assign(
        **{
            f"approved_numeric_source_{index}": float(index)
            for index in range(80)
        }
    )
    builder = Stage3FeatureBuilder()
    contract = builder.fit(panel)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", pd.errors.PerformanceWarning)
        builder.transform(panel, contract)

    assert not [
        warning
        for warning in captured
        if issubclass(warning.category, pd.errors.PerformanceWarning)
    ]
