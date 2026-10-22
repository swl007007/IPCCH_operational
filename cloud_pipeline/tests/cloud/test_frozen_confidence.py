"""Frozen FEWS confidence outputs (2026-10 retrain): copied unchanged, current outcomes recomputed."""

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from cloud.orchestrator import delivery_manifest as dm
from cloud.orchestrator import delivery_outputs as do
from fewsnet_partitioned_rf_pipeline.local.outputs import _read_local_prediction_csv

FALLBACK = Path(__file__).resolve().parents[2] / "fallback/october_2026"
SOURCE_PACKAGE = "local-202604-57cb3b981198-510375f58cd8"
needs_fallback = pytest.mark.skipif(not (FALLBACK / "scopes/0m/fewsnet/polygon_confidence.csv").is_file(),
                                    reason="accepted October fallback outputs not present")


def _ref(data: bytes, name: str) -> dict:
    return {"uri": f"gs://source/{name}", "generation": "1", "sha256": hashlib.sha256(data).hexdigest()}


def _scope(horizon: int, *, polygon_bytes=None, country_bytes=None, period=None):
    scope = FALLBACK / f"scopes/{horizon}m/fewsnet"
    polygon = polygon_bytes if polygon_bytes is not None else (scope / "polygon_confidence.csv").read_bytes()
    country = country_bytes if country_bytes is not None else (scope / "country_confidence.csv").read_bytes()
    availability = (FALLBACK / "reports/diagnostic_availability.csv").read_bytes()
    basis, approved_period = do.APPROVED_PROXY_EVIDENCE[("fewsnet", horizon)]
    blobs = {"polygon_confidence": polygon, "country_confidence": country,
             "polygon_confidence.availability": availability, "country_confidence.availability": availability}
    declared = {family: {"status": do.FROZEN_OUTPUT, "ref": _ref(blobs[family], f"{family}.csv"),
                         "availability_ref": _ref(availability, "diagnostic_availability.csv"),
                         "source_delivery_id": "oct-confidence-20261009b",
                         "evidence_model_package_id": f"{SOURCE_PACKAGE}/{horizon}m",
                         "evidence_horizon_months": horizon, "evidence_basis": basis,
                         "evidence_period": period or approved_period}
                for family in ("polygon_confidence", "country_confidence")}
    return blobs, declared


def _inputs(horizon: int):
    predictions = _read_local_prediction_csv(FALLBACK / f"scopes/{horizon}m/fewsnet/polygon_predictions.csv")
    census = pd.read_csv(FALLBACK / "shared/fewsnet/country_population_reference.csv", dtype=str,
                         keep_default_na=False).replace({"": pd.NA})
    return predictions, census


def _run(horizon, predictions, census, blobs, declared):
    declarations = do.normalise_declarations("fewsnet", horizon, declared)
    return do.scope_diagnostics("fewsnet", horizon, predictions, declarations=declarations,
                                evidence_bytes=lambda family: blobs[family],
                                package_id=f"full-202610-aaaaaaaaaaaa-bbbbbbbbbbbb/{horizon}m",
                                polygons=predictions["admin_code"].astype(str), census=census, area_lookup=None,
                                iso_by_polygon=pd.Series(dtype=str), origin="2026-10")


