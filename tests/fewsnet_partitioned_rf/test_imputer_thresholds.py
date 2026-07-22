from importlib import import_module

import numpy as np
import pytest
from sklearn.exceptions import NotFittedError


def _max_plus_imputer_type():
    module = import_module("fewsnet_partitioned_rf_pipeline.core.preprocessing")
    return module.MaxPlusImputer


def _thresholds_module():
    return import_module("fewsnet_partitioned_rf_pipeline.core.thresholds")


def test_max_plus_imputer_uses_fit_rows_only():
    imputer = _max_plus_imputer_type()(multiplier=100.0).fit(
        [[1.0], [2.0], [None]]
    )

    transformed = imputer.transform([[1000.0], [None]])

    assert transformed[:, 0].tolist() == [1000.0, 200.0]


def test_max_plus_imputer_raises_sklearn_not_fitted_error_before_fit():
    with pytest.raises(NotFittedError, match="MaxPlusImputer"):
        _max_plus_imputer_type()().transform([[1.0]])


def test_max_plus_imputer_records_float64_fit_evidence_and_exact_edge_rules():
    imputer = _max_plus_imputer_type()(multiplier=100.0).fit(
        [
            [1.0, -3.0, None, np.inf, -np.inf],
            [2.0, -1.0, np.nan, 0.0, np.nan],
            [np.nan, -2.0, None, -np.inf, np.inf],
        ]
    )

    assert imputer.n_features_in_ == 5
    assert imputer.feature_mins_.dtype == np.dtype("float64")
    assert imputer.feature_maxs_.dtype == np.dtype("float64")
    assert imputer.impute_values_.dtype == np.dtype("float64")
    np.testing.assert_allclose(
        imputer.feature_mins_,
        np.array([1.0, -3.0, np.nan, 0.0, np.nan]),
        equal_nan=True,
    )
    np.testing.assert_allclose(
        imputer.feature_maxs_,
        np.array([2.0, -1.0, np.nan, 0.0, np.nan]),
        equal_nan=True,
    )
    np.testing.assert_array_equal(
        imputer.impute_values_,
        np.array([200.0, -100.0, 0.0, 100.0, 0.0]),
    )


def test_max_plus_imputer_replaces_both_infinities_during_transform():
    imputer = _max_plus_imputer_type()(multiplier=100.0).fit(
        [[2.0, -1.0, None, 0.0]]
    )

    transformed = imputer.transform([[np.inf, -np.inf, np.nan, np.inf]])

    np.testing.assert_array_equal(
        transformed,
        np.array([[200.0, -100.0, 0.0, 100.0]], dtype=np.float64),
    )
    assert transformed.dtype == np.dtype("float64")
    assert transformed.ndim == 2


def test_max_plus_imputer_rejects_a_different_feature_count():
    imputer = _max_plus_imputer_type()().fit([[1.0, 2.0]])

    with pytest.raises(ValueError, match="feature count"):
        imputer.transform([[1.0]])


def test_max_plus_imputer_requires_two_dimensional_input():
    imputer_type = _max_plus_imputer_type()

    with pytest.raises(ValueError, match="2-D"):
        imputer_type().fit([1.0, 2.0])

    with pytest.raises(ValueError, match="2-D"):
        imputer_type().fit([[1.0]]).transform([1.0])


def test_max_plus_imputer_fit_transform_matches_fitted_transform():
    values = np.array([[1.0, np.nan], [2.0, 0.0]], dtype=np.float32)

    imputer = _max_plus_imputer_type()()
    actual = imputer.fit_transform(values)
    expected = imputer.transform(values)

    np.testing.assert_array_equal(actual, expected)
    assert actual.dtype == np.dtype("float64")


def test_max_plus_imputer_accepts_sklearn_style_X_and_y_keywords():
    imputer = _max_plus_imputer_type()()

    fit_transformed = imputer.fit_transform(X=[[None]], y=np.array([1]))
    transformed = imputer.transform(X=[[np.inf]])

    np.testing.assert_array_equal(fit_transformed, np.array([[0.0]]))
    np.testing.assert_array_equal(transformed, np.array([[0.0]]))


def test_threshold_search_chooses_higher_threshold_on_f1_tie():
    result = _thresholds_module().select_max_f1_threshold(
        y_true=np.array([0, 1]),
        y_probability=np.array([0.10, 0.90]),
    )

    assert result.threshold == 0.90
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.support == 2
    assert result.positive_cases == 1
    assert result.fallback_reason is None


def test_threshold_search_uses_inclusive_shared_grid_and_reports_metrics():
    result = _thresholds_module().select_max_f1_threshold(
        y_true=np.array([1, 0, 1]),
        y_probability=np.array([0.90, 0.80, 0.70]),
    )

    assert result.threshold == 0.70
    assert result.precision == pytest.approx(2 / 3)
    assert result.recall == 1.0
    assert result.f1 == pytest.approx(0.8)
    assert result.support == 3
    assert result.positive_cases == 2
    assert result.fallback_reason is None


def test_threshold_search_filters_nonfinite_probabilities_before_scoring():
    result = _thresholds_module().select_max_f1_threshold(
        y_true=np.array([1, 0, 1, 0, 1]),
        y_probability=np.array([0.90, np.nan, np.inf, -np.inf, 0.40]),
    )

    assert result.threshold == 0.40
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.support == 2
    assert result.positive_cases == 2
    assert result.fallback_reason is None


def test_threshold_falls_back_when_validation_has_no_observations():
    result = _thresholds_module().select_max_f1_threshold(
        np.array([1, 0, 1]),
        np.array([np.nan, np.inf, -np.inf]),
    )

    assert result.threshold == 0.50
    assert result.precision is None
    assert result.recall is None
    assert result.f1 is None
    assert result.support == 0
    assert result.positive_cases == 0
    assert result.fallback_reason == "no_validation_observations"


def test_threshold_falls_back_when_validation_has_no_positive_cases():
    result = _thresholds_module().select_max_f1_threshold(
        np.array([0, 0]),
        np.array([0.2, 0.8]),
    )

    assert result.threshold == 0.50
    assert result.precision is None
    assert result.recall is None
    assert result.f1 is None
    assert result.support == 2
    assert result.positive_cases == 0
    assert result.fallback_reason == "no_validation_positive_cases"


def test_threshold_falls_back_when_validation_has_no_finite_f1(monkeypatch):
    thresholds = _thresholds_module()
    monkeypatch.setattr(thresholds, "f1_score", lambda *args, **kwargs: np.nan)

    result = thresholds.select_max_f1_threshold(
        np.array([0, 1]),
        np.array([0.2, 0.8]),
    )

    assert result.threshold == 0.50
    assert result.precision is None
    assert result.recall is None
    assert result.f1 is None
    assert result.support == 2
    assert result.positive_cases == 1
    assert result.fallback_reason == "no_finite_validation_f1"


def test_threshold_search_rejects_shape_mismatches():
    select_threshold = _thresholds_module().select_max_f1_threshold

    with pytest.raises(ValueError, match="same shape"):
        select_threshold(np.array([0, 1]), np.array([0.5]))

    with pytest.raises(ValueError, match="one-dimensional"):
        select_threshold(
            np.array([[0, 1]]),
            np.array([[0.2, 0.8]]),
        )
