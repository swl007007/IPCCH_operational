"""Inherited systems are verified by pinned member identity: never re-aggregated or regenerated."""

import hashlib
import json

import pandas as pd
import pytest

from cloud.orchestrator import delivery_bundle as bundle
from cloud.orchestrator import delivery_outputs as do
from tests.cloud.test_delivery_bundle import _valid_delivery


def _inherit_ipcch(root):
    rows = pd.read_csv(root / bundle.AVAILABILITY, dtype=str, keep_default_na=False)
    rows[rows["model_system"] == "ipcch"].to_csv(root / "reports/ipcch_diagnostic_availability.csv", index=False)
    names = [f"scopes/{h}m/ipcch/{n}.csv" for h in bundle.HORIZONS for n in bundle.SCOPE_TABLES["ipcch"]]
    names += ["reports/ipcch_diagnostic_availability.csv", "inputs/ipcch_origin_rows.csv"]
    members = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
    (root / "reports/inherited_members.json").write_text(json.dumps({"ipcch": {"members": members}}))


def _no_ipcch_recomputation(monkeypatch):
    country_tables, regenerate = do.country_tables, bundle.regenerate_diagnostics

    def guarded_country(system, *args, **kwargs):
        assert system != "ipcch", "inherited IPCCH country fields were re-aggregated"
        return country_tables(system, *args, **kwargs)

    def guarded_regenerate(root, system, *args, **kwargs):
        assert system != "ipcch", "inherited IPCCH diagnostics were regenerated"
        return regenerate(root, system, *args, **kwargs)

    monkeypatch.setattr(do, "country_tables", guarded_country)
    monkeypatch.setattr(bundle, "regenerate_diagnostics", guarded_regenerate)


def test_inherited_system_is_checked_by_identity_with_truthful_names(tmp_path, monkeypatch):
    root = tmp_path / "delivery"
    _valid_delivery(root)
    _inherit_ipcch(root)
    _no_ipcch_recomputation(monkeypatch)

    validation = bundle.validate_delivery(root)

    checks = validation["checks"]
    assert validation["status"] == "passed", validation["failures"]
    for horizon in bundle.HORIZONS:
        assert checks[f"ipcch_{horizon}m_country_inherited_identical"] is True
        assert checks[f"ipcch_{horizon}m_diagnostics_inherited_identical"] is True
        assert f"ipcch_{horizon}m_country_consistent" not in checks
        assert f"ipcch_{horizon}m_diagnostics_regenerated" not in checks
        assert checks[f"fewsnet_{horizon}m_country_consistent"] is True  # scored system keeps legacy names
        assert checks[f"fewsnet_{horizon}m_diagnostics_regenerated"] is True
    assert checks["ipcch_inherited_members_identical"] is True


@pytest.mark.parametrize("damage,check", [
    ("scopes/6m/ipcch/country_predictions.csv", "ipcch_6m_country_inherited_identical"),
    ("scopes/12m/ipcch/polygon_training_errors.csv", "ipcch_12m_diagnostics_inherited_identical"),
    ("inputs/ipcch_origin_rows.csv", "ipcch_inherited_members_identical"),
])
def test_a_changed_inherited_member_fails_its_identity_check(tmp_path, monkeypatch, damage, check):
    root = tmp_path / "delivery"
    _valid_delivery(root)
    _inherit_ipcch(root)
    _no_ipcch_recomputation(monkeypatch)
    with (root / damage).open("a", encoding="utf-8") as handle:
        handle.write("\n")

    assert bundle.validate_delivery(root)["checks"][check] is False


def test_inherited_availability_rows_must_equal_the_inherited_member(tmp_path, monkeypatch):
    root = tmp_path / "delivery"
    _valid_delivery(root)
    _inherit_ipcch(root)
    _no_ipcch_recomputation(monkeypatch)
    rows = pd.read_csv(root / bundle.AVAILABILITY, dtype=str, keep_default_na=False)
    rows = rows.drop(rows.index[(rows["model_system"] == "ipcch") & (rows["horizon_months"] == "0")][0])
    rows.to_csv(root / bundle.AVAILABILITY, index=False)

    checks = bundle.validate_delivery(root)["checks"]
    assert checks["ipcch_0m_diagnostics_inherited_identical"] is False
    assert checks["ipcch_6m_diagnostics_inherited_identical"] is True
