import hashlib
import json
import warnings

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

import fewsnet_partitioned_rf_pipeline.cli.normalize_panel as normalize_panel_cli
from fewsnet_partitioned_rf_pipeline.core.normalization import (
    normalize_panel,
    validate_normalization_audit,
)


def _reference_notebook_zscore(frame, source_column):
    rolling = pd.to_numeric(frame[source_column]).rolling(
        window=12,
        min_periods=1,
    ).mean()
    grouped = rolling.groupby(frame["FEWSNET_admin_code"], sort=False)
    return (rolling - grouped.transform("mean")) / grouped.transform(
        "std",
        ddof=1,
    )


def write_normalization_fixture(
    tmp_path,
    *,
    duplicate_key=(2996, "2025-10-01"),
    duplicate_changes=None,
):
    core_columns = [
        "FEWSNET_admin_code",
        "date",
        "fews_ipc_crisis",
        "lat",
        "Tair_f_tavg_mean",
        "Tair_zscore",
        "Rainf_f_tavg_mean",
        "Rainf_zscore",
    ]
    columns = core_columns + [f"source_feature_{index:02d}" for index in range(80)]
    rows = []
    for month in range(1, 13):
        rows.append(
            {
                "FEWSNET_admin_code": 2996,
                "date": f"2025-{month:02d}-01",
                "fews_ipc_crisis": 1 if month <= 11 else np.nan,
                "lat": 12.5,
                "Tair_f_tavg_mean": np.nan if month == 4 else float(month),
                "Tair_zscore": float(month) / 10,
                "Rainf_f_tavg_mean": np.nan if month == 5 else float(month * 2),
                "Rainf_zscore": -float(month) / 10,
                **{f"source_feature_{index:02d}": month + index for index in range(80)},
            }
        )
    rows.insert(
        0,
        {
            "FEWSNET_admin_code": 4001,
            "date": "2025-01-01",
            "fews_ipc_crisis": 0,
            "lat": -2.0,
            "Tair_f_tavg_mean": 30.0,
            "Tair_zscore": 0.0,
            "Rainf_f_tavg_mean": 40.0,
            "Rainf_zscore": 0.0,
            **{f"source_feature_{index:02d}": 100 + index for index in range(80)},
        },
    )
    source = next(
        row
        for row in rows
        if row["FEWSNET_admin_code"] == duplicate_key[0]
        and row["date"] == duplicate_key[1]
    )
    duplicate = dict(source)
    duplicate.update(duplicate_changes or {})
    rows.append(duplicate)

    path = tmp_path / "panel.raw.csv"
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return path


