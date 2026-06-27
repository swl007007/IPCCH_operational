from cloud.common.forbidden_side_effects import (
    ForbiddenSideEffect,
    scan_forbidden_side_effects,
)


def test_allowed_prefixes_pass_without_findings():
    findings = scan_forbidden_side_effects(
        observed_uris=[
            "gs://bucket/monthly/runs/run-1/evi/EVI_mean_monthly_long.csv",
            "gs://bucket/monthly/runs/run-1/inference/ipcch_launch_202604_scope_0m_predictions.csv",
        ],
        allowed_prefixes=["gs://bucket/monthly/runs/run-1/"],
    )

    assert findings == []


def test_forbidden_output_families_are_reported():
    findings = scan_forbidden_side_effects(
        observed_uris=[
            "gs://bucket/monthly/runs/run-1/maps/ipcch_prediction_map.png",
            "gs://bucket/monthly/runs/run-1/prediction_sheets/ipcch.xlsx",
            "gs://bucket/monthly/runs/run-1/training/model.pkl",
        ],
        allowed_prefixes=["gs://bucket/monthly/runs/run-1/"],
    )

    assert [finding.family for finding in findings] == [
        "map",
        "prediction_sheet",
        "training",
    ]
    assert all(isinstance(finding, ForbiddenSideEffect) for finding in findings)


def test_container_temp_files_are_ignored():
    findings = scan_forbidden_side_effects(
        observed_uris=["/tmp/ipcch-cloud-worker/prediction_map_preview.png"],
        allowed_prefixes=["gs://bucket/monthly/runs/run-1/"],
        ignored_prefixes=["/tmp/ipcch-cloud-worker/"],
    )

    assert findings == []
