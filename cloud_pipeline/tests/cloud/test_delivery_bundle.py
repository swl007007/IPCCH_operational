import json
import tarfile

import pytest

from cloud.orchestrator import delivery_bundle as bundle


def _write(root, relative, text):
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    (root / relative).write_text(text)


def _table(root, relative, system, name, rows):
    import pandas as pd

    from cloud.orchestrator import delivery_outputs as do

    header = list(do.SEPTEMBER_HEADERS[system][name])
    frame = pd.DataFrame([{column: row.get(column, "") for column in header} for row in rows], columns=header)
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(root / relative, index=False)


def _sources(tmp):
    """Accepted package directories, runtime tree and lock file as install_runtime_and_models consumes them."""
    import hashlib

    repo = tmp / "repo"
    for package in bundle.RUNTIME_PACKAGES:
        _write(repo, f"{package}/__init__.py", "")
    _write(repo, "cloud/orchestrator/delivery_bundle.py", "# runtime\n")
    fews = {}
    for horizon in bundle.HORIZONS:
        directory = tmp / f"fews_{horizon}m"
        _write(directory, "model.joblib", f"model {horizon}")
        _write(directory, "local_model_manifest.json",
               '{"files": ["model.joblib", "local_model_manifest.json", "checksums.json"]}')
        digest = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                  for name in ("model.joblib", "local_model_manifest.json")}
        _write(directory, "checksums.json", json.dumps(digest))
        fews[horizon] = directory
    ipcch = tmp / "ipcch_pkg"
    _write(ipcch, "model_package_manifest.json", '{"training_cutoff": "2026-04-01"}')
    for horizon in bundle.HORIZONS:
        for name in bundle.IPCCH_SCOPE_FILES:
            _write(ipcch, f"scope_{horizon}m/{name}", f"{horizon}{name}")
    _write(tmp, "requirements.lock.txt", "pandas==3.0.0\n")
    return repo, fews, ipcch, tmp / "requirements.lock.txt"


CENSUS = {"ISO3": "SSD", "country": "South Sudan", "country_en": "South Sudan", "referenced_population": "1000",
          "population_reference_year": "2024", "population_reference_date": "2024-07-01", "population_measure": "total",
          "population_source": "test", "population_vintage": "2024", "population_source_url": "https://example.org",
          "census_genc_codes": "SSD"}


def _ipcch_predictions(horizon, target):
    import pandas as pd

    return pd.DataFrame({
        "polygon_id": ["a", "b"], "area_id": ["a", "b"], "admin_code": ["0a", "0b"], "_row_id": [0, 1],
        "population_estimate": [10.0, 0.0], "population_reference_period": ["2026-04", "2026-04"],
        "population_imputation_method": ["observed_feature_month"] * 2,
        "phase2_worse_score": [-0.01, 0.5], "phase2_worse_pred": [0, 1], "phase3_worse_score": [0.3, 0.1],
        "phase3_worse_pred": [1, 0], "phase4_worse_score": [0.0, 0.0], "phase4_worse_pred": [0, 0],
        "phase5_worse_score": [0.0, 0.0], "phase5_worse_pred": [0, 0], "overall_phase_pred": [3, 2],
        "feature_period": "2026-04", "target_period": target, "scope_months": horizon, "model_package_id": "pkg",
        "source_input": "inputs/ipcch_origin_rows.csv"})


