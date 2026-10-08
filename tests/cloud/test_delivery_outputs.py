from pathlib import Path

import pandas as pd
import pytest

from cloud.orchestrator import delivery_outputs as out

V3 = Path(__file__).resolve().parents[2] / "Outcome/model_delivery/202609_h5/20260923_country_confidence_v3"
needs_v3 = pytest.mark.skipif(not V3.exists(), reason="September v3 delivery not available locally")


def _read(path):
    return pd.read_csv(path, low_memory=False, float_precision="round_trip",
                       dtype={"admin_code": "string", "area_id": "string", "polygon_id": "string"})


@needs_v3
@pytest.mark.parametrize("system", ["fewsnet", "ipcch"])
def test_mapping_reproduces_september_when_given_its_parameters(system):
    predictions = _read(V3 / f"{system}/polygon_predictions.csv")

    mapping = out.polygon_mapping(system, predictions, origin="2026-04", target="2026-09", horizon=5,
                                  package_path=f"{system}/model_package")

    # Compare the delivered artifact form: blank and NA cells serialize identically.
    september = _read(V3 / f"{system}/polygon_model_mapping.csv")
    assert mapping.to_csv(index=False) == september.to_csv(index=False)


@needs_v3
@pytest.mark.parametrize("system", ["fewsnet", "ipcch"])
def test_country_tables_keep_current_outcomes_and_blank_unsupported_diagnostics(system):
    predictions = _read(V3 / f"{system}/polygon_predictions.csv")
    census = _read(V3 / f"{system}/country_population_reference.csv")
    lookup = _read(V3 / "inputs/ipcch_april_panel.csv") if system == "ipcch" else None

    country, confidence = out.country_tables(system, predictions, census=census, area_lookup=lookup)

    september = _read(V3 / f"{system}/country_confidence.csv").set_index("ISO3")
    current = confidence.set_index("ISO3")
    assert list(country.columns) == list(out.SEPTEMBER_HEADERS[system]["country_predictions"])
    outcome = ["country_outcome_crisis"] if system == "fewsnet" else ["country_overall_phase", "country_maximum_phase"]
    for column in outcome:  # forecast-derived fields recomputed from current scores
        assert current[column].astype("Int64").equals(september.loc[current.index, column].astype("Int64"))
    for column in ("country_error_rate", "country_confidence_flag", "country_error_basis",
                   "country_error_sample_count", "country_error_eligible_area_count"):
        assert current[column].isna().all()  # never zero, never an h5 proxy
    if system == "ipcch":
        assert current["country_maximum_phase_uncertainty_status"].isna().all()
        assert set(current["country_overall_phase_availability"]) == {"available"}


def _fews_predictions():
    return pd.DataFrame({"admin_code": ["0", "1"], "ISO3": ["KEN", "KEN"], "population": [10.0, None],
                         "population_reference_period": ["2024-10", None], "population_source": ["raw", None]})


def test_availability_sidecar_and_frozen_schema_writes(tmp_path):
    predictions = _fews_predictions()
    table = out.polygon_diagnostics_unavailable("fewsnet", predictions, pd.Series(dtype=str))

    assert table["historical_sample_count"].isna().all() and table["polygon_confidence"].isna().all()
    rows = out.availability_rows("fewsnet", 6, polygons=["0", "1"], countries=["KEN"])
    assert set(zip(rows.diagnostic_family, rows.level)) == {("polygon_confidence", "polygon"), ("country_confidence", "country")}
    assert set(rows.status) == {"unavailable"} and set(rows.reason) == {"missing_evidence"}
    path = out.write_table(table, tmp_path / "scopes/6m/fewsnet/polygon_confidence.csv", system="fewsnet",
                           name="polygon_confidence")
    assert path.read_text().splitlines()[0] == ",".join(out.SEPTEMBER_HEADERS["fewsnet"]["polygon_confidence"])
    with pytest.raises(FileExistsError):
        out.write_table(table, path, system="fewsnet", name="polygon_confidence")
    with pytest.raises(out.OutputSchemaError):
        out.write_table(table.iloc[:, ::-1], tmp_path / "other.csv", system="fewsnet", name="polygon_confidence")