def test_normalizer_collapses_derived_only_duplicates_before_climate_recompute(
    tmp_path,
):
    raw = write_normalization_fixture(
        tmp_path,
        duplicate_key=(2996, "2025-10-01"),
        duplicate_changes={"Tair_zscore": -99.0, "Rainf_zscore": 99.0},
    )
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    result = normalize_panel(raw, output, audit)
    normalized = pd.read_csv(output)
    payload = validate_normalization_audit(audit, output)

    assert result.raw_row_count == len(normalized) + 1
    assert result.duplicate_group_count == 1
    assert result.removed_row_count == 1
    assert payload["comparison_excluded_columns"] == [
        "Tair_zscore",
        "Rainf_zscore",
    ]
    assert payload["duplicate_groups"][0]["disposition"] == (
        "collapsed_identical_or_derived_only"
    )
    assert payload["duplicate_groups"][0]["differing_excluded_columns"] == [
        "Tair_zscore",
        "Rainf_zscore",
    ]
    assert normalized.columns.tolist() == pd.read_csv(raw, nrows=0).columns.tolist()
    assert len(normalized.columns) == 88
    normalized_keys = normalized.assign(
        feature_month=pd.to_datetime(normalized["date"]).dt.to_period("M")
    )
    assert not normalized_keys.duplicated(
        ["FEWSNET_admin_code", "feature_month"]
    ).any()
    assert_series_equal(
        normalized["Tair_zscore"],
        _reference_notebook_zscore(normalized, "Tair_f_tavg_mean"),
        check_names=False,
        rtol=1e-12,
        atol=1e-12,
    )
    assert_series_equal(
        normalized["Rainf_zscore"],
        _reference_notebook_zscore(normalized, "Rainf_f_tavg_mean"),
        check_names=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_normalizer_collapses_exact_duplicate_and_records_one_based_rows(tmp_path):
    raw = write_normalization_fixture(tmp_path)
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    normalize_panel(raw, output, audit)
    payload = json.loads(audit.read_text(encoding="utf-8"))

    duplicate = payload["duplicate_groups"][0]
    assert duplicate["source_row_numbers"] == [11, 14]
    assert duplicate["group_size"] == 2
    assert duplicate["differing_excluded_columns"] == []
    assert payload["duplicate_row_count"] == 2
    assert payload["removed_row_count"] == 1


def test_normalizer_rejects_any_non_derived_duplicate_conflict(tmp_path):
    raw = write_normalization_fixture(
        tmp_path,
        duplicate_key=(2996, "2025-10-01"),
        duplicate_changes={"lat": 123.0},
    )
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    with pytest.raises(ValueError, match="2996.*2025-10.*lat"):
        normalize_panel(raw, output, audit)
    assert not output.exists()
    assert not audit.exists()


def test_normalizer_never_overwrites_or_aliases_the_raw_source(tmp_path):
    raw = write_normalization_fixture(tmp_path)
    raw_before = raw.read_bytes()
    audit = tmp_path / "panel.audit.json"

    with pytest.raises(ValueError, match="different from raw"):
        normalize_panel(raw, raw, audit)
    assert raw.read_bytes() == raw_before


def test_normalizer_rejects_raw_source_drift_after_parse(tmp_path, monkeypatch):
    raw = write_normalization_fixture(tmp_path)
    raw_before = raw.read_bytes()
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"
    from fewsnet_partitioned_rf_pipeline.core import normalization as module

    original_read_csv = module.pd.read_csv
    mutated = False

    def read_then_mutate(*args, **kwargs):
        nonlocal mutated
        frame = original_read_csv(*args, **kwargs)
        if not mutated and args[0] == raw.resolve():
            raw.write_bytes(raw_before + b"\n")
            mutated = True
        return frame

    monkeypatch.setattr(module.pd, "read_csv", read_then_mutate)

    with pytest.raises(ValueError, match="raw panel changed"):
        normalize_panel(raw, output, audit)

    assert mutated
    assert not output.exists()
    assert not audit.exists()


def test_normalizer_rejects_preexisting_versioned_outputs(tmp_path):
    raw = write_normalization_fixture(tmp_path)
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"
    output.write_text("immutable", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        normalize_panel(raw, output, audit)
    assert output.read_text(encoding="utf-8") == "immutable"
    assert not audit.exists()


def test_normalizer_preserves_concurrently_created_audit(tmp_path, monkeypatch):
    raw = write_normalization_fixture(tmp_path)
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"
    from fewsnet_partitioned_rf_pipeline.core import normalization as module

    original_panel_metadata = module._panel_metadata
    calls = 0

    def create_competing_audit(path, row_count, column_count):
        nonlocal calls
        calls += 1
        metadata = original_panel_metadata(path, row_count, column_count)
        if calls == 2:
            audit.write_text("competing immutable audit", encoding="utf-8")
        return metadata

    monkeypatch.setattr(module, "_panel_metadata", create_competing_audit)

    with pytest.raises(FileExistsError):
        normalize_panel(raw, output, audit)
    assert audit.read_text(encoding="utf-8") == "competing immutable audit"
    assert not output.exists()


def test_normalizer_emits_no_dtype_warning_for_mixed_source_columns(tmp_path):
    row_count = 20_000
    values = np.arange(row_count)
    frame = pd.DataFrame(
        {
            "ADMIN3": np.where(values < 10_000, values.astype(str), "mixed"),
            "FEWSNET_admin_code": values + 1,
            "date": "2025-01-01",
            "fews_ipc_crisis": 1,
            "Tair_f_tavg_mean": values.astype(float),
            "Tair_zscore": 0.0,
            "Rainf_f_tavg_mean": values.astype(float) * 2,
            "Rainf_zscore": 0.0,
            **{f"source_feature_{index:02d}": values for index in range(80)},
        }
    )
    raw = tmp_path / "mixed-source.csv"
    output = tmp_path / "mixed-source.normalized.csv"
    audit = tmp_path / "mixed-source.audit.json"
    frame.to_csv(raw, index=False)

    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.DtypeWarning)
        normalize_panel(raw, output, audit)


def test_audit_validation_rejects_panel_byte_or_row_count_drift(tmp_path):
    raw = write_normalization_fixture(tmp_path)
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"
    normalize_panel(raw, output, audit)
    output.write_bytes(output.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="checksum|size|row_count"):
        validate_normalization_audit(audit, output)


def test_normalization_cli_prints_sorted_json_summary(tmp_path, capsys):
    raw = write_normalization_fixture(tmp_path)
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    result = normalize_panel_cli.main(
        [
            "--input-panel",
            str(raw),
            "--output-panel",
            str(output),
            "--audit-output",
            str(audit),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == sorted(payload)
    assert payload["output_panel_path"] == str(output.resolve())
    assert payload["audit_path"] == str(audit.resolve())
    assert payload["raw_row_count"] == 14
    assert payload["normalized_row_count"] == 13
    assert payload["duplicate_group_count"] == 1
    assert payload["removed_row_count"] == 1
    assert payload["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_normalization_cli_returns_json_error_on_audit_hash_error(
    tmp_path,
    monkeypatch,
    capsys,
):
    raw = write_normalization_fixture(tmp_path)
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    def fail_audit_hash(path):
        raise OSError(f"cannot hash {path.name}")

    monkeypatch.setattr(normalize_panel_cli, "_sha256_file", fail_audit_hash)

    result = normalize_panel_cli.main(
        [
            "--input-panel",
            str(raw),
            "--output-panel",
            str(output),
            "--audit-output",
            str(audit),
        ]
    )

    assert result == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert list(payload) == sorted(payload)
    assert payload == {"error": f"cannot hash {audit.name}"}


def test_normalization_cli_returns_json_error_without_partial_outputs(tmp_path, capsys):
    raw = write_normalization_fixture(
        tmp_path,
        duplicate_changes={"lat": 123.0},
    )
    output = tmp_path / "panel.normalized-v1.csv"
    audit = tmp_path / "panel.normalized-v1.audit.json"

    result = normalize_panel_cli.main(
        [
            "--input-panel",
            str(raw),
            "--output-panel",
            str(output),
            "--audit-output",
            str(audit),
        ]
    )

    assert result == 1
    assert "2996" in json.loads(capsys.readouterr().err)["error"]
    assert not output.exists()
    assert not audit.exists()
