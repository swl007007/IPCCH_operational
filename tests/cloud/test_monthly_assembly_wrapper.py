import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.orchestrator import assembly, base_input_validation


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_existing_monthly_builder():
    path = PROJECT_ROOT / "Final_harmonise" / "00_build_monthly_ipcch_base_input.py"
    spec = importlib.util.spec_from_file_location("existing_monthly_builder", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_assembly_merges_cloud_evi_long_outputs_and_preserves_scaffold_rows():
    scaffold = pd.DataFrame(
        {"area_id": ["A", "B"], "year": [2026, 2026], "month": [4, 4]}
    )
    source = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "price": [1.0, 2.0],
        }
    )
    fixed = pd.DataFrame({"area_id": ["A", "B"], "admin_name": ["a", "b"]})
    evi_mean = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_mean": [10.0, None],
        }
    )
    evi_std = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_std": [1.0, None],
        }
    )

    base_input, report = assembly.assemble_monthly_base_input(
        scaffold=scaffold,
        source_panel=source,
        fixed_slow_features=fixed,
        evi_mean_long=evi_mean,
        evi_std_long=evi_std,
        feature_month="2026-04",
    )

    assert len(base_input) == len(scaffold)
    assert set(base_input.columns) >= {
        "area_id",
        "year",
        "month",
        "price",
        "admin_name",
        "EVI_mean",
        "EVI_std",
    }
    assert report["status"] == "passed"
    assert report["scaffold_row_count"] == 2
    assert report["row_count"] == 2


def test_assembly_normalizes_admin_code_and_records_missing_selected_source_month():
    scaffold = pd.DataFrame(
        {"admin_code": [" A ", "B"], "year": [2026, 2026], "month": [4, 4]}
    )
    source = pd.DataFrame(
        {
            "admin_code": ["A", "B"],
            "year": [2026, 2026],
            "month": [3, 3],
            "price": [1.0, 2.0],
        }
    )
    fixed = pd.DataFrame({"admin_code": ["A", "B"], "admin_name": ["a", "b"]})
    evi_mean = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_mean": [1, 2],
        }
    )
    evi_std = pd.DataFrame(
        {
            "area_id": ["A", "B"],
            "year": [2026, 2026],
            "month": [4, 4],
            "EVI_std": [0, 0],
        }
    )

    base_input, report = assembly.assemble_monthly_base_input(
        scaffold=scaffold,
        source_panel=source,
        fixed_slow_features=fixed,
        evi_mean_long=evi_mean,
        evi_std_long=evi_std,
        feature_month="2026-04",
    )

    assert list(base_input["area_id"]) == ["A", "B"]
    assert "price" not in base_input.columns or base_input["price"].isna().all()
    assert report["source_join"]["target_month_present_in_source"] is False