@pytest.mark.parametrize("phases", [[1, 7], [2, None], [None, None], [2.5, 3]])
def test_ipcch_phase_integrity_is_a_failure_not_a_blank(phases):
    predictions = pd.DataFrame({"polygon_id": ["0", "1"], "overall_phase_pred": phases})

    with pytest.raises(out.OutputSchemaError, match="integral 1..5"):
        out.validate_ipcch_phases(predictions)


def test_valid_ipcch_phases_including_zero_population_areas_pass():
    out.validate_ipcch_phases(pd.DataFrame({"polygon_id": ["0", "1"], "overall_phase_pred": [1, 5],
                                            "population_estimate": [0.0, 10.0]}))


def test_polygon_training_errors_unavailable_keeps_iso_and_blank_counts():
    predictions = pd.DataFrame({"polygon_id": ["7", "8"]})

    table = out.polygon_diagnostics_unavailable("ipcch", predictions, pd.Series({"7": "NGA", "8": "MLI"}))

    assert table.columns.tolist() == list(out.SEPTEMBER_HEADERS["ipcch"]["polygon_training_errors"])
    assert table["ISO3"].tolist() == ["NGA", "MLI"] and table["training_sample_count"].isna().all()


DECLARED = {"status": "available", "evidence_model_package_id": "pkg/6m", "evidence_horizon_months": 6}
IDENTITY = {"model_package_id": "pkg/6m", "horizon_months": 6, "basis": "package_validation_split",
            "period": "2023-10..2026-02"}
ACCEPT_FEWS = {"system": "fewsnet", "origin": "2026-10", "period": "2023-10..2026-02"}
ACCEPT_IPCCH = {"system": "ipcch", "origin": "2026-10", "period": None, "latest_end": "2026-04"}
RESIDUAL_IDENTITY = {"model_package_id": "pkg/scope_6m", "horizon_months": 6, "basis": "training_resubstitution",
                     "period": "2020-01..2020-04"}


def _area(**identity):
    frame = pd.DataFrame({"polygon_id": ["0", "1"], "sample_count": [4, 3], "error_count": [1, 0]})
    return frame.assign(**{**IDENTITY, **identity})


@pytest.mark.parametrize(
    ("mutate", "declared", "message"),
    [
        (lambda f: f.assign(horizon_months=5), DECLARED, "belongs to pkg/6m/5"),
        (lambda f: f.assign(model_package_id="h5"), DECLARED, "belongs to h5/6"),
        (lambda f: f, {**DECLARED, "evidence_model_package_id": "other"}, "declared other/6"),
        (lambda f: f.assign(basis=["a", "b"]), DECLARED, "one non-blank"),
        (lambda f: f.assign(period=""), DECLARED, "one non-blank"),
        (lambda f: f.drop(columns=["basis"]), DECLARED, "identity columns"),
        (lambda f: f.drop(columns=["error_count"]), DECLARED, "lacks columns"),
        (lambda f: pd.concat([f, f.iloc[:1]]), DECLARED, "unique"),
        (lambda f: f.assign(polygon_id=["0", "99"]), DECLARED, "roster IDs"),
        (lambda f: f.assign(error_count=[1, 5]), DECLARED, "exceeds"),
        (lambda f: f.assign(sample_count=[2.5, 3]), DECLARED, "non-negative integers"),
        (lambda f: f.assign(sample_count=[None, 3]), DECLARED, "non-negative integers"),
        # semantic acceptance: no h5 proxy relabelled for 0/6/12, no arbitrary or future period
        (lambda f: f.assign(basis="h5_validation_error_proxy_stage3_2021_2024"), DECLARED, "not the accepted"),
        (lambda f: f.assign(basis="training_resubstitution"), DECLARED, "not the accepted"),
        (lambda f: f.assign(period="2023-10..2026-03"), DECLARED, "recorded validation split"),
        (lambda f: f.assign(period="2021..2024"), DECLARED, "YYYY-MM..YYYY-MM"),
        (lambda f: f.assign(period="2026-02..2023-10"), DECLARED, "YYYY-MM..YYYY-MM"),
        (lambda f: f.assign(period="2026-01..2026-11"), DECLARED, "YYYY-MM..YYYY-MM"),
    ],
)
def test_corrupt_or_foreign_evidence_is_an_integrity_failure(mutate, declared, message):
    with pytest.raises(out.EvidenceIntegrityError, match=message):
        out.area_evidence(mutate(_area()), roster=["0", "1"], model_package_id="pkg/6m", horizon=6, declared=declared,
                          acceptance=ACCEPT_FEWS)


