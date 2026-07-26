import hashlib

import numpy as np
import pandas as pd
import pytest

from fewsnet_partitioned_rf_pipeline.local import outputs as local_outputs
from fewsnet_partitioned_rf_pipeline.local.outputs import (
    LOCAL_PREDICTION_COLUMNS,
    build_identity_population_frame,
    enrich_local_predictions,
    validate_local_prediction_frame,
    validate_local_prediction_suite,
    write_local_prediction_csv,
)


SUITE_VERSION = "local-202604-111111111111-222222222222"


def population_panel_fixture() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for area_index, admin_code in enumerate(("0", "1", "2", "3")):
        for period in pd.PeriodIndex(("2024-09", "2024-10", "2026-04"), freq="M"):
            rows.append(
                {
                    "FEWSNET_admin_code": admin_code,
                    "ADMIN0": f"country-{area_index // 2}",
                    "ADMIN1": f"admin1-{area_index // 2}",
                    "ADMIN2": f"admin2-{area_index}",
                    "ADMIN3": f"admin3-{area_index}",
                    "ISO3": "SSD",
                    "lat": 5.0 + area_index,
                    "lon": 25.0 + area_index,
                    "date": period.to_timestamp().strftime("%Y-%m-%d"),
                    "pop": (
                        float(1000 + area_index * 100)
                        if area_index < 2
                        and period <= pd.Period("2024-10", freq="M")
                        else None
                    ),
                }
            )
    return pd.DataFrame(rows)


def formal_prediction_fixture(horizon_months: int) -> pd.DataFrame:
    target_month = str(pd.Period("2026-04", freq="M") + horizon_months)
    probabilities = np.asarray((0.20, 0.60, 0.80, 0.40))
    threshold = 0.50
    return pd.DataFrame(
        {
            "admin_code": ("0", "1", "2", "3"),
            "feature_month": ("2026-04",) * 4,
            "target_month": (target_month,) * 4,
            "horizon_months": (horizon_months,) * 4,
            "probability_crisis": probabilities,
            "predicted_crisis": (probabilities >= threshold).astype(int),
            "threshold": (threshold,) * 4,
            "cluster_id": pd.array((5, 5, 1, None), dtype="Int64"),
            "prediction_source": (
                "partition_model",
                "partition_model",
                "pooled_small_partition",
                "pooled_unmapped",
            ),
            "suite_version": (SUITE_VERSION,) * 4,
            "vertex_model_resource_name": ("",) * 4,
            "vertex_model_version_id": ("",) * 4,
        }
    )


def enriched_prediction_fixture(horizon_months: int) -> pd.DataFrame:
    identity, _ = build_identity_population_frame(
        population_panel_fixture(),
        "2026-04",
    )
    horizon_key = {0: "0m", 6: "6m", 12: "12m"}[horizon_months]
    return enrich_local_predictions(
        formal_prediction_fixture(horizon_months),
        identity,
        model_artifact_path=f"model_artifacts/{SUITE_VERSION}/{horizon_key}",
        source_input="/tmp/panel.csv",
    )


def validate_0m(frame: pd.DataFrame) -> dict[str, object]:
    return validate_local_prediction_frame(
        frame,
        expected_admin_codes=("0", "1", "2", "3"),
        feature_month="2026-04",
        target_month="2026-04",
        horizon_months=0,
        suite_version=SUITE_VERSION,
    )


def test_population_uses_latest_raw_observation_and_never_model_imputation():
    panel = population_panel_fixture()
    identity, summary = build_identity_population_frame(panel, "2026-04")

    by_admin = identity.set_index("admin_code")
    assert by_admin.loc["0", "population"] == 1000.0
    assert by_admin.loc["0", "population_reference_period"] == "2024-10"
    assert by_admin.loc["0", "population_source"] == "raw_last_observed"
    assert pd.isna(by_admin.loc["2", "population"])
    assert pd.isna(by_admin.loc["2", "population_reference_period"])
    assert by_admin.loc["2", "population_source"] == "missing_raw"
    assert identity["admin_code"].tolist() == ["0", "1", "2", "3"]
    assert summary.raw_last_observed_count == 2
    assert summary.missing_raw_count == 2
    assert summary.missing_admin_codes == ("2", "3")
    assert summary.reference_period_counts == {"2024-10": 2}