def test_assembly_rejects_scaffold_with_multiple_months():
    scaffold = pd.DataFrame(
        {
            "admin_code": ["A", "B"],
            "lat": [1.0, 2.0],
            "lon": [31.0, 32.0],
            "year": [2026, 2026],
            "month": [4, 5],
        }
    )

    with pytest.raises(ValueError, match="exactly one month"):
        assembly.assemble_monthly_base_input(
            scaffold=scaffold,
            source_panel=pd.DataFrame(
                {"admin_code": ["A"], "year": [2026], "month": [4]}
            ),
            fixed_slow_features=pd.DataFrame({"area_id": ["A"], "crop": [1]}),
            evi_mean_long=pd.DataFrame(
                {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
            ),
            evi_std_long=pd.DataFrame(
                {"area_id": ["A"], "year": [2026], "month": [4], "EVI_std": [0.1]}
            ),
            feature_month="2026-04",
        )


def test_assembly_excludes_source_overlap_with_fixed_and_engineered_columns():
    scaffold = pd.DataFrame(
        {
            "admin_code": ["101.0"],
            "lat": [1.1],
            "lon": [31.1],
            "year": [2026],
            "month": [4],
        }
    )
    fixed = pd.DataFrame(
        {
            "area_id": ["101"],
            "admin_code": ["101"],
            "lat": [1.1],
            "lon": [31.1],
            "crop": [1],
            "elevation": [500],
        }
    )
    source = pd.DataFrame(
        {
            "admin_code": ["101"],
            "lat": [1.1],
            "lon": [31.1],
            "year": [2026],
            "month": [4],
            "crop": [99],
            "overall_phase": [3],
            "EVI_mean__l12": [0.5],
            "rain_lag1": [12.0],
        }
    )
    evi_mean = pd.DataFrame(
        {"area_id": ["101"], "year": [2026], "month": [4], "EVI_mean": [0.23]}
    )
    evi_std = pd.DataFrame(
        {"area_id": ["101"], "year": [2026], "month": [4], "EVI_std": [0.04]}
    )

    base_input, report = assembly.assemble_monthly_base_input(
        scaffold=scaffold,
        source_panel=source,
        fixed_slow_features=fixed,
        evi_mean_long=evi_mean,
        evi_std_long=evi_std,
        feature_month="2026-04",
    )

    assert list(base_input.columns)[:6] == [
        "area_id",
        "admin_code",
        "lat",
        "lon",
        "year",
        "month",
    ]
    assert base_input.loc[0, "area_id"] == "101"
    assert base_input.loc[0, "crop"] == 1
    assert base_input.loc[0, "overall_phase"] == 3
    assert base_input.loc[0, "EVI_mean"] == 0.23
    assert "crop_x" not in base_input.columns
    assert "crop_y" not in base_input.columns
    assert "EVI_mean__l12" not in base_input.columns
    assert "rain_lag1" not in base_input.columns
    assert report["fixed_slow_join"]["matched_rows"] == 1
    assert report["source_join"]["matched_rows"] == 1
    assert report["source_join"]["feature_columns"] == 1


def test_assembly_matches_existing_builder_for_shared_inputs_then_appends_evi(
    tmp_path,
):
    existing_builder = _load_existing_monthly_builder()
    scaffold_path = tmp_path / "scaffold.csv"
    fixed_path = tmp_path / "fixed.csv"
    source_path = tmp_path / "source.csv"
    expected_output_path = tmp_path / "expected.csv"
    expected_summary_path = tmp_path / "expected_summary.json"
    scaffold = pd.DataFrame(
        {
            "area_id": ["101"],
            "admin_code": ["101"],
            "lat": ["1.1"],
            "lon": ["31.1"],
            "year": ["2026"],
            "month": ["4"],
        }
    )
    fixed = pd.DataFrame(
        {
            "area_id": ["101"],
            "admin_code": ["101"],
            "lat": ["1.1"],
            "lon": ["31.1"],
            "crop": ["1"],
            "elevation": ["500"],
        }
    )
    source = pd.DataFrame(
        {
            "area_id": ["101"],
            "admin_code": ["101"],
            "lat": ["1.1"],
            "lon": ["31.1"],
            "year": ["2026"],
            "month": ["4"],
            "crop": ["99"],
            "overall_phase": ["3"],
            "rain_lag1": ["12"],
        }
    )
    scaffold.to_csv(scaffold_path, index=False)
    fixed.to_csv(fixed_path, index=False)
    source.to_csv(source_path, index=False)

    existing_builder.build_monthly_base_input(
        year=2026,
        month=4,
        scaffold_path=scaffold_path,
        fixed_slow_path=fixed_path,
        historical_panel_path=source_path,
        output_path=expected_output_path,
        summary_path=expected_summary_path,
    )
    expected = pd.read_csv(expected_output_path, dtype=str)
    expected_summary = json.loads(expected_summary_path.read_text(encoding="utf-8"))

    base_input, report = assembly.assemble_monthly_base_input(
        scaffold=pd.read_csv(scaffold_path),
        source_panel=pd.read_csv(source_path),
        fixed_slow_features=pd.read_csv(fixed_path),
        evi_mean_long=pd.DataFrame(
            {"area_id": ["101"], "year": [2026], "month": [4], "EVI_mean": [0.23]}
        ),
        evi_std_long=pd.DataFrame(
            {"area_id": ["101"], "year": [2026], "month": [4], "EVI_std": [0.04]}
        ),
        feature_month="2026-04",
    )

    shared_columns = list(expected.columns)
    assert list(base_input.columns[: len(shared_columns)]) == shared_columns
    assert base_input[shared_columns].astype(str).reset_index(drop=True).to_dict(
        "list"
    ) == expected.astype(str).reset_index(drop=True).to_dict("list")
    assert "EVI_mean" in base_input.columns
    assert "EVI_std" in base_input.columns
    assert (
        report["source_join"]["scanned_rows"]
        == expected_summary["source_join"]["scanned_rows"]
    )


def test_assembly_rejects_duplicate_selected_month_source_keys():
    scaffold = pd.DataFrame({"area_id": ["A"], "year": [2026], "month": [4]})
    source = pd.DataFrame(
        {
            "area_id": ["A", "A"],
            "year": [2026, 2026],
            "month": [4, 4],
            "price": [1.0, 2.0],
        }
    )
    fixed = pd.DataFrame({"area_id": ["A"], "admin_name": ["a"]})
    evi_mean = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
    )
    evi_std = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_std": [0.1]}
    )

    with pytest.raises(ValueError, match="duplicate source"):
        assembly.assemble_monthly_base_input(
            scaffold=scaffold,
            source_panel=source,
            fixed_slow_features=fixed,
            evi_mean_long=evi_mean,
            evi_std_long=evi_std,
            feature_month="2026-04",
        )