def test_ipcch_area_evidence_accepts_training_resubstitution_only():
    frame = _area(basis="training_resubstitution", period="2014-01..2026-04")
    table, identity = out.area_evidence(frame, roster=["0", "1"], model_package_id="pkg/6m", horizon=6,
                                        declared=DECLARED, acceptance=ACCEPT_IPCCH)
    assert identity["basis"] == "training_resubstitution" and len(table) == 2
    with pytest.raises(out.EvidenceIntegrityError, match="not the accepted"):
        out.area_evidence(_area(), roster=["0", "1"], model_package_id="pkg/6m", horizon=6, declared=DECLARED,
                          acceptance=ACCEPT_IPCCH)
    # September 2026 residual/error evidence for an April-2026 training cutoff is not resubstitution
    late = _area(basis="training_resubstitution", period="2014-01..2026-09")
    with pytest.raises(out.EvidenceIntegrityError, match="training cutoff '2026-04'"):
        out.area_evidence(late, roster=["0", "1"], model_package_id="pkg/6m", horizon=6, declared=DECLARED,
                          acceptance=ACCEPT_IPCCH)
    with pytest.raises(out.EvidenceIntegrityError, match="training cutoff None"):
        out.area_evidence(frame, roster=["0", "1"], model_package_id="pkg/6m", horizon=6, declared=DECLARED,
                          acceptance={**ACCEPT_IPCCH, "latest_end": None})


def test_ipcch_training_cutoff_comes_from_the_package_manifest(tmp_path):
    (tmp_path / "model_package_manifest.json").write_text('{"training_cutoff": "2026-04-01"}')
    assert out.ipcch_training_cutoff_month(tmp_path) == "2026-04"


def test_fewsnet_validation_period_comes_from_the_package_report(tmp_path):
    (tmp_path / "training_report.json").write_text('{"validation_target_month_range": {"start": "2023-10", "end": "2026-02"}}')
    assert out.fewsnet_validation_period(tmp_path) == "2023-10..2026-02"


