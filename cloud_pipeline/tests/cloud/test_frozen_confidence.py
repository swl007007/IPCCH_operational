"""Frozen FEWS confidence outputs (2026-10 retrain): copied unchanged, current outcomes recomputed."""

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from cloud.orchestrator import delivery_manifest as dm
from cloud.orchestrator import delivery_outputs as do
from fewsnet_partitioned_rf_pipeline.local.outputs import _read_local_prediction_csv

FALLBACK = Path(__file__).resolve().parents[2] / "fallback/october_2026"
EVIDENCE = Path(__file__).resolve().parents[2] / "bootstrap/evidence"
RAW = {0: "fewsnet_0m_stage3_fs1_area.csv", 6: "fewsnet_6m_stage3_fs2_area.csv", 12: "fewsnet_12m_stage3_fs3_area.csv"}
SOURCE_PACKAGE = "local-202604-57cb3b981198-510375f58cd8"
needs_fallback = pytest.mark.skipif(not (FALLBACK / "scopes/0m/fewsnet/polygon_confidence.csv").is_file()
                                    or not (EVIDENCE / RAW[0]).is_file(),
                                    reason="accepted October fallback outputs/evidence not present")


def _ref(data: bytes, name: str) -> dict:
    return {"uri": f"gs://source/{name}", "generation": "1", "sha256": hashlib.sha256(data).hexdigest()}


def _scope(horizon: int, *, polygon_bytes=None, country_bytes=None, period=None, raw_bytes=None):
    scope = FALLBACK / f"scopes/{horizon}m/fewsnet"
    polygon = polygon_bytes if polygon_bytes is not None else (scope / "polygon_confidence.csv").read_bytes()
    country = country_bytes if country_bytes is not None else (scope / "country_confidence.csv").read_bytes()
    availability = (FALLBACK / "reports/diagnostic_availability.csv").read_bytes()
    raw = raw_bytes if raw_bytes is not None else (EVIDENCE / RAW[horizon]).read_bytes()
    source = (FALLBACK / "reports/fewsnet_diagnostic_declarations.json").read_bytes()
    basis, approved_period = do.APPROVED_PROXY_EVIDENCE[("fewsnet", horizon)]
    blobs = {}
    for family, table in (("polygon_confidence", polygon), ("country_confidence", country)):
        blobs.update({f"{family}.output": table, f"{family}.availability": availability,
                      f"{family}.source_evidence": raw, f"{family}.source_declarations": source})
    declared = {family: {"status": do.FROZEN_OUTPUT, "ref": _ref(blobs[f"{family}.output"], f"{family}.csv"),
                         "availability_ref": _ref(availability, "diagnostic_availability.csv"),
                         "source_evidence_ref": _ref(raw, RAW[horizon]),
                         "source_declarations_ref": _ref(source, "fewsnet_diagnostic_declarations.json"),
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
    assert written.read_bytes() == blobs["polygon_confidence.output"]  # byte-identical copy

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
    assert set(diag["frozen_evidence"]) == set(blobs)  # raw evidence + source declarations retained too
    identity = diag["evidence_identity"]["polygon_confidence"]
    assert identity["attachment"] == {"mode": "frozen_output", "recomputed": False,
                                      "scored_model_package_id": f"full-202610-aaaaaaaaaaaa-bbbbbbbbbbbb/{horizon}m"}

    from cloud.orchestrator.deliver import freeze_diagnostic_evidence
    record = freeze_diagnostic_evidence(tmp_path / "bundle", "fewsnet", horizon,
                                        do.normalise_declarations("fewsnet", horizon, declared), diag)
    paths = record["polygon_confidence"]["frozen_paths"]
    assert set(paths) == {"output", "availability", "source_evidence", "source_declarations"}
    assert all(path.startswith("inputs/evidence/frozen/") for path in paths.values())
    assert (tmp_path / "bundle" / paths["source_evidence"]).read_bytes() == (EVIDENCE / RAW[horizon]).read_bytes()


@needs_fallback
def test_frozen_outputs_reject_tampering_and_wrong_lineage():
    predictions, census = _inputs(0)
    blobs, declared = _scope(0)
    with pytest.raises(do.EvidenceIntegrityError, match="approved historical basis"):
        do.normalise_declarations("fewsnet", 0, _scope(0, period="2023-10..2026-02")[1])
    tampered = dict(blobs, **{"polygon_confidence.output": blobs["polygon_confidence.output"] + b"\n"})
    with pytest.raises(do.EvidenceIntegrityError, match="do not match"):
        _run(0, predictions, census, tampered, declared)
    short = b"\n".join(blobs["polygon_confidence.output"].split(b"\n")[:-2]) + b"\n"
    blobs_short, declared_short = _scope(0, polygon_bytes=short)
    with pytest.raises(do.EvidenceIntegrityError, match="keys must equal"):
        _run(0, predictions, census, blobs_short, declared_short)
    wrong_raw = (EVIDENCE / RAW[6]).read_bytes()  # another horizon's raw evidence: lineage must fail
    blobs_raw, declared_raw = _scope(0, raw_bytes=wrong_raw)
    with pytest.raises(do.EvidenceIntegrityError, match="does not bind these raw evidence bytes"):
        _run(0, predictions, census, blobs_raw, declared_raw)
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
                                    "source_evidence": _ref(b"z", "raw"),
                                    "source_declarations": _ref(b"w", "declarations"),
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