def test_assembly_rejects_blank_fixed_or_source_area_ids():
    scaffold = pd.DataFrame({"area_id": ["A"], "year": [2026], "month": [4]})
    evi_mean = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_mean": [1.0]}
    )
    evi_std = pd.DataFrame(
        {"area_id": ["A"], "year": [2026], "month": [4], "EVI_std": [0.1]}
    )

    with pytest.raises(ValueError, match="fixed/slow.*blank"):
        assembly.assemble_monthly_base_input(
            scaffold=scaffold,
            source_panel=pd.DataFrame(
                {"area_id": ["A"], "year": [2026], "month": [4], "price": [1.0]}
            ),
            fixed_slow_features=pd.DataFrame({"area_id": [""], "admin_name": ["x"]}),
            evi_mean_long=evi_mean,
            evi_std_long=evi_std,
            feature_month="2026-04",
        )

    with pytest.raises(ValueError, match="source.*blank"):
        assembly.assemble_monthly_base_input(
            scaffold=scaffold,
            source_panel=pd.DataFrame(
                {"area_id": [""], "year": [2026], "month": [4], "price": [1.0]}
            ),
            fixed_slow_features=pd.DataFrame({"area_id": ["A"], "admin_name": ["a"]}),
            evi_mean_long=evi_mean,
            evi_std_long=evi_std,
            feature_month="2026-04",
        )


def test_base_input_validation_report_checks_row_universe_and_selected_month():
    base = pd.DataFrame({"area_id": ["A", "B"], "year": [2026, 2026], "month": [4, 4]})
    scaffold = pd.DataFrame(
        {"area_id": ["A", "B"], "year": [2026, 2026], "month": [4, 4]}
    )

    report = base_input_validation.validate_base_input(
        base_input=base,
        scaffold=scaffold,
        feature_month="2026-04",
    )

    assert report["status"] == "passed"
    assert report["row_universe_match"] is True
    assert report["base_input_row_count"] == 2