@needs_v3
@pytest.mark.parametrize("system", ["fewsnet", "ipcch"])
def test_supported_evidence_reproduces_v3_arithmetic_with_its_own_basis(system):
    predictions = _read(V3 / f"{system}/polygon_predictions.csv")
    census = _read(V3 / f"{system}/country_population_reference.csv")
    lookup = _read(V3 / "inputs/ipcch_april_panel.csv") if system == "ipcch" else None
    name = "polygon_confidence" if system == "fewsnet" else "polygon_training_errors"
    v3_polygons = _read(V3 / f"{system}/{name}.csv")
    counts = (v3_polygons[["polygon_id", "historical_sample_count", "historical_error_count"]] if system == "fewsnet"
              else v3_polygons[["polygon_id", "training_sample_count", "training_error_count"]])
    counts.columns = ["polygon_id", "sample_count", "error_count"]
    v3_country = _read(V3 / f"{system}/country_confidence.csv")
    # Arithmetic replay only: v3's own counts under a label/period accepted for the test package.
    period = "2021-01..2024-12"
    counts = counts.dropna().assign(model_package_id="pkg", horizon_months=5, basis=out.EVIDENCE_BASIS[system],
                                    period=period)
    roster = predictions["admin_code" if system == "fewsnet" else "polygon_id"]
    evidence, identity = out.area_evidence(counts, roster=roster, model_package_id="pkg", horizon=5, declared={
        "evidence_model_package_id": "pkg", "evidence_horizon_months": 5},
        acceptance={"system": system, "origin": "2026-10", "period": period, "latest_end": "2026-04"})
    iso = (lookup[["area_id", "country"]].merge(census[["country", "ISO3"]], on="country").set_index("area_id")["ISO3"]
           if system == "ipcch" else pd.Series(dtype=str))

    polygons, errors = out.supported_diagnostics(system, predictions, evidence, identity=identity, iso_by_polygon=iso)
    _, confidence = out.country_tables(system, predictions, census=census, area_lookup=lookup, country_errors=errors)

    mine, theirs = confidence.set_index("ISO3"), v3_country.set_index("ISO3")
    for column in ("country_error_rate", "country_error_eligible_area_count", "country_error_sample_count",
                   "country_error_mistake_count", "country_confidence_flag"):
        assert mine[column].astype(str).equals(theirs.loc[mine.index, column].astype(str)), column
    assert set(mine["country_error_basis"]) == {out.EVIDENCE_BASIS[system]}  # the evidence's own basis
    assert set(mine["country_error_evidence_period"].dropna()) == {period}
    assert polygons.columns.tolist() == list(out.SEPTEMBER_HEADERS[system][name])


def _ipcch_iso(census):
    lookup = _read(V3 / "inputs/ipcch_april_panel.csv")
    return lookup, lookup[["area_id", "country"]].merge(census[["country", "ISO3"]], on="country").set_index("area_id")["ISO3"]


@needs_v3
def test_maximum_phase_residual_transfer_reproduces_v3_exactly():
    predictions = _read(V3 / "ipcch/polygon_predictions.csv")
    census = _read(V3 / "ipcch/country_population_reference.csv")
    _, iso = _ipcch_iso(census)
    replay = _read(V3 / "reports/ipcch_four_target_training_replay.csv")
    period = f"{replay['target_month'].min()}..{replay['target_month'].max()}"
    replay = replay.assign(model_package_id="pkg/scope_5m", horizon_months=5, basis="training_resubstitution",
                           period=period)
    residuals, _ = out.residual_evidence(replay, roster=predictions["polygon_id"], model_package_id="pkg/scope_5m",
                                         horizon=5, declared={"evidence_model_package_id": "pkg/scope_5m",
                                                              "evidence_horizon_months": 5},
                                         acceptance={"system": "ipcch", "origin": "2026-10", "period": None,
                                                     "latest_end": "2026-04"})
    countries = sorted(set(predictions["polygon_id"].map(iso).dropna()))

    mine = out.maximum_phase_diagnostics(predictions, residuals, iso, countries).set_index("ISO3")

    theirs = _read(V3 / "ipcch/country_confidence.csv").set_index("ISO3").loc[mine.index]
    for column in out.MAXIMUM_PHASE_FIELDS:
        assert mine[column].astype(str).equals(theirs[column].astype(str)), column


