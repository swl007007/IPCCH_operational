import math

import pandas as pd
import pytest

from cloud.orchestrator import causal_fill


SOURCE_REF = {"uri": "gs://bucket/prepared/evi.csv", "generation": "7", "sha256": "a" * 64}
PACKAGE = "local-202604-57cb3b981198-510375f58cd8/6m"


def _observations():
    return pd.DataFrame(
        {
            "admin_code": ["0", "0", "0", "10"],
            "month": ["2025-12", "2026-03", "2026-06", "2026-07"],
            "EVI": [0.5, 0.3, 0.6, 0.9],
        }
    )


def _fill(observations=None, **overrides):
    kwargs = dict(
        system="fewsnet",
        id_column="admin_code",
        month_column="month",
        feature_columns=["EVI"],
        roster=["0", "10", "200"],
        months=["2026-04", "2026-05", "2026-06", "2026-07"],
        source_ref=SOURCE_REF,
    )
    kwargs.update(overrides)
    return causal_fill.carry_forward_base_series(
        _observations() if observations is None else observations, **kwargs
    )


def _row(audit, polygon, month, model_feature=None, dependency_month=None):
    rows = audit.loc[audit["polygon_id"].eq(polygon) & audit["feature_month"].eq(month)]
    if model_feature is not None:
        rows = rows.loc[rows["model_feature"].eq(model_feature)]
    if dependency_month is not None:
        rows = rows.loc[rows["dependency_month"].eq(dependency_month)]
    assert len(rows) == 1
    return rows.iloc[0]


def test_fill_uses_only_same_area_past_observations():
    observations = _observations()
    original = observations.copy(deep=True)

    filled, audit = _fill(observations)

    pd.testing.assert_frame_equal(observations, original)  # raw untouched
    values = filled.set_index(["admin_code", "month"])["EVI"]
    # April/May take March, never the later June value.
    assert values[("0", "2026-04")] == 0.3 and values[("0", "2026-05")] == 0.3
    assert values[("0", "2026-06")] == 0.6 and values[("0", "2026-07")] == 0.6
    # Polygon 10 is not filled from polygon 0 before its own first observation.
    assert math.isnan(values[("10", "2026-04")])
    assert values[("10", "2026-07")] == 0.9
    may = _row(audit, "0", "2026-05")
    assert (may["observation_month"], may["staleness_months"], may["fill_method"]) == ("2026-03", 2, "carry_forward")
    assert (may["source_ref"], may["source_sha256"]) == ("gs://bucket/prepared/evi.csv#7", "a" * 64)
    assert pd.isna(may["model_feature"]) and pd.isna(may["imputation_rule"])  # not yet bound
    june = _row(audit, "0", "2026-06")
    assert (june["fill_method"], june["staleness_months"]) == ("observed", 0)
    assert list(audit.columns) == causal_fill.AUDIT_COLUMNS


def test_no_history_stays_missing_without_zero_or_base_imputation():
    filled, audit = _fill()

    assert filled.loc[filled["admin_code"].eq("200"), "EVI"].isna().all()
    row = _row(audit, "200", "2026-04")
    assert row["fill_method"] == "no_eligible_history"
    assert pd.isna(row["observation_month"]) and pd.isna(row["staleness_months"])
    assert pd.isna(row["feature_value_method"])


def _bind(audit, final_missing, rules, **overrides):
    kwargs = dict(
        feature_month="2026-07",
        horizon_months=6,
        model_package_id=PACKAGE,
        final_missing=final_missing,
        imputation_rules=rules,
    )
    kwargs.update(overrides)
    return causal_fill.bind_model_features(
        audit,
        {"EVI": ("EVI", (0,)), "EVI_lag2": ("EVI", (2,)), "EVI_prior2_sum": ("EVI", (1, 2))},
        **kwargs,
    )


def _final_missing(**missing):
    frame = pd.DataFrame(False, index=pd.Index(["0", "10", "200"], name="polygon_id"),
                         columns=["EVI", "EVI_lag2", "EVI_prior2_sum"])
    for column, polygons in missing.items():
        frame.loc[polygons, column] = True
    return frame


def test_final_feature_imputation_is_bound_to_the_package_feature_rule():
    _, audit = _fill()
    # The builder left polygon 200's lag/window and polygon 10's lag2 missing
    # (no eligible history); the saved imputer acts on those FINAL columns.
    final_missing = _final_missing(EVI=["200"], EVI_lag2=["10", "200"], EVI_prior2_sum=["10", "200"])
    rules = {"EVI": "MaxPlusImputer[EVI]", "EVI_lag2": "MaxPlusImputer[EVI_lag2]",
             "EVI_prior2_sum": "MaxPlusImputer[EVI_prior2_sum]"}

    bound = _bind(audit, final_missing, rules)

    lag = _row(bound, "10", "2026-07", "EVI_lag2")
    assert lag["dependency_month"] == "2026-05"
    assert lag["fill_method"] == "no_eligible_history"  # base gap is not relabelled
    assert pd.isna(lag["observation_month"])
    assert (lag["feature_value_method"], lag["imputation_rule"]) == (
        "model_imputation", f"{PACKAGE}:MaxPlusImputer[EVI_lag2]"
    )
    assert (lag["horizon_months"], lag["model_package_id"]) == (6, PACKAGE)
    window = bound.loc[bound["polygon_id"].eq("200") & bound["model_feature"].eq("EVI_prior2_sum")]
    assert sorted(window["dependency_month"]) == ["2026-05", "2026-06"]
    assert window["imputation_rule"].eq(f"{PACKAGE}:MaxPlusImputer[EVI_prior2_sum]").all()
    # Polygon 0's lag2 is computed from a carried-forward base value, not imputed.
    computed = _row(bound, "0", "2026-07", "EVI_lag2")
    assert (computed["feature_value_method"], computed["fill_method"]) == ("computed", "carry_forward")
    assert bool(computed["derived_from_filled"]) is True and pd.isna(computed["imputation_rule"])
    direct = _row(bound, "10", "2026-07", "EVI")
    assert (direct["feature_value_method"], bool(direct["derived_from_filled"])) == ("computed", False)


