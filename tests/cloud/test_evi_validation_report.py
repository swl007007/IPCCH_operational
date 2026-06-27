import pandas as pd
import pytest

from cloud.batch import evi_validation


def test_evi_validation_report_accepts_required_wide_long_outputs_and_area_identity():
    mean_wide = pd.DataFrame({"region_id": ["A", "B"], "2026_04": [1.0, None]})
    std_wide = pd.DataFrame({"region_id": ["A", "B"], "2026_04": [0.1, None]})
    mean_long = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_mean": [1.0, None],
        }
    )
    std_long = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_std": [0.1, None],
        }
    )

    report = evi_validation.build_evi_validation_report(
        feature_month="2026-04",
        run_id="run-1",
        mean_wide=mean_wide,
        std_wide=std_wide,
        mean_long=mean_long,
        std_long=std_long,
        scaffold_area_ids=["A", "B"],
        reference_comparison={"status": "not_provided"},
    )

    assert report["status"] == "passed"
    assert report["output_contract_status"] == "passed"
    assert report["area_identity"]["region_id_equals_area_id"] is True
    assert report["long_outputs"]["row_count"] == 2
    assert report["reference_comparison"] == {"status": "not_provided"}


def test_evi_validation_report_records_advisory_warning_without_failing_contract():
    report = evi_validation.build_evi_validation_report(
        feature_month="2026-04",
        run_id="run-1",
        mean_wide=pd.DataFrame({"region_id": ["A"], "2026_04": [1.0]}),
        std_wide=pd.DataFrame({"region_id": ["A"], "2026_04": [0.1]}),
        mean_long=pd.DataFrame(
            {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
        ),
        std_long=pd.DataFrame(
            {"area_id": ["A"], "year": [2026], "month": [4], "EVI_std": [0.1]}
        ),
        scaffold_area_ids=["A"],
        reference_comparison={"status": "advisory_difference", "max_abs_diff": 0.5},
    )

    assert report["status"] == "passed_with_warnings"
    assert report["advisory_warnings"]


def test_evi_validation_report_rejects_row_count_mismatch():
    with pytest.raises(evi_validation.EVIValidationError, match="row count"):
        evi_validation.build_evi_validation_report(
            feature_month="2026-04",
            run_id="run-1",
            mean_wide=pd.DataFrame({"region_id": ["A"], "2026_04": [1.0]}),
            std_wide=pd.DataFrame({"region_id": ["A"], "2026_04": [0.1]}),
            mean_long=pd.DataFrame(
                {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
            ),
            std_long=pd.DataFrame(
                {"area_id": ["A"], "year": [2026], "month": [4], "EVI_std": [0.1]}
            ),
            scaffold_area_ids=["A", "B"],
            reference_comparison={"status": "not_provided"},
        )