def _valid_delivery(root):
    """A small but content-valid delivery root (origin 2026-04) that passes pre-package validation."""
    import pandas as pd

    from cloud.orchestrator import delivery_outputs as do
    from fewsnet_partitioned_rf_pipeline.local.outputs import (
        build_identity_population_frame,
        write_local_prediction_csv,
    )
    from tests.fewsnet_partitioned_rf.test_local_outputs import enriched_prediction_fixture, population_panel_fixture

    root.mkdir(parents=True, exist_ok=True)
    repo, fews, ipcch, lock = _sources(root.parent / f"{root.name}_sources")
    bundle.install_runtime_and_models(root, repo=repo, fewsnet_packages=fews, ipcch_package_root=ipcch, lock_file=lock)
    bundle.write_bundle_docs(root, origin="2026-04", prepare_id="p")
    _write(root, "reports/delivery.json", '{"origin_month": "2026-04"}')
    census = pd.DataFrame([CENSUS])
    for system in bundle.SYSTEMS:
        _write(root, f"{system}/polygons.geojson", "{}")
        census.to_csv(root / f"{system}/country_population_reference.csv", index=False)
        declarations = {f"{h}m": {family: {**entry, "frozen_path": None, "evidence_identity": None}
                                   for family, entry in do.normalise_declarations(system, h, {}).items()}
                        for h in bundle.HORIZONS}
        _write(root, f"reports/{system}_diagnostic_declarations.json", json.dumps(declarations))
    identity, _ = build_identity_population_frame(population_panel_fixture(), "2026-04")
    (root / "inputs").mkdir(exist_ok=True)
    identity.to_csv(root / "inputs/fewsnet_identity_population.csv", index=False)
    lookup = pd.DataFrame({"area_id": ["a", "b"], "admin_code": ["0a", "0b"], "country": "South Sudan",
                           "country_en": "South Sudan"})
    lookup.to_csv(root / "inputs/ipcch_origin_rows.csv", index=False)
    availability = []
    for horizon in bundle.HORIZONS:
        target = {0: "2026-04", 6: "2026-10", 12: "2027-04"}[horizon]
        scope = f"scopes/{horizon}m"
        fews_predictions = enriched_prediction_fixture(horizon)
        write_local_prediction_csv(fews_predictions, root / scope / "fewsnet/polygon_predictions.csv")
        ipcch_predictions = _ipcch_predictions(horizon, target)
        for system, predictions, area_lookup in (("fewsnet", fews_predictions, None),
                                                 ("ipcch", ipcch_predictions, lookup)):
            if system == "ipcch":
                do.write_table(predictions[list(do.SEPTEMBER_HEADERS["ipcch"]["polygon_predictions"])],
                               root / scope / "ipcch/polygon_predictions.csv")
            mapping = do.polygon_mapping(system, predictions, origin="2026-04", target=target, horizon=horizon,
                                         package_path=(f"fewsnet/model_package/{horizon}m" if system == "fewsnet"
                                                       else f"ipcch/model_package/scope_{horizon}m"))
            do.write_table(mapping, root / scope / system / "polygon_model_mapping.csv")
            iso = pd.Series({"a": "SSD", "b": "SSD"})
            name = "polygon_confidence" if system == "fewsnet" else "polygon_training_errors"
            do.write_table(do.polygon_diagnostics_unavailable(system, predictions, iso), root / scope / system / f"{name}.csv")
            country, confidence = do.country_tables(system, predictions, census=census, area_lookup=area_lookup)
            do.write_table(country, root / scope / system / "country_predictions.csv")
            do.write_table(confidence, root / scope / system / "country_confidence.csv")
            availability.append(do.availability_rows(system, horizon, polygons=mapping["polygon_id"],
                                                     countries=confidence["ISO3"]))
    do.write_table(pd.concat(availability, ignore_index=True), root / "reports/diagnostic_availability.csv")
    _write(root, "reports/feature_fill_audit.csv", "a\n1\n")
    for horizon in bundle.HORIZONS:
        _write(root, f"inputs/fewsnet_scope_{horizon}m_inference.csv", "x\n")
    _write(root, "inputs/fewsnet_normalized_panel.csv", "big\n")
    _write(root, "notes/nested/manifest.json", "{}")  # nested manifests are ordinary inventoried files


def test_inventory_and_archive_exclude_external_histories(tmp_path):
    tmp_path = tmp_path / "delivery"
    _valid_delivery(tmp_path)

    inventory = bundle.write_inventory(tmp_path, provenance={"prepare_id": "p"})
    archive = bundle.build_archive(tmp_path)

    entries = {entry["path"]: entry for entry in inventory["files"]}
    assert entries["inputs/fewsnet_normalized_panel.csv"]["portable"] is False  # inventoried, not archived
    assert "notes/nested/manifest.json" in entries  # only the ROOT manifest is excluded
    assert inventory["validation"]["status"] == "passed", inventory["validation"]["failures"]
    assert inventory["validation"]["stage"] == "pre_package"
    summary = inventory["diagnostics_availability_summary"]
    assert {(row["model_system"], row["diagnostic_family"], row["status"]) for row in summary} >= {
        ("ipcch", "maximum_phase", "unavailable"), ("fewsnet", "polygon_confidence", "unavailable")}
    assert inventory["files"] and (tmp_path / "model_inventory.json").is_file()
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert "inputs/fewsnet_normalized_panel.csv" not in names
    assert {"scopes/0m/ipcch/polygon_predictions.csv", "inputs/ipcch_origin_rows.csv", "manifest.json"} <= names
    assert json.loads((tmp_path / "manifest.json").read_text())["provenance"] == {"prepare_id": "p"}
    with pytest.raises(FileExistsError):
        bundle.build_archive(tmp_path)
    with pytest.raises(FileExistsError):
        bundle.write_inventory(tmp_path)