def _two_country_scope():
    predictions = pd.DataFrame({"polygon_id": ["a", "b", "c"], "area_id": ["a", "b", "c"],
                                "phase2_worse_score": [0.1, 0.3, 0.1], "phase3_worse_score": [0.0, 0.1, 0.0],
                                "phase4_worse_score": [0.0, 0.0, 0.0], "phase5_worse_score": [0.0, 0.0, 0.0],
                                "overall_phase_pred": [1, 2, 1]})
    iso = pd.Series({"a": "AAA", "b": "AAA", "c": "CCC"})
    rows = []
    for month, shift in (("2020-01", 0.0), ("2020-02", 0.15), ("2020-03", 0.0)):
        for pid in ("a", "b"):
            rows.append({"polygon_id": pid, "target_month": month, "phase2_worse_residual": 0.0,
                         "phase3_worse_residual": shift, "phase4_worse_residual": 0.0, "phase5_worse_residual": 0.0})
    rows.append({"polygon_id": "c", "target_month": "2020-01", "phase2_worse_residual": 0.2,
                 "phase3_worse_residual": 0.0, "phase4_worse_residual": 0.0, "phase5_worse_residual": 0.0})
    rows.append({"polygon_id": "a", "target_month": "2020-04", "phase2_worse_residual": 0.5,  # incomplete month
                 "phase3_worse_residual": 0.5, "phase4_worse_residual": 0.5, "phase5_worse_residual": 0.5})
    return predictions, iso, pd.DataFrame(rows)


def test_maximum_phase_uses_complete_months_only_and_restarts_the_seed():
    predictions, iso, residuals = _two_country_scope()

    first = out.maximum_phase_diagnostics(predictions, residuals, iso, ["AAA", "CCC"]).set_index("ISO3")
    second = out.maximum_phase_diagnostics(predictions, residuals, iso, ["AAA", "CCC"]).set_index("ISO3")

    pd.testing.assert_frame_equal(first, second)  # deterministic per call (per scope)
    assert first.loc["AAA", "country_maximum_phase_history_month_count"] == 3  # 2020-04 is incomplete
    assert first.loc["AAA", "country_maximum_phase_error_probability_proxy"] == pytest.approx(1 / 3)  # Feb -> phase 3
    assert first.loc["AAA", "country_maximum_phase_uncertainty_status"] == "supported"
    assert first.loc["CCC", "country_maximum_phase_uncertainty_status"] == "single_month"
    assert first.loc["CCC", "country_maximum_phase_error_probability_proxy"] == 1.0
    assert pd.isna(first.loc["CCC", "country_maximum_phase_error_probability_ci_lower"])
    assert set(first["country_maximum_phase_uncertainty_method"]) == {out.MAXIMUM_PHASE_METHOD}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda f: f.assign(target_month=["2020-13", *f["target_month"].iloc[1:]]), "YYYY-MM"),
        (lambda f: f.assign(phase2_worse_residual=float("inf")), "finite"),
        (lambda f: f.assign(phase2_worse_residual="x"), "finite"),
        (lambda f: pd.concat([f, f.iloc[:1]]), "unique"),
        (lambda f: f.drop(columns=["phase5_worse_residual"]), "lacks columns"),
        (lambda f: f.assign(horizon_months=12), "belongs to"),
        (lambda f: f.assign(period="2020-02..2020-04"), "inside the evidence period"),
        (lambda f: f.assign(basis="package_validation_split"), "not the accepted"),
    ],
)
def test_corrupt_residual_evidence_is_an_integrity_failure(mutate, message):
    _, _, residuals = _two_country_scope()
    frame = mutate(residuals.assign(**RESIDUAL_IDENTITY))

    with pytest.raises(out.EvidenceIntegrityError, match=message):
        out.residual_evidence(frame, roster=["a", "b", "c"], model_package_id="pkg/scope_6m", horizon=6,
                              declared={"evidence_model_package_id": "pkg/scope_6m", "evidence_horizon_months": 6},
                              acceptance=ACCEPT_IPCCH)


REF = {"uri": "gs://b/evidence.csv", "generation": "4", "sha256": "0" * 64}
AVAILABLE = {"status": "available", "ref": REF, "evidence_model_package_id": "pkg/6m", "evidence_horizon_months": 6}