@needs_fallback
@pytest.mark.parametrize("horizon", [0, 6, 12])
def test_frozen_tables_are_copied_and_current_outcomes_recomputed(tmp_path, horizon):
    predictions, census = _inputs(horizon)
    predictions["probability_crisis"] = 0.99  # new scores: every country now has a crisis outcome
    blobs, declared = _scope(horizon)
    diag = _run(horizon, predictions, census, blobs, declared)

    written = do.write_table(diag["polygon_table"], tmp_path / "polygon_confidence.csv", system="fewsnet",
                             name="polygon_confidence")
    assert written.read_bytes() == blobs["polygon_confidence"]  # byte-identical copy

    source = pd.read_csv(FALLBACK / f"scopes/{horizon}m/fewsnet/country_confidence.csv", dtype=str,
                         keep_default_na=False).set_index("ISO3")
    do.write_table(diag["confidence"], tmp_path / "country_confidence.csv", system="fewsnet",
                   name="country_confidence")
    new = pd.read_csv(tmp_path / "country_confidence.csv", dtype=str, keep_default_na=False).set_index("ISO3")
    columns = list(do.FROZEN_FEWSNET_COUNTRY_COLUMNS)
    pd.testing.assert_frame_equal(new.loc[source.index, columns], source[columns])  # values and blank masks
    assert set(new["country_outcome_crisis"]) == {"1"} and set(new["country_outcome_crisis_threshold"]) == {"0.5"}
    assert diag["evidence_identity"]["country_confidence"]["model_package_id"] == f"{SOURCE_PACKAGE}/{horizon}m"

    availability = pd.read_csv(FALLBACK / "reports/diagnostic_availability.csv", dtype=str, keep_default_na=False)
    expected = availability[(availability["model_system"] == "fewsnet")
                            & (availability["horizon_months"] == str(horizon))]
    got = diag["availability"].astype(str)
    assert sorted(map(tuple, got.itertuples(index=False))) == sorted(map(tuple, expected.itertuples(index=False)))
    assert set(diag["frozen_evidence"]) == set(blobs)


@needs_fallback
def test_frozen_outputs_reject_tampering_and_wrong_lineage():
    predictions, census = _inputs(0)
    blobs, declared = _scope(0)
    with pytest.raises(do.EvidenceIntegrityError, match="approved historical basis"):
        do.normalise_declarations("fewsnet", 0, _scope(0, period="2023-10..2026-02")[1])
    tampered = dict(blobs, polygon_confidence=blobs["polygon_confidence"] + b"\n")
    with pytest.raises(do.EvidenceIntegrityError, match="do not match"):
        _run(0, predictions, census, tampered, declared)
    short = b"\n".join(blobs["polygon_confidence"].split(b"\n")[:-2]) + b"\n"
    blobs_short, declared_short = _scope(0, polygon_bytes=short)
    with pytest.raises(do.EvidenceIntegrityError, match="keys must equal"):
        _run(0, predictions, census, blobs_short, declared_short)
    with pytest.raises(do.EvidenceIntegrityError, match="FEWS-only"):
        do.normalise_declarations("ipcch", 0, {"country_confidence": declared["country_confidence"]})


def _manifest_entries(frozen):
    entries = []
    for system in dm.SYSTEMS:
        for horizon in dm.HORIZONS_MONTHS:
            for family in dm.DIAGNOSTIC_FAMILIES[system]:
                if system == "fewsnet":
                    basis, period = do.APPROVED_PROXY_EVIDENCE[("fewsnet", horizon)]
                    entries.append({"system": system, "horizon_months": horizon, "family": family,
                                    "status": "frozen_output", "evidence": _ref(b"x", family),
                                    "source_availability": _ref(b"y", "availability"),
                                    "source_delivery_id": "oct-confidence-20261009b",
                                    "evidence_model_package_id": f"{SOURCE_PACKAGE}/{horizon}m",
                                    "evidence_horizon_months": horizon, "evidence_basis": basis,
                                    "evidence_period": frozen.get(horizon, period)})
                else:
                    entries.append({"system": system, "horizon_months": horizon, "family": family,
                                    "status": "unavailable", "evidence": None, "reason": "missing_evidence"})
    return entries


def test_manifest_accepts_frozen_fews_outputs_distinct_from_the_scored_package():
    models = {(system, horizon): f"new/{system}/{horizon}" for system in dm.SYSTEMS for horizon in dm.HORIZONS_MONTHS}
    dm._diagnostics(_manifest_entries({}), models)
    with pytest.raises(dm.DeliveryManifestError, match="approved"):
        dm._diagnostics(_manifest_entries({6: "2023-10..2026-02"}), models)