@pytest.mark.parametrize("change", ["history", "added_report", "removed"])
def test_archive_refuses_a_changed_or_extended_sealed_inventory(tmp_path, change):
    tmp_path = tmp_path / "delivery"
    _valid_delivery(tmp_path)
    bundle.write_inventory(tmp_path)
    if change == "history":  # non-portable history: never archived, still sealed
        (tmp_path / "inputs/fewsnet_normalized_panel.csv").write_text("changed\n")
    elif change == "added_report":
        _write(tmp_path, "reports/late_addition.json", "{}")
    else:
        (tmp_path / "reports/feature_fill_audit.csv").unlink()

    with pytest.raises(ValueError, match="inventory changed|changed after sealing"):
        bundle.build_archive(tmp_path)
    assert not (tmp_path / bundle.ARCHIVE).exists()


def test_failed_pre_package_validation_is_recorded_and_blocks_the_archive(tmp_path):
    tmp_path = tmp_path / "delivery"
    _valid_delivery(tmp_path)
    (tmp_path / "scopes/6m/ipcch/country_confidence.csv").unlink()

    inventory = bundle.write_inventory(tmp_path)

    assert inventory["validation"]["status"] == "failed"
    assert inventory["validation"]["checks"]["scope_inventory_exact"] is False
    with pytest.raises(ValueError, match="pre-package validation failed"):
        bundle.build_archive(tmp_path)


def test_compare_scopes_flags_value_and_shape_differences(tmp_path):
    for root, value in (("a", "0.5"), ("b", "0.5000000000001")):
        path = tmp_path / root / "scopes/0m/fewsnet/polygon_predictions.csv"
        path.parent.mkdir(parents=True)
        path.write_text(f"admin_code,probability_crisis\n0,{value}\n")

    result = bundle.compare_scopes(tmp_path / "a", tmp_path / "b", atol=1e-12)

    assert result["scopes/0m/fewsnet/polygon_predictions.csv"]["equal"] is True
    assert result["_inventory"]["equal"] is False  # 29 of the 30 required tables are missing
    assert bundle.compare_scopes(tmp_path / "a", tmp_path / "b", atol=1e-15)[
        "scopes/0m/fewsnet/polygon_predictions.csv"]["equal"] is False



def _pair(tmp_path, header, left, right):
    for root, row in (("a", left), ("b", right)):
        path = tmp_path / root / "scopes/0m/fewsnet/polygon_predictions.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{header}\n{row}\n")
    return bundle.compare_scopes(tmp_path / "a", tmp_path / "b")["scopes/0m/fewsnet/polygon_predictions.csv"]


@pytest.mark.parametrize(("left", "right"), [("abc", "def"), ("0.5", "abc"), ("inf", "inf"), ("0.5", ""), ("", "0.5")])
def test_continuous_cells_must_be_finite_numbers_with_equal_blank_masks(tmp_path, left, right):
    assert _pair(tmp_path, "probability_crisis", left, right)["equal"] is False


def test_ids_and_provenance_compare_exactly(tmp_path):
    assert _pair(tmp_path, "admin_code", "0001", "1")["equal"] is False
    assert _pair(tmp_path / "p", "population_reference_period", "2026-04", "2026-4")["equal"] is False