def test_declarations_default_to_missing_evidence_and_keep_reasons():
    decl = out.normalise_declarations("ipcch", 6, {"maximum_phase": {"status": "unavailable", "reason": "no_complete_history"}})

    assert decl["polygon_training_errors"] == {"status": "unavailable", "reason": "missing_evidence"}
    assert decl["maximum_phase"]["reason"] == "no_complete_history"


@pytest.mark.parametrize(
    ("families", "message"),
    [
        ({"polygon_confidence": {**AVAILABLE, "ref": {}}}, "hash-bound ref"),
        ({"polygon_confidence": {**AVAILABLE, "evidence_horizon_months": 5}}, "declare this horizon"),
        ({"polygon_confidence": {**AVAILABLE, "evidence_model_package_id": ""}}, "declare this horizon"),
        ({"polygon_confidence": {"status": "unavailable"}}, "needs a reason"),
        ({"maximum_phase": AVAILABLE}, "unknown diagnostic families"),
    ],
)
def test_invalid_family_declarations_fail(families, message):
    with pytest.raises(out.EvidenceIntegrityError, match=message):
        out.normalise_declarations("fewsnet", 6, families)


def test_evidence_bytes_must_match_the_ref_hash():
    decl = out.normalise_declarations("fewsnet", 6, {"polygon_confidence": AVAILABLE})

    with pytest.raises(out.EvidenceIntegrityError, match="do not match the ref"):
        out.scope_diagnostics("fewsnet", 6, _fews_predictions(), declarations=decl,
                              evidence_bytes=lambda family: b"polygon_id,sample_count,error_count\n0,3,1\n",
                              package_id="pkg/6m", polygons=["0", "1"], census=pd.DataFrame(), area_lookup=None,
                              iso_by_polygon=pd.Series(dtype=str), origin="2026-10",
                              accepted_period="2023-10..2026-02")


def _ref(data):
    import hashlib

    return {"uri": "gs://b/e.csv", "generation": "9", "sha256": hashlib.sha256(data).hexdigest()}


def test_ipcch_maximum_phase_family_alone_reports_available_limited_and_frozen_bytes(monkeypatch):
    predictions, iso, residuals = _two_country_scope()
    data = residuals.assign(**RESIDUAL_IDENTITY).to_csv(index=False).encode()
    decl = out.normalise_declarations("ipcch", 6, {"maximum_phase": {
        "status": "available", "ref": _ref(data), "evidence_model_package_id": "pkg/scope_6m",
        "evidence_horizon_months": 6}})
    seen = {}

    def fake_tables(system, preds, *, census, area_lookup, country_errors=None, maximum_phase=None):
        seen["errors"], seen["maximum"] = country_errors, maximum_phase
        confidence = pd.DataFrame({"ISO3": ["AAA", "CCC"]}).merge(maximum_phase, on="ISO3")
        return pd.DataFrame(), confidence

    monkeypatch.setattr(out, "country_tables", fake_tables)
    diag = out.scope_diagnostics("ipcch", 6, predictions, declarations=decl, evidence_bytes=lambda family: data,
                                 package_id="pkg/scope_6m", polygons=["a", "b", "c"], census=pd.DataFrame(),
                                 area_lookup=pd.DataFrame(), iso_by_polygon=iso, origin="2026-10",
                                 training_cutoff="2026-04")

    assert seen["errors"] is None and diag["frozen_evidence"] == {"maximum_phase": data}
    rows = diag["availability"].set_index(["diagnostic_family", "entity_id"])
    assert rows.loc[("maximum_phase", "AAA"), "status"] == "available"
    assert tuple(rows.loc[("maximum_phase", "CCC"), ["status", "reason"]]) == ("limited", "single_month_interval_unavailable")
    assert rows.loc[("maximum_phase", "CCC"), "evidence_ref"] == "gs://b/e.csv#9"
    assert set(rows.loc["polygon_training_errors", "reason"]) == {"missing_evidence"}  # independent families
    assert diag["evidence_identity"]["maximum_phase"]["basis"] == "training_resubstitution"


