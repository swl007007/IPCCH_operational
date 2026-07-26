from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import fewsnet_partitioned_rf_pipeline.local.runner as runner
from fewsnet_partitioned_rf_pipeline.core.normalization import normalize_panel
from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
from tests.fewsnet_partitioned_rf.local_test_support import (
    write_normalized_local_panel_fixture,
)


def seed_existing_suite(
    staged: runner.StagedLocalExperiment,
    output_root: Path,
) -> None:
    package_parent = staged.package_dirs["0m"].parent
    final_package_parent = output_root / "model_artifacts" / staged.suite_version
    shutil.copytree(package_parent, final_package_parent)

    report_parent = staged.report_files["run_manifest"].parent
    final_report_parent = output_root / "reports" / staged.suite_version
    shutil.copytree(report_parent, final_report_parent)


def test_staged_engine_trains_reloads_and_predicts_all_three_horizons(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    monkeypatch.setattr(runner, "utc_now", lambda: "2026-07-26T12:00:00Z")

    staged = runner.build_staged_local_experiment(
        runner.LocalExperimentConfig(
            panel_path=panel,
            normalization_audit_path=audit,
            feature_month="2026-04",
            output_root=tmp_path / "final",
            overwrite=False,
        ),
        tmp_path / "staging",
    )

    assert staged.suite_version == (
        "local-202604-111111111111-" + staged.panel_sha256[:12]
    )
    assert staged.reused_model_suite is False
    assert set(staged.package_dirs) == {"0m", "6m", "12m"}
    assert set(staged.prediction_files) == {"0m", "6m", "12m"}
    expected_targets = {"0m": "2026-04", "6m": "2026-10", "12m": "2027-04"}

    for horizon_key, package_dir in staged.package_dirs.items():
        loaded = load_local_model_package(
            package_dir,
            expected_suite_version=staged.suite_version,
            expected_source_git_commit="1" * 40,
            expected_panel_sha256=staged.panel_sha256,
        )
        assert loaded.predictor.horizon_key == horizon_key

        prediction = pd.read_csv(staged.prediction_files[horizon_key])
        assert len(prediction) == 4
        assert prediction["target_month"].unique().tolist() == [
            expected_targets[horizon_key]
        ]
        assert prediction["probability_crisis"].between(0, 1).all()

    summary = json.loads(staged.run_summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["gcp_write_performed"] is False
    assert summary["population"]["raw_last_observed_count"] == 2
    assert summary["population"]["missing_raw_count"] == 2


def test_staged_engine_fails_closed_when_one_horizon_training_fails(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    original = runner.train_horizon_model

    def fail_6m(aligned_frame, feature_contract, partition_map, horizon_key):
        if horizon_key == "6m":
            raise RuntimeError("synthetic 6m failure")
        return original(
            aligned_frame,
            feature_contract,
            partition_map,
            horizon_key,
        )

    monkeypatch.setattr(runner, "train_horizon_model", fail_6m)
    with pytest.raises(RuntimeError, match="synthetic 6m failure"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "staging",
        )
    assert not (tmp_path / "staging/predictions/202604/run_summary.json").exists()


def test_staged_engine_reuses_only_a_fully_valid_existing_suite(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    config = runner.LocalExperimentConfig(
        panel_path=panel,
        normalization_audit_path=audit,
        feature_month="2026-04",
        output_root=tmp_path / "final",
        overwrite=True,
    )
    first = runner.build_staged_local_experiment(config, tmp_path / "stage-one")
    seed_existing_suite(first, config.output_root)

    def forbidden_training(*args, **kwargs):
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(runner, "train_horizon_model", forbidden_training)
    second = runner.build_staged_local_experiment(config, tmp_path / "stage-two")
    assert second.reused_model_suite is True

    relocated_source = tmp_path / "relocated-source"
    relocated_source.mkdir()
    relocated_panel = relocated_source / panel.name
    relocated_audit = relocated_source / audit.name
    shutil.copy2(panel, relocated_panel)
    shutil.copy2(audit, relocated_audit)
    relocated_config = runner.LocalExperimentConfig(
        panel_path=relocated_panel,
        normalization_audit_path=relocated_audit,
        feature_month="2026-04",
        output_root=config.output_root,
        overwrite=True,
    )
    relocated = runner.build_staged_local_experiment(
        relocated_config,
        tmp_path / "stage-relocated",
    )
    assert relocated.reused_model_suite is True
    relocated_prediction = pd.read_csv(relocated.prediction_files["0m"])
    assert relocated_prediction["source_input"].unique().tolist() == [
        str(relocated_panel.resolve())
    ]

    manifest_path = (
        config.output_root
        / "reports"
        / relocated.suite_version
        / "run_manifest.json"
    )
    original_manifest = manifest_path.read_text(encoding="utf-8")
    invalid_manifest = json.loads(original_manifest)
    invalid_manifest["run_id"] = "local-202603-20260726T120000000000Z"
    manifest_path.write_text(
        json.dumps(invalid_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="run_id"):
        runner.build_staged_local_experiment(
            config,
            tmp_path / "stage-invalid-run-id",
        )
    manifest_path.write_text(original_manifest, encoding="utf-8")

    checksums = (
        config.output_root
        / "model_artifacts"
        / second.suite_version
        / "6m"
        / "checksums.json"
    )
    checksums.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        runner.build_staged_local_experiment(config, tmp_path / "stage-four")


def test_staged_engine_rejects_panel_audit_drift_and_nonlatest_month(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    panel.write_bytes(panel.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="normalization audit does not match panel"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "stage-audit-drift",
        )

    panel, audit, _ = write_normalized_local_panel_fixture(
        tmp_path / "source-two"
    )
    with pytest.raises(ValueError, match="latest feature month"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-03",
                output_root=tmp_path / "final-two",
            ),
            tmp_path / "stage-old-month",
        )


def test_staged_engine_rejects_area_count_and_unsafe_ipcch_root(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    with pytest.raises(ValueError, match="area_count.*5718"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "stage-area-count",
        )

    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    forbidden_root = Path.cwd() / "Outcome/ipcch_unified/local-fewsnet-test"
    with pytest.raises(ValueError, match="Outcome/ipcch_unified"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=forbidden_root,
            ),
            tmp_path / "stage-unsafe-root",
        )

    sibling_checkout_root = (
        tmp_path
        / "sibling-checkout"
        / "Outcome"
        / "ipcch_unified"
        / "local-fewsnet-test"
    )
    with pytest.raises(ValueError, match="Outcome/ipcch_unified"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=sibling_checkout_root,
            ),
            tmp_path / "stage-unsafe-sibling-root",
        )


def test_path_safety_rejects_mixed_case_ipcch_and_equal_paths(tmp_path):
    mixed_case_forbidden_root = (
        Path.cwd()
        / "outcome"
        / "IPCCH_UNIFIED"
        / "local-fewsnet-test"
    )
    with pytest.raises(ValueError, match="Outcome/ipcch_unified"):
        runner._resolve_output_root(mixed_case_forbidden_root)

    assert runner._paths_equal(
        tmp_path / "Panel.NORMALIZED-v1.csv",
        tmp_path / "panel.normalized-V1.CSV",
    )


def test_clean_git_probe_rejects_tracked_changes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
    )
    tracked = repo / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "initial"],
        cwd=repo,
        check=True,
    )
    assert len(runner.resolve_clean_git_commit(repo)) == 40
    tracked.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tracked Git changes"):
        runner.resolve_clean_git_commit(repo)


def test_staged_engine_rejects_feature_or_partition_checksum_drift(
    tmp_path,
    monkeypatch,
):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    monkeypatch.setattr(runner, "FEATURE_CONTRACT_FILE_SHA256", "f" * 64)
    with pytest.raises(ValueError, match="feature contract SHA-256"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel,
                audit,
                "2026-04",
                tmp_path / "final",
            ),
            tmp_path / "stage-feature-drift",
        )

    monkeypatch.setattr(
        runner,
        "FEATURE_CONTRACT_FILE_SHA256",
        "3779c6bcde70560c0e1514c563ced6e7bd559c6d352689398c3cecb93d44a67b",
    )
    monkeypatch.setattr(runner, "PARTITION_ASSET_SHA256", "e" * 64)
    with pytest.raises(ValueError, match="partition asset SHA-256"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel,
                audit,
                "2026-04",
                tmp_path / "final-two",
            ),
            tmp_path / "stage-partition-drift",
        )