@pytest.mark.parametrize("bad_population", ("not-a-number", np.inf, -1.0))
def test_population_rejects_invalid_nonnull_raw_values(bad_population):
    panel = population_panel_fixture()
    panel["pop"] = panel["pop"].astype("object")
    panel.loc[0, "pop"] = bad_population

    with pytest.raises(ValueError, match="population.*finite nonnegative"):
        build_identity_population_frame(panel, "2026-04")


def test_population_requires_one_feature_month_identity_row_per_admin():
    panel = population_panel_fixture()
    feature_row = panel.loc[
        (panel["FEWSNET_admin_code"] == "0")
        & panel["date"].str.startswith("2026-04")
    ]
    duplicate = pd.concat([panel, feature_row], ignore_index=True)
    with pytest.raises(ValueError, match="exactly one.*feature month"):
        build_identity_population_frame(duplicate, "2026-04")

    missing = panel.drop(feature_row.index)
    with pytest.raises(ValueError, match="exactly one.*feature month"):
        build_identity_population_frame(missing, "2026-04")


def test_enriched_predictions_have_exact_local_columns_and_no_ipcch_fields():
    formal = formal_prediction_fixture(horizon_months=6)
    identity, _ = build_identity_population_frame(
        population_panel_fixture(),
        "2026-04",
    )
    enriched = enrich_local_predictions(
        formal,
        identity,
        model_artifact_path="model_artifacts/local-suite/6m",
        source_input="/tmp/panel.csv",
    )

    assert enriched.columns.tolist() == list(LOCAL_PREDICTION_COLUMNS)
    assert enriched["admin_code"].tolist() == ["0", "1", "2", "3"]
    assert not any(name.startswith("phase") for name in enriched.columns)
    assert "prediction_uncertainty" not in enriched.columns
    assert "vertex_model_resource_name" not in enriched.columns
    assert "vertex_model_version_id" not in enriched.columns


def test_enrichment_requires_the_frozen_formal_contract_and_blank_vertex_identity():
    identity, _ = build_identity_population_frame(
        population_panel_fixture(),
        "2026-04",
    )
    extra = formal_prediction_fixture(0).assign(unexpected="value")
    with pytest.raises(ValueError, match="exact formal prediction columns"):
        enrich_local_predictions(
            extra,
            identity,
            model_artifact_path="model_artifacts/local-suite/0m",
            source_input="/tmp/panel.csv",
        )

    vertex = formal_prediction_fixture(0)
    vertex.loc[0, "vertex_model_resource_name"] = "projects/fake/models/fake"
    with pytest.raises(ValueError, match="Vertex fields must be blank"):
        enrich_local_predictions(
            vertex,
            identity,
            model_artifact_path="model_artifacts/local-suite/0m",
            source_input="/tmp/panel.csv",
        )


def test_prediction_validation_enforces_probability_threshold_and_row_order():
    frame = enriched_prediction_fixture(horizon_months=0)
    summary = validate_0m(frame)
    assert summary["row_count"] == 4
    assert summary["probability_min"] == 0.20
    assert summary["probability_max"] == 0.80
    assert summary["probability_mean"] == pytest.approx(0.50)
    assert summary["threshold"] == 0.50
    assert summary["positive_label_count"] == 2
    assert summary["fallback_counts"] == {
        "pooled_unmapped": 1,
        "pooled_small_partition": 1,
        "pooled_single_class": 0,
        "pooled_missing_partition_model": 0,
    }
    assert summary["population_counts"] == {
        "raw_last_observed": 2,
        "missing_raw": 2,
    }
    assert summary["missing_admin_codes"] == ["2", "3"]

    invalid = frame.copy()
    invalid.loc[0, "predicted_crisis"] = 1 - invalid.loc[0, "predicted_crisis"]
    with pytest.raises(ValueError, match="threshold-to-label"):
        validate_0m(invalid)