def test_empty_rescore_output_never_passes(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    result = bundle.compare_scopes(tmp_path / "a", tmp_path / "b")

    assert result["_inventory"]["equal"] is False and len(result["_inventory"]["missing"]) == 30


def test_delivered_side_must_also_hold_the_exact_30_tables(tmp_path):
    _valid_delivery(tmp_path / "rescored")
    (tmp_path / "delivered").mkdir()

    result = bundle.compare_scopes(tmp_path / "delivered", tmp_path / "rescored")

    assert result["_inventory"]["equal"] is False and len(result["_inventory"]["delivered_missing"]) == 30



@pytest.mark.parametrize("damage", [
    "header_only", "duplicate_key", "foreign_key", "country_not_in_reference", "missing_ipcch_score",
    "fewsnet_package_member_removed", "fewsnet_package_member_changed", "ipcch_scope_file_removed",
    "runtime_removed", "docs_removed", "mapping_target_missing", "country_prediction_blanked",
    "country_outcome_changed", "availability_header_only", "availability_entity_missing", "ipcch_area_id_wrong",
    "ipcch_admin_code_wrong", "fewsnet_identity_changed", "mapping_identity_wrong",
])
def test_pre_package_validation_rejects_content_and_member_damage(tmp_path, damage):
    import shutil

    root = tmp_path / "delivery"
    _valid_delivery(root)
    if damage == "header_only":
        for path in root.glob("scopes/*/*/*.csv"):
            path.write_text(path.read_text().splitlines()[0] + "\n")
    elif damage == "duplicate_key":
        path = root / "scopes/6m/ipcch/polygon_training_errors.csv"
        lines = path.read_text().splitlines()
        path.write_text("\n".join([*lines, lines[1]]) + "\n")
    elif damage == "foreign_key":
        path = root / "scopes/0m/fewsnet/polygon_model_mapping.csv"
        path.write_text(path.read_text().replace("\n3,3,", "\n9,9,"))
    elif damage == "country_not_in_reference":
        import pandas as pd

        pd.DataFrame([{**CENSUS, "ISO3": "KEN"}]).to_csv(root / "fewsnet/country_population_reference.csv", index=False)
    elif damage == "missing_ipcch_score":
        path = root / "scopes/12m/ipcch/polygon_predictions.csv"
        path.write_text(path.read_text().replace("-0.01", "", 1))
    elif damage == "fewsnet_package_member_removed":
        (root / "fewsnet/model_package/6m/model.joblib").unlink()
    elif damage == "fewsnet_package_member_changed":
        (root / "fewsnet/model_package/12m/model.joblib").write_text("other model")
    elif damage == "ipcch_scope_file_removed":
        (root / "ipcch/model_package/scope_6m/phase4_worse_model.json").unlink()
    elif damage == "runtime_removed":
        shutil.rmtree(root / "runtime/model_pipeline")
    elif damage == "docs_removed":
        (root / "README.md").unlink()
    elif damage == "mapping_target_missing":
        shutil.rmtree(root / "ipcch/model_package/scope_12m")
    else:
        _damage_content(root, damage)

    assert bundle.validate_delivery(root)["status"] == "failed", damage
    bundle.write_inventory(root)
    with pytest.raises(ValueError, match="pre-package validation failed"):
        bundle.build_archive(root)


def _edit(path, change):
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    change(frame)
    frame.to_csv(path, index=False)


def _damage_content(root, damage):
    def blank(frame):
        frame.loc[:, [c for c in frame.columns if c != "ISO3"]] = ""

    def outcome(frame):
        frame["country_outcome_crisis"] = "1" if frame["country_outcome_crisis"].iloc[0] != "1" else "0"

    def area(frame):
        frame.loc[0, "area_id"] = "b"  # a real roster area on the wrong row

    def admin(frame):
        frame.loc[0, "admin_code"] = "0z"

    def lat(frame):
        frame.loc[0, "lat"] = "5.5"  # valid coordinate, wrong row identity

    def mapping(frame):
        frame.loc[0, "admin_code"] = "3"

    def estimate(frame):
        frame.loc[0, ["historical_sample_count", "historical_error_count"]] = ["5", "0"]

    actions = {
        "country_prediction_blanked": ("scopes/6m/ipcch/country_predictions.csv", blank),
        "country_outcome_changed": ("scopes/0m/fewsnet/country_confidence.csv", outcome),
        "ipcch_area_id_wrong": ("scopes/12m/ipcch/polygon_predictions.csv", area),
        "ipcch_admin_code_wrong": ("scopes/0m/ipcch/polygon_model_mapping.csv", admin),
        "fewsnet_identity_changed": ("scopes/6m/fewsnet/polygon_predictions.csv", lat),
        "mapping_identity_wrong": ("scopes/12m/fewsnet/polygon_model_mapping.csv", mapping),
        "unsupported_estimate_filled": ("scopes/0m/fewsnet/polygon_confidence.csv", estimate),
    }
    path = root / "reports/diagnostic_availability.csv"
    if damage == "availability_header_only":
        path.write_text(path.read_text().splitlines()[0] + "\n")
    elif damage == "availability_entity_missing":
        lines = path.read_text().splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n")
    else:
        relative, change = actions[damage]
        _edit(root / relative, change)


HEADER = "model_system,horizon_months,level,entity_id,diagnostic_family,status,reason,evidence_ref\n"


@pytest.mark.parametrize("rescored_text", [
    HEADER, HEADER + "ipcch,0,country,SSD,maximum_phase,unavailable,no_complete_history,\n"])
def test_rescored_availability_must_reproduce_every_entity_family_status_and_reason(tmp_path, rescored_text):
    _write(tmp_path / "a", bundle.AVAILABILITY, HEADER + "ipcch,0,country,SSD,maximum_phase,unavailable,missing_evidence,\n")
    _write(tmp_path / "b", bundle.AVAILABILITY, rescored_text)

    assert bundle.compare_scopes(tmp_path / "a", tmp_path / "b")[bundle.AVAILABILITY]["equal"] is False


def test_availability_comparison_is_order_independent_and_empty_never_passes(tmp_path):
    rows = ["fewsnet,6,polygon,0,polygon_confidence,unavailable,missing_evidence,\n",
            "ipcch,0,country,SSD,maximum_phase,limited,single_month_interval_unavailable,gs://b/e.csv#9\n"]
    _write(tmp_path / "a", bundle.AVAILABILITY, HEADER + "".join(rows))
    _write(tmp_path / "b", bundle.AVAILABILITY, HEADER + "".join(reversed(rows)))
    assert bundle.compare_scopes(tmp_path / "a", tmp_path / "b")[bundle.AVAILABILITY]["equal"] is True
    _write(tmp_path / "c", bundle.AVAILABILITY, HEADER)
    _write(tmp_path / "d", bundle.AVAILABILITY, HEADER)
    assert bundle.compare_scopes(tmp_path / "c", tmp_path / "d")[bundle.AVAILABILITY]["equal"] is False


@pytest.mark.parametrize(("damage", "check"), [
    ("country_prediction_blanked", "ipcch_6m_country_consistent"),
    ("country_outcome_changed", "fewsnet_0m_country_consistent"),
    ("availability_header_only", "availability_complete"),
    ("availability_entity_missing", "availability_complete"),
    ("ipcch_area_id_wrong", "ipcch_12m_row_identity"),
    ("ipcch_admin_code_wrong", "ipcch_0m_row_identity"),
    ("fewsnet_identity_changed", "fewsnet_6m_row_identity"),
    ("mapping_identity_wrong", "fewsnet_12m_row_identity"),
    ("unsupported_estimate_filled", "fewsnet_0m_diagnostics_regenerated"),
])
def test_each_content_gate_fails_on_its_own_check(tmp_path, damage, check):
    root = tmp_path / "delivery"
    _valid_delivery(root)
    _damage_content(root, damage)

    validation = bundle.validate_delivery(root)

    assert validation["checks"].get(check) is False, validation["failures"]



@pytest.mark.parametrize(("status", "reason", "ref"), [
    ("available", "not_a_reason", ""),  # an unavailable row relabelled with a bogus reason
    ("available", "", ""),               # available without any bound evidence or ref
    ("available", "", "gs://b/e.csv#1"),  # a ref that no frozen declaration binds
    ("limited", "single_month_interval_unavailable", ""),
])
def test_availability_rows_cannot_contradict_the_frozen_declarations(tmp_path, status, reason, ref):
    root = tmp_path / "delivery"
    _valid_delivery(root)

    def relabel(frame):
        row = frame.index[(frame["model_system"] == "fewsnet") & (frame["horizon_months"] == "6")
                          & (frame["level"] == "polygon")][0]
        frame.loc[row, ["status", "reason", "evidence_ref"]] = [status, reason, ref]

    _edit(root / "reports/diagnostic_availability.csv", relabel)
    validation = bundle.validate_delivery(root)

    assert validation["checks"]["fewsnet_6m_diagnostics_regenerated"] is False, validation["failures"]
    if reason == "not_a_reason":
        assert validation["checks"]["availability_status_valid"] is False