def test_staged_engine_rejects_missing_feature_month_area(tmp_path, monkeypatch):
    _, _, raw = write_normalized_local_panel_fixture(
        tmp_path / "complete-source"
    )
    feature_periods = pd.to_datetime(raw["date"]).dt.to_period("M")
    missing_latest = raw.loc[
        ~(
            raw["FEWSNET_admin_code"].astype(str).eq("3")
            & feature_periods.eq(pd.Period("2026-04", freq="M"))
        )
    ].copy()
    source = tmp_path / "missing-source"
    source.mkdir()
    raw_path = source / "panel.raw.csv"
    panel_path = source / "panel.normalized-v1.csv"
    audit_path = source / "panel.normalized-v1.audit.json"
    missing_latest.to_csv(raw_path, index=False, lineterminator="\n")
    normalize_panel(raw_path, panel_path, audit_path)

    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    with pytest.raises(ValueError, match="missing authoritative admin_code"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel_path,
                normalization_audit_path=audit_path,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            tmp_path / "stage-missing-area",
        )


def test_staged_engine_keeps_staging_outside_final_output(tmp_path, monkeypatch):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    output_root = tmp_path / "final"
    with pytest.raises(ValueError, match="staging_root.*output_root"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=output_root,
            ),
            output_root / "temporary-run",
        )
    assert not output_root.exists()