def test_prediction_validation_rejects_target_month_horizon_mismatch():
    frame = enriched_prediction_fixture(0)
    frame["target_month"] = "2026-05"

    with pytest.raises(ValueError, match="target_month.*predictive horizon"):
        validate_local_prediction_frame(
            frame,
            expected_admin_codes=("0", "1", "2", "3"),
            feature_month="2026-04",
            target_month="2026-05",
            horizon_months=0,
            suite_version=SUITE_VERSION,
        )


def test_three_scope_validation_requires_identical_identity_and_target_semantics():
    predictions = {
        "0m": enriched_prediction_fixture(horizon_months=0),
        "6m": enriched_prediction_fixture(horizon_months=6),
        "12m": enriched_prediction_fixture(horizon_months=12),
    }
    suite = validate_local_prediction_suite(
        predictions,
        expected_admin_codes=("0", "1", "2", "3"),
        feature_month="2026-04",
        suite_version=SUITE_VERSION,
    )
    assert suite["target_months"] == {
        "0m": "2026-04",
        "6m": "2026-10",
        "12m": "2027-04",
    }
    assert list(suite["horizon_summaries"]) == ["0m", "6m", "12m"]

    predictions["12m"] = predictions["12m"].iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="identical admin_code row order"):
        validate_local_prediction_suite(
            predictions,
            expected_admin_codes=("0", "1", "2", "3"),
            feature_month="2026-04",
            suite_version=SUITE_VERSION,
        )


def test_prediction_validation_rejects_duplicate_or_missing_area():
    frame = enriched_prediction_fixture(0)
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate admin_code"):
        validate_0m(duplicate)
    with pytest.raises(ValueError, match="expected admin_code row order"):
        validate_0m(frame.iloc[:-1].copy())


def test_prediction_validation_rejects_nonfinite_probability_and_threshold_drift():
    frame = enriched_prediction_fixture(0)
    nonfinite = frame.copy()
    nonfinite.loc[0, "probability_crisis"] = np.inf
    with pytest.raises(ValueError, match="finite"):
        validate_0m(nonfinite)
    threshold_drift = frame.copy()
    threshold_drift.loc[0, "threshold"] = 0.70
    with pytest.raises(ValueError, match="one constant threshold"):
        validate_0m(threshold_drift)


def test_prediction_validation_rejects_invalid_source_and_population_pairing():
    frame = enriched_prediction_fixture(0)
    invalid_source = frame.copy()
    invalid_source.loc[0, "cluster_id"] = pd.NA
    invalid_source.loc[0, "prediction_source"] = "partition_model"
    with pytest.raises(ValueError, match="cluster/source"):
        validate_0m(invalid_source)
    invalid_population = frame.copy()
    invalid_population.loc[2, "population"] = 123.0
    with pytest.raises(ValueError, match="population provenance"):
        validate_0m(invalid_population)


def test_prediction_validation_rejects_prohibited_extra_field():
    frame = enriched_prediction_fixture(0)
    frame["phase3_worse_probability"] = 0.25
    with pytest.raises(ValueError, match="exact columns"):
        validate_0m(frame)


def test_prediction_validation_rejects_coordinate_and_schema_violations():
    invalid_latitude = enriched_prediction_fixture(0)
    invalid_latitude.loc[0, "lat"] = 90.1
    with pytest.raises(ValueError, match=r"latitude.*\[-90, 90\]"):
        validate_0m(invalid_latitude)

    invalid_cluster = enriched_prediction_fixture(0)
    invalid_cluster.loc[0, "cluster_id"] = 17
    with pytest.raises(ValueError, match="local-prediction-record contract"):
        validate_0m(invalid_cluster)


def test_suite_validation_rejects_cross_horizon_identity_drift():
    predictions = {
        "0m": enriched_prediction_fixture(0),
        "6m": enriched_prediction_fixture(6),
        "12m": enriched_prediction_fixture(12),
    }
    predictions["6m"].loc[1, "population"] = 9999.0
    with pytest.raises(ValueError, match="identical identity and population"):
        validate_local_prediction_suite(
            predictions,
            expected_admin_codes=("0", "1", "2", "3"),
            feature_month="2026-04",
            suite_version=SUITE_VERSION,
        )


