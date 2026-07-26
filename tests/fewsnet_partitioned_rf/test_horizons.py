import pandas as pd
import pytest

from fewsnet_partitioned_rf_pipeline.core.horizons import (
    align_horizon,
    select_latest_inference_frame,
    select_training_window,
    split_threshold_window,
)


def feature_frame_fixture() -> pd.DataFrame:
    rows = []
    for admin_code in ("B", "A"):
        for feature_month in pd.period_range("2023-03", "2026-04", freq="M"):
            target = (
                float(feature_month.year * 100 + feature_month.month)
                if feature_month <= pd.Period("2026-02", freq="M")
                else None
            )
            rows.append(
                {
                    "admin_code": admin_code,
                    "feature_month": str(feature_month),
                    "fews_ipc_crisis": target,
                    "predictor": float(feature_month.ordinal),
                }
            )
    return pd.DataFrame(reversed(rows))


def aligned_fixture() -> pd.DataFrame:
    rows = []
    for admin_code in ("B", "A"):
        for target_month in pd.period_range("2022-12", "2026-03", freq="M"):
            rows.append(
                {
                    "admin_code": admin_code,
                    "feature_month": str(target_month),
                    "target_month": target_month.start_time,
                    "fews_ipc_crisis": float(target_month.month % 2),
                    "predictor": float(target_month.ordinal),
                }
            )
    return pd.DataFrame(reversed(rows))


def sparse_aligned_fixture() -> tuple[pd.DataFrame, list[pd.Period]]:
    rows: list[dict[str, object]] = []
    target_months = [
        pd.Period("2018-01", freq="M") + 2 * index
        for index in range(42)
    ]
    for admin_code in ("B", "A"):
        for month_index, target_month in enumerate(target_months):
            rows.append(
                {
                    "admin_code": admin_code,
                    "feature_month": str(target_month),
                    "target_month": target_month.start_time,
                    "fews_ipc_crisis": float(month_index % 2),
                    "predictor": float(target_month.ordinal),
                }
            )
    return pd.DataFrame(reversed(rows)), target_months


def test_horizon_alignment_uses_keyed_feature_and_target_months():
    result = align_horizon(feature_frame_fixture(), horizon_months=6)

    row = result.frame.loc[result.frame["admin_code"] == "A"].iloc[-1]
    assert str(row["feature_month"]) == "2025-08"
    assert str(row["target_month"]) == "2026-02"
    assert row["fews_ipc_crisis"] == 202602.0
    assert result.dropped_rows_by_reason == {
        "missing_target_row": 12,
        "null_target_value": 4,
    }
    assert list(
        result.frame[["admin_code", "feature_month"]].itertuples(
            index=False,
            name=None,
        )
    ) == sorted(
        result.frame[["admin_code", "feature_month"]].itertuples(
            index=False,
            name=None,
        )
    )


def test_horizon_alignment_rejects_duplicate_area_month_keys():
    frame = feature_frame_fixture()
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)

    with pytest.raises(
        ValueError,
        match=r"duplicate admin_code \+ feature_month",
    ):
        align_horizon(duplicate, horizon_months=6)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("admin_code", None, "admin_code contains missing or blank values"),
        ("admin_code", "  ", "admin_code contains missing or blank values"),
        ("feature_month", None, "feature_month contains invalid or missing values"),
        (
            "feature_month",
            "not-a-month",
            "feature_month contains invalid or missing values",
        ),
    ],
)
def test_horizon_alignment_rejects_invalid_identity_or_month_values(
    column,
    value,
    message,
):
    frame = feature_frame_fixture()
    frame.loc[frame.index[0], column] = value

    with pytest.raises(ValueError, match=message):
        align_horizon(frame, horizon_months=6)


def test_horizon_alignment_rejects_pandas_missing_month_identity():
    frame = pd.DataFrame(
        {
            "admin_code": ["A"],
            "feature_month": pd.Series([pd.NA], dtype="object"),
            "fews_ipc_crisis": [1.0],
        }
    )

    with pytest.raises(
        ValueError,
        match="feature_month contains invalid or missing values",
    ):
        align_horizon(frame, horizon_months=0)


@pytest.mark.parametrize("missing_column", ["admin_code", "feature_month", "fews_ipc_crisis"])
def test_horizon_alignment_rejects_missing_required_columns(missing_column):
    with pytest.raises(ValueError, match=missing_column):
        align_horizon(
            feature_frame_fixture().drop(columns=[missing_column]),
            horizon_months=6,
        )


def test_horizon_alignment_rejects_unsupported_horizons():
    with pytest.raises(ValueError, match="0, 6, and 12"):
        align_horizon(feature_frame_fixture(), horizon_months=3)


def test_current_36_month_and_six_month_windows_are_exact():
    training = select_training_window(
        aligned_fixture(),
        latest_label_month="2026-02",
        months=36,
    )
    fit, validation = split_threshold_window(training, validation_months=6)

    assert str(training["target_month"].min()) == "2023-03"
    assert str(training["target_month"].max()) == "2026-02"
    assert str(fit["target_month"].max()) == "2025-08"
    assert str(validation["target_month"].min()) == "2025-09"
    assert training["target_month"].dtype == pd.PeriodDtype(freq="M")
    assert validation["target_month"].nunique() == 6
    assert len(validation) == 12