def test_staging_containment_is_case_insensitive(tmp_path):
    output_root = (tmp_path / "Final").resolve()
    mixed_case_child = tmp_path / "final" / "temporary-run"

    with pytest.raises(ValueError, match="staging_root.*output_root"):
        runner._prepare_staging_root(mixed_case_child, output_root)

    assert not mixed_case_child.exists()


def test_staged_engine_rejects_input_change_after_preflight(tmp_path, monkeypatch):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    original_prepare = runner._prepare_staging_root

    def mutate_panel_after_preflight(staging_root, output_root):
        prepared = original_prepare(staging_root, output_root)
        panel.write_bytes(panel.read_bytes() + b"\n")
        return prepared

    monkeypatch.setattr(
        runner,
        "_prepare_staging_root",
        mutate_panel_after_preflight,
    )
    staging_root = tmp_path / "staging"
    with pytest.raises(ValueError, match="panel changed after preflight"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            staging_root,
        )
    assert not (staging_root / "predictions/202604/run_summary.json").exists()


def test_staged_engine_rejects_panel_change_during_preflight(tmp_path, monkeypatch):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    original_load_contract = runner.load_feature_contract

    def mutate_panel_after_audit_validation(path):
        contract = original_load_contract(path)
        panel.write_bytes(panel.read_bytes() + b"\n")
        return contract

    monkeypatch.setattr(
        runner,
        "load_feature_contract",
        mutate_panel_after_audit_validation,
    )
    staging_root = tmp_path / "staging"
    with pytest.raises(ValueError, match="panel changed during preflight"):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            staging_root,
        )
    assert not staging_root.exists()


def test_staged_engine_rejects_audit_change_during_preflight(tmp_path, monkeypatch):
    panel, audit, _ = write_normalized_local_panel_fixture(tmp_path / "source")
    monkeypatch.setattr(runner, "EXPECTED_AREA_COUNT", 4)
    monkeypatch.setattr(
        runner,
        "resolve_clean_git_commit",
        lambda root: "1" * 40,
    )
    original_inspect_panel = runner.inspect_panel

    def mutate_audit_after_validation(path):
        panel_info = original_inspect_panel(path)
        audit_payload = json.loads(audit.read_text(encoding="utf-8"))
        audit_payload["latest_feature_month"] = "2026-03"
        audit.write_text(
            json.dumps(audit_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return panel_info

    monkeypatch.setattr(
        runner,
        "inspect_panel",
        mutate_audit_after_validation,
    )
    staging_root = tmp_path / "staging"
    with pytest.raises(
        ValueError,
        match="normalization audit changed during preflight",
    ):
        runner.build_staged_local_experiment(
            runner.LocalExperimentConfig(
                panel_path=panel,
                normalization_audit_path=audit,
                feature_month="2026-04",
                output_root=tmp_path / "final",
            ),
            staging_root,
        )
    assert not staging_root.exists()