def test_base_input_validation_accepts_assembled_numeric_admin_code_identity():
    scaffold = pd.DataFrame(
        {
            "admin_code": [101.0],
            "lat": [1.1],
            "lon": [31.1],
            "year": [2026],
            "month": [4],
        }
    )
    base_input, _ = assembly.assemble_monthly_base_input(
        scaffold=scaffold,
        source_panel=pd.DataFrame(
            {"admin_code": [101], "year": [2026], "month": [4], "price": [1.0]}
        ),
        fixed_slow_features=pd.DataFrame(
            {"admin_code": [101], "admin_name": ["admin-101"]}
        ),
        evi_mean_long=pd.DataFrame(
            {"area_id": ["101"], "year": [2026], "month": [4], "EVI_mean": [0.23]}
        ),
        evi_std_long=pd.DataFrame(
            {"area_id": ["101"], "year": [2026], "month": [4], "EVI_std": [0.04]}
        ),
        feature_month="2026-04",
    )

    report = base_input_validation.validate_base_input(
        base_input=base_input,
        scaffold=scaffold,
        feature_month="2026-04",
    )

    assert report["status"] == "passed"


def test_base_input_validation_invokes_model_input_forecast_schema_gate():
    base = pd.DataFrame({"area_id": [], "year": [], "month": []})
    scaffold = pd.DataFrame({"area_id": [], "year": [], "month": []})

    with pytest.raises(base_input_validation.BaseInputValidationError, match="schema"):
        base_input_validation.validate_base_input(
            base_input=base,
            scaffold=scaffold,
            feature_month="2026-04",
        )


def test_base_input_validation_rejects_row_universe_mismatch():
    base = pd.DataFrame({"area_id": ["A"], "year": [2026], "month": [4]})
    scaffold = pd.DataFrame(
        {"area_id": ["A", "B"], "year": [2026, 2026], "month": [4, 4]}
    )

    with pytest.raises(
        base_input_validation.BaseInputValidationError, match="row universe"
    ):
        base_input_validation.validate_base_input(
            base_input=base,
            scaffold=scaffold,
            feature_month="2026-04",
        )


def test_base_input_validation_rejects_blank_required_keys():
    base = pd.DataFrame({"area_id": ["A", ""], "year": [2026, 2026], "month": [4, 4]})
    scaffold = pd.DataFrame(
        {"area_id": ["A", ""], "year": [2026, 2026], "month": [4, 4]}
    )

    with pytest.raises(base_input_validation.BaseInputValidationError, match="blank"):
        base_input_validation.validate_base_input(
            base_input=base,
            scaffold=scaffold,
            feature_month="2026-04",
        )


def test_assembly_wrapper_localizes_cloud_inputs_and_writes_artifacts(tmp_path):
    store = LocalObjectStore(tmp_path)
    store.write_text("gs://bucket/scaffold.csv", "area_id,year,month\nA,2026,4\n")
    store.write_text(
        "gs://bucket/source.csv", "area_id,year,month,price\nA,2026,4,1.0\n"
    )
    store.write_text("gs://bucket/fixed.csv", "area_id,admin_name\nA,admin-a\n")
    store.write_text(
        "gs://bucket/evi_mean.csv", "area_id,year,month,EVI_mean\nA,2026,4,10.0\n"
    )
    store.write_text(
        "gs://bucket/evi_std.csv", "area_id,year,month,EVI_std\nA,2026,4,1.0\n"
    )

    result = assembly.write_monthly_assembly_artifacts(
        store=store,
        feature_month="2026-04",
        run_id="run-1",
        output_prefix_uri="gs://bucket/runs/run-1/assembly/",
        scaffold_uri="gs://bucket/scaffold.csv",
        source_panel_uri="gs://bucket/source.csv",
        fixed_slow_features_uri="gs://bucket/fixed.csv",
        evi_mean_long_uri="gs://bucket/evi_mean.csv",
        evi_std_long_uri="gs://bucket/evi_std.csv",
    )

    assert result["status"] == "passed"
    assert store.read_text(
        "gs://bucket/runs/run-1/assembly/ipcch_monthly_base_input_202604.csv"
    ).startswith("area_id,admin_code,lat,lon,year,month")
    assert (
        "gs://bucket/runs/run-1/assembly/ipcch_monthly_base_input_202604_summary.json"
        in store.list("gs://bucket/runs/run-1/assembly/")
    )