def test_missing_final_feature_without_package_rule_blocks_release():
    _, audit = _fill()
    final_missing = _final_missing(EVI_lag2=["200"])
    # A rule exists for the base source name only; the final column has none.
    rules = {"EVI": "MaxPlusImputer[EVI]"}

    with pytest.raises(causal_fill.RequiredInputUnavailable, match="EVI_lag2"):
        _bind(audit, final_missing, rules)


def test_dependency_coverage_is_checked_per_polygon():
    _, audit = _fill()
    gap = audit.drop(audit.index[audit["polygon_id"].eq("10") & audit["feature_month"].eq("2026-05")])

    with pytest.raises(ValueError, match=r"incomplete for polygons \['10'\]"):
        _bind(gap, _final_missing(), {})
    with pytest.raises(ValueError, match="incomplete"):
        causal_fill.bind_model_features(
            audit, {"EVI_lag12": ("EVI", (12,))}, feature_month="2026-07", horizon_months=6,
            model_package_id=PACKAGE, final_missing=pd.DataFrame(
                False, index=pd.Index(["0", "10", "200"]), columns=["EVI_lag12"]), imputation_rules={},
        )


@pytest.mark.parametrize("lags", [(-1,), (1.0,), (True,), (), (1, 1)])
def test_lag_arguments_must_be_unique_non_negative_integers(lags):
    _, audit = _fill()

    with pytest.raises(ValueError, match="lags must be"):
        causal_fill.bind_model_features(
            audit, {"EVI_bad": ("EVI", lags)}, feature_month="2026-07", horizon_months=6,
            model_package_id=PACKAGE, final_missing=pd.DataFrame(
                False, index=pd.Index(["0", "10", "200"]), columns=["EVI_bad"]), imputation_rules={},
        )


@pytest.mark.parametrize(
    ("observations", "overrides", "message"),
    [
        (pd.DataFrame({"admin_code": [0], "month": ["2026-04"], "EVI": [1.0]}), {}, "non-empty strings"),
        (pd.DataFrame({"admin_code": ["0", "0"], "month": ["2026-04", "2026-04"], "EVI": [1.0, 2.0]}), {}, "duplicate polygon-month"),
        (pd.DataFrame({"admin_code": ["999"], "month": ["2026-04"], "EVI": [1.0]}), {}, "outside the roster"),
        (pd.DataFrame({"admin_code": ["0"], "month": ["2026-4"], "EVI": [1.0]}), {}, "YYYY-MM"),
        (pd.DataFrame({"admin_code": ["0"], "month": ["2026-04"], "EVI": [math.inf]}), {}, "non-finite"),
        (None, {"roster": ["0", "0"]}, "duplicate native IDs"),
        (None, {"system": "ch"}, "system must be one of"),
        (None, {"source_ref": {"uri": "gs://bucket/evi.csv", "generation": "7"}}, "source_ref"),
        (None, {"source_ref": {**SOURCE_REF, "uri": "gs://bucket/prefix/"}}, "object URI"),
    ],
)
def test_invalid_identity_calendar_and_values_are_rejected(observations, overrides, message):
    with pytest.raises(ValueError, match=message):
        _fill(observations, **overrides)


@pytest.mark.parametrize(
    "observations",
    [
        pd.DataFrame({"admin_code": ["0"], "month": ["2026-04"], "x": [float("nan")]}),
        pd.DataFrame({"admin_code": pd.Series([], dtype=str), "month": pd.Series([], dtype=str),
                      "x": pd.Series([], dtype=float)}),
    ],
)
def test_feature_without_any_observation_is_no_history_then_package_rule_or_block(observations):
    filled, audit = causal_fill.carry_forward_base_series(
        observations, system="ipcch", id_column="admin_code", month_column="month",
        feature_columns=["x"], roster=["0", "00"], months=["2026-04", "2026-10"], source_ref=SOURCE_REF,
    )

    assert filled["x"].isna().all() and filled["admin_code"].tolist() == ["0", "0", "00", "00"]
    assert audit["fill_method"].eq("no_eligible_history").all()
    final_missing = pd.DataFrame({"x": [True, True]}, index=pd.Index(["0", "00"]))
    kwargs = dict(feature_month="2026-10", horizon_months=0, model_package_id="launch_2026_04/scope_0m",
                  final_missing=final_missing)
    bound = causal_fill.bind_model_features(audit, {"x": ("x", (0,))}, imputation_rules={"x": "median:x"}, **kwargs)
    assert bound["feature_value_method"].eq("model_imputation").all()
    assert bound["imputation_rule"].eq("launch_2026_04/scope_0m:median:x").all()
    with pytest.raises(causal_fill.RequiredInputUnavailable, match="no imputation rule"):
        causal_fill.bind_model_features(audit, {"x": ("x", (0,))}, imputation_rules={}, **kwargs)