def _fews_scope(monkeypatch):
    seen = {}

    def fake_tables(system, preds, *, census, area_lookup, country_errors=None, maximum_phase=None):
        seen["errors"] = country_errors
        confidence = pd.DataFrame({"ISO3": ["KEN"], "country_error_rate": [
            None if country_errors is None else country_errors.set_index("ISO3").loc["KEN", "country_error_rate"]]})
        return pd.DataFrame(), confidence

    monkeypatch.setattr(out, "country_tables", fake_tables)
    return seen


def _evidence(counts, **identity):
    frame = pd.DataFrame({"polygon_id": ["0", "1"], "sample_count": counts[0], "error_count": counts[1]})
    return frame.assign(**{**IDENTITY, **identity}).to_csv(index=False).encode()


def _scope(declared, data):
    decl = out.normalise_declarations("fewsnet", 6, declared)
    return out.scope_diagnostics("fewsnet", 6, _fews_predictions().assign(population=[10.0, 5.0]),
                                 declarations=decl, evidence_bytes=lambda family: data[family], package_id="pkg/6m",
                                 polygons=["0", "1"], census=pd.DataFrame(), area_lookup=None,
                                 iso_by_polygon=pd.Series(dtype=str), origin="2026-10",
                                 accepted_period="2023-10..2026-02")


def test_country_family_is_selected_and_frozen_independently_of_the_polygon_family(monkeypatch):
    seen = _fews_scope(monkeypatch)
    country = _evidence(([4, 2], [1, 0]))
    diag = _scope({"country_confidence": {**AVAILABLE, "ref": _ref(country)}}, {"country_confidence": country})

    # population-weighted area error rates: (10 * 1/4 + 5 * 0/2) / 15
    assert seen["errors"].set_index("ISO3").loc["KEN", "country_error_rate"] == pytest.approx(2.5 / 15)
    assert diag["frozen_evidence"] == {"country_confidence": country}
    assert diag["polygon_table"]["historical_sample_count"].isna().all()  # polygon family stays unavailable
    rows = diag["availability"].set_index(["diagnostic_family", "entity_id"])
    assert tuple(rows.loc[("polygon_confidence", "0"), ["status", "reason"]]) == ("unavailable", "missing_evidence")
    assert rows.loc[("country_confidence", "KEN"), "status"] == "available"


def test_polygon_and_country_families_may_use_different_accepted_refs(monkeypatch):
    seen = _fews_scope(monkeypatch)
    polygon, country = _evidence(([4, 2], [1, 0])), _evidence(([5, 5], [5, 0]))
    diag = _scope({"polygon_confidence": {**AVAILABLE, "ref": _ref(polygon)},
                   "country_confidence": {**AVAILABLE, "ref": {**_ref(country), "uri": "gs://b/c.csv"}}},
                  {"polygon_confidence": polygon, "country_confidence": country})

    assert diag["polygon_table"]["historical_error_count"].tolist() == [1, 0]
    assert seen["errors"].set_index("ISO3").loc["KEN", "country_error_rate"] == pytest.approx((10 * 1.0) / 15)
    assert diag["frozen_evidence"] == {"polygon_confidence": polygon, "country_confidence": country}


def test_polygon_family_alone_leaves_country_errors_blank_with_their_reason(monkeypatch):
    seen = _fews_scope(monkeypatch)
    polygon = _evidence(([4, 2], [1, 0]))
    diag = _scope({"polygon_confidence": {**AVAILABLE, "ref": _ref(polygon)},
                   "country_confidence": {"status": "unavailable", "reason": "no_eligible_area_history"}},
                  {"polygon_confidence": polygon})

    assert seen["errors"] is None
    rows = diag["availability"].set_index(["diagnostic_family", "entity_id"])
    assert tuple(rows.loc[("country_confidence", "KEN"), ["status", "reason"]]) == (
        "unavailable", "no_eligible_area_history")