def test_training_window_selects_latest_36_sparse_labeled_periods():
    frame, target_months = sparse_aligned_fixture()
    latest_label_month = target_months[-2]
    eligible_periods = [
        period for period in target_months if period <= latest_label_month
    ]
    expected_periods = eligible_periods[-36:]

    training = select_training_window(
        frame,
        latest_label_month=latest_label_month,
        months=36,
    )

    assert sorted(training["target_month"].unique()) == expected_periods
    assert len(training) == 72
    assert training["target_month"].nunique() == 36
    assert not training["target_month"].eq(target_months[-1]).any()
    assert list(
        training[["admin_code", "feature_month"]].itertuples(
            index=False,
            name=None,
        )
    ) == sorted(
        training[["admin_code", "feature_month"]].itertuples(
            index=False,
            name=None,
        )
    )


def test_training_window_requires_the_latest_label_boundary_period():
    frame, target_months = sparse_aligned_fixture()
    unlabeled_boundary = target_months[-2] + 1

    with pytest.raises(
        ValueError,
        match="latest_label_month must be represented",
    ):
        select_training_window(
            frame,
            latest_label_month=unlabeled_boundary,
            months=36,
        )


def test_training_window_requires_requested_distinct_period_count():
    frame, target_months = sparse_aligned_fixture()
    retained_periods = set(target_months[-35:])
    only_35 = frame.loc[
        pd.to_datetime(frame["target_month"])
        .dt.to_period("M")
        .isin(retained_periods)
    ]

    with pytest.raises(
        ValueError,
        match="at least 36 distinct labeled target_month periods",
    ):
        select_training_window(
            only_35,
            latest_label_month=target_months[-1],
            months=36,
        )


@pytest.mark.parametrize("months", [0, -1, True, 6.5])
def test_training_window_requires_a_positive_integer_month_count(months):
    with pytest.raises(ValueError, match="months must be a positive integer"):
        select_training_window(
            aligned_fixture(),
            latest_label_month="2026-02",
            months=months,
        )


@pytest.mark.parametrize("validation_months", [0, -1, True, 2.5])
def test_threshold_split_requires_a_positive_integer_month_count(
    validation_months,
):
    with pytest.raises(
        ValueError,
        match="validation_months must be a positive integer",
    ):
        split_threshold_window(
            aligned_fixture(),
            validation_months=validation_months,
        )


def test_threshold_split_requires_fit_history_before_validation_periods():
    six_periods = aligned_fixture().loc[
        lambda frame: pd.to_datetime(frame["target_month"])
        >= pd.Timestamp("2025-10-01")
    ]

    with pytest.raises(
        ValueError,
        match="at least 7 distinct target_month periods",
    ):
        split_threshold_window(six_periods, validation_months=6)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        (
            "target_month",
            "invalid",
            "target_month contains invalid or missing values",
        ),
        (
            "latest_label_month",
            "invalid",
            "latest_label_month contains an invalid or missing value",
        ),
    ],
)
def test_training_window_rejects_invalid_target_or_boundary_months(
    column,
    value,
    message,
):
    frame = aligned_fixture()
    latest_label_month = "2026-02"
    if column == "target_month":
        frame[column] = frame[column].astype("object")
        frame.loc[frame.index[0], column] = value
    else:
        latest_label_month = value

    with pytest.raises(ValueError, match=message):
        select_training_window(
            frame,
            latest_label_month=latest_label_month,
            months=36,
        )


def test_latest_inference_frame_uses_only_2026_04_for_all_horizons():
    frame = feature_frame_fixture()

    for horizon, target in ((0, "2026-04"), (6, "2026-10"), (12, "2027-04")):
        latest = select_latest_inference_frame(frame, "2026-04", horizon)

        assert set(latest["feature_month"].astype(str)) == {"2026-04"}
        assert set(latest["target_month"].astype(str)) == {target}
        assert latest["admin_code"].tolist() == ["A", "B"]
        assert latest["admin_code"].is_unique
        assert latest["fews_ipc_crisis"].isna().all()
        assert latest["feature_month"].dtype == pd.PeriodDtype(freq="M")
        assert latest["target_month"].dtype == pd.PeriodDtype(freq="M")


def test_latest_inference_frame_requires_the_complete_snapshot_admin_universe():
    frame = feature_frame_fixture()
    incomplete = frame.loc[
        ~(
            frame["admin_code"].eq("A")
            & frame["feature_month"].eq("2026-04")
        )
    ]

    with pytest.raises(
        ValueError,
        match="latest feature month 2026-04 is missing.*A",
    ):
        select_latest_inference_frame(incomplete, "2026-04", 6)


def test_latest_inference_frame_rejects_empty_authoritative_universe():
    empty = pd.DataFrame(
        columns=[
            "admin_code",
            "feature_month",
            "fews_ipc_crisis",
            "predictor",
        ]
    )

    with pytest.raises(
        ValueError,
        match="authoritative admin_code universe is empty",
    ):
        select_latest_inference_frame(empty, "2026-04", 6)


def test_latest_inference_frame_rejects_duplicate_area_month_keys():
    frame = feature_frame_fixture()
    latest_row = frame.loc[
        frame["feature_month"].eq("2026-04")
    ].iloc[[0]]

    with pytest.raises(
        ValueError,
        match=r"duplicate admin_code \+ feature_month",
    ):
        select_latest_inference_frame(
            pd.concat([frame, latest_row], ignore_index=True),
            "2026-04",
            6,
        )


def test_latest_inference_frame_rejects_invalid_latest_feature_month():
    with pytest.raises(
        ValueError,
        match="latest_feature_month contains an invalid or missing value",
    ):
        select_latest_inference_frame(
            feature_frame_fixture(),
            "invalid",
            6,
        )
