from __future__ import annotations

import json
from pathlib import Path

import pytest

from fewsnet_partitioned_rf_pipeline.cli import run_local_experiment as cli
from fewsnet_partitioned_rf_pipeline.local.runner import LocalExperimentResult


def result_fixture(tmp_path: Path) -> LocalExperimentResult:
    root = tmp_path / "Outcome/fewsnet_partitioned_rf"
    return LocalExperimentResult(
        run_id="local-202604-20260726T120000000000Z",
        suite_version="local-202604-111111111111-222222222222",
        output_root=root,
        run_summary_path=root / "predictions/202604/run_summary.json",
        prediction_paths={
            key: root / f"predictions/202604/{key}.csv"
            for key in ("0m", "6m", "12m")
        },
        model_package_paths={
            key: root / f"model_artifacts/local-suite/{key}"
            for key in ("0m", "6m", "12m")
        },
        report_paths={
            "training_threshold_report": (
                root / "reports/local-suite/training_threshold_report.json"
            ),
            "run_manifest": root / "reports/local-suite/run_manifest.json",
        },
    )


def test_cli_prints_json_success_and_forwards_overwrite(tmp_path, monkeypatch, capsys):
    captured_config = None

    def fake_run(config):
        nonlocal captured_config
        captured_config = config
        return result_fixture(tmp_path)

    monkeypatch.setattr(cli, "run_local_experiment", fake_run)
    code = cli.main(
        [
            "--panel", str(tmp_path / "panel.csv"),
            "--normalization-audit", str(tmp_path / "panel.audit.json"),
            "--feature-month", "2026-04",
            "--overwrite",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "passed"
    assert captured_config.output_root == Path("Outcome/fewsnet_partitioned_rf")
    assert captured_config.overwrite is True


def test_cli_returns_json_failure_and_has_no_cloud_arguments(
    tmp_path,
    monkeypatch,
    capsys,
):
    def fail(config):
        raise RuntimeError(f"synthetic failure: {config.feature_month}")

    monkeypatch.setattr(cli, "run_local_experiment", fail)
    code = cli.main(
        [
            "--panel", str(tmp_path / "panel.csv"),
            "--normalization-audit", str(tmp_path / "panel.audit.json"),
            "--feature-month", "2026-04",
        ]
    )
    payload = json.loads(capsys.readouterr().err)
    assert code == 1
    assert payload == {
        "error_type": "RuntimeError",
        "message": "synthetic failure: 2026-04",
        "status": "failed",
    }
    help_text = cli.build_parser().format_help().lower()
    for forbidden in ("gcs", "vertex", "registry", "endpoint", "batch", "shapefile"):
        assert forbidden not in help_text


def test_cli_requires_panel_audit_and_feature_month():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["--panel", "panel.csv", "--normalization-audit", "audit.json"]
        )