def test_local_prediction_csv_is_create_only_and_reports_verified_bytes(tmp_path):
    frame = enriched_prediction_fixture(0)
    output = tmp_path / "nested" / "predictions.csv"

    metadata = write_local_prediction_csv(frame, output)

    payload = output.read_bytes()
    assert metadata == {
        "path": str(output),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "row_count": 4,
        "columns": list(LOCAL_PREDICTION_COLUMNS),
    }
    assert b"\r\n" not in payload
    reloaded = pd.read_csv(
        output,
        dtype={"admin_code": "string", "cluster_id": "Int64"},
    )
    assert reloaded["admin_code"].tolist() == ["0", "1", "2", "3"]
    assert reloaded["cluster_id"].iloc[:3].tolist() == [5, 5, 1]
    assert pd.isna(reloaded["cluster_id"].iloc[3])

    before = output.read_bytes()
    with pytest.raises(FileExistsError, match="already exists"):
        write_local_prediction_csv(frame, output)
    assert output.read_bytes() == before


def test_local_prediction_csv_readback_preserves_literal_na_identity_values(
    tmp_path,
):
    frame = enriched_prediction_fixture(0)
    frame.loc[0, "ADMIN1"] = "NA"
    frame.loc[1, "ADMIN2"] = "N/A"
    output = tmp_path / "predictions.csv"

    write_local_prediction_csv(frame, output)

    reloaded = local_outputs._read_local_prediction_csv(output)
    assert isinstance(reloaded.loc[0, "ADMIN1"], str)
    assert reloaded.loc[0, "ADMIN1"] == "NA"
    assert reloaded.loc[1, "ADMIN2"] == "N/A"


def test_local_prediction_csv_readback_preserves_genuine_nullable_values(tmp_path):
    frame = enriched_prediction_fixture(0)
    frame.loc[2, "ADMIN1"] = pd.NA
    output = tmp_path / "predictions.csv"

    write_local_prediction_csv(frame, output)

    reloaded = local_outputs._read_local_prediction_csv(output)
    assert pd.isna(reloaded.loc[2, "ADMIN1"])
    assert pd.isna(reloaded.loc[2, "population"])
    assert pd.isna(reloaded.loc[2, "population_reference_period"])
    assert pd.isna(reloaded.loc[3, "cluster_id"])


@pytest.mark.parametrize(
    ("column", "replacement"),
    (
        ("ADMIN0", "drifted-admin0"),
        ("ADMIN1", "drifted-admin1"),
        ("ADMIN2", "drifted-admin2"),
        ("ADMIN3", "drifted-admin3"),
        ("ISO3", "DRF"),
        ("lat", 6.0),
        ("lon", 26.0),
        ("population", 999.0),
        ("population_reference_period", "2024-09"),
        ("population_source", "missing_raw"),
        ("probability_crisis", 0.3),
        ("predicted_crisis", 1),
        ("threshold", 0.6),
        ("cluster_id", 6),
        ("prediction_source", "pooled_small_partition"),
        ("feature_month", "2026-05"),
        ("target_month", "2026-05"),
        ("horizon_months", 6),
        ("suite_version", "drifted-suite"),
        ("model_artifact_path", "model_artifacts/drifted/0m"),
        ("source_input", "/tmp/drifted-panel.csv"),
    ),
)
def test_local_prediction_csv_rejects_non_admin_readback_drift(
    tmp_path,
    monkeypatch,
    column,
    replacement,
):
    frame = enriched_prediction_fixture(0)
    output = tmp_path / "predictions.csv"
    stable_read = local_outputs._read_local_prediction_csv

    def read_with_drift(path):
        reloaded = stable_read(path)
        reloaded.loc[0, column] = replacement
        return reloaded

    monkeypatch.setattr(local_outputs, "_read_local_prediction_csv", read_with_drift)

    with pytest.raises(ValueError, match="values differ after stable readback"):
        write_local_prediction_csv(frame, output)
