import pytest

from cloud.orchestrator import deliver
from cloud.orchestrator.delivery_outputs import OutputSchemaError


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_finalize_streams_per_system_sidecars_preserving_blanks(tmp_path):
    for name in ("feature_fill_audit", "diagnostic_availability"):
        _write(tmp_path / f"reports/fewsnet_{name}.csv", "a,b\n1,\n2,x\n")
        _write(tmp_path / f"reports/ipcch_{name}.csv", "a,b\n3,y\n")

    deliver.finalize(tmp_path)

    assert (tmp_path / "reports/feature_fill_audit.csv").read_text() == "a,b\n1,\n2,x\n3,y\n"
    with pytest.raises(FileExistsError):
        deliver.finalize(tmp_path)


def test_finalize_rejects_mismatched_headers(tmp_path):
    for name in ("feature_fill_audit", "diagnostic_availability"):
        _write(tmp_path / f"reports/fewsnet_{name}.csv", "a,b\n1,2\n")
        _write(tmp_path / f"reports/ipcch_{name}.csv", "a,c\n3,4\n")

    with pytest.raises(OutputSchemaError, match="headers differ"):
        deliver.finalize(tmp_path)


def _checkpoint(root):
    import json

    from cloud.common.object_refs import sha256_file
    from fewsnet_partitioned_rf_pipeline.core.normalization import NORMALIZATION_VERSION

    for name, text in (("inputs/fewsnet_base_panel.csv", "admin_code,month_key\n1,2026-10\n"),
                       ("inputs/fewsnet_extra_observations.csv", "admin_code,month_key\n"),
                       ("inputs/fewsnet_extended_raw.csv", "a\n1\n"), ("inputs/fewsnet_normalized_panel.csv", "a\n2\n")):
        _write(root / name, text)
    def sha(name):
        return sha256_file(root / name)

    _write(root / "inputs/fewsnet_fill_sources.json", json.dumps({
        "panel_rows": {"sha256": sha("inputs/fewsnet_base_panel.csv")},
        "extra_observations": {"sha256": sha("inputs/fewsnet_extra_observations.csv")}}))
    _write(root / "reports/fewsnet_normalization_audit.json", json.dumps({
        "normalization_version": NORMALIZATION_VERSION,
        "source_panel": {"sha256": sha("inputs/fewsnet_extended_raw.csv")},
        "output_panel": {"sha256": sha("inputs/fewsnet_normalized_panel.csv")}}))


def test_checkpoint_resume_copies_hash_bound_files_into_a_new_directory(tmp_path):
    _checkpoint(tmp_path / "d")
    result = deliver._verified_checkpoint(tmp_path / "d", tmp_path / "e")
    assert all(result["checks"].values())
    for name in deliver.FEWSNET_CHECKPOINT_FILES:
        assert (tmp_path / "e" / name).read_bytes() == (tmp_path / "d" / name).read_bytes()
    assert not (tmp_path / "e/inputs/fewsnet_fill_sources.json").exists()  # rewritten by the resumed run


def test_checkpoint_resume_rejects_inconsistent_or_in_place_use(tmp_path):
    _checkpoint(tmp_path / "d")
    with pytest.raises(ValueError, match="new output directory"):
        deliver._verified_checkpoint(tmp_path / "d", tmp_path / "d")
    (tmp_path / "d/inputs/fewsnet_normalized_panel.csv").write_text("a\n3\n")
    with pytest.raises(ValueError, match="not internally consistent"):
        deliver._verified_checkpoint(tmp_path / "d", tmp_path / "e")
    assert not (tmp_path / "e").exists()


class _Reader:
    def __init__(self, objects):
        self.objects = objects

    def read_bytes(self, uri, generation):
        return self.objects.get((uri, generation))


def _request(data):
    import hashlib

    ref = {"uri": "gs://b/evidence/ipcch_6m_residuals.csv", "generation": "7", "sha256": hashlib.sha256(data).hexdigest()}
    return {"validation_level": "structural", "diagnostics": [
        {"system": "ipcch", "horizon_months": 6, "family": "maximum_phase", "status": "available", "evidence": ref,
         "evidence_model_package_id": "pkg/scope_6m", "evidence_horizon_months": 6},
        {"system": "ipcch", "horizon_months": 6, "family": "polygon_training_errors", "status": "unavailable",
         "evidence": None, "reason": "missing_evidence"},
        {"system": "ipcch", "horizon_months": 6, "family": "country_confidence", "status": "unavailable",
         "evidence": None, "reason": "no_eligible_area_history"},
        {"system": "fewsnet", "horizon_months": 6, "family": "polygon_confidence", "status": "unavailable",
         "evidence": None, "reason": "missing_evidence"}]}, ref


def _residual_bytes():
    import pandas as pd

    rows = [{"polygon_id": pid, "target_month": month, "phase2_worse_residual": 0.0, "phase3_worse_residual": shift,
             "phase4_worse_residual": 0.0, "phase5_worse_residual": 0.0}
            for month, shift in (("2020-01", 0.0), ("2020-02", 0.15)) for pid in ("a", "b")]
    return pd.DataFrame(rows).assign(model_package_id="pkg/scope_6m", horizon_months=6, basis="training_resubstitution",
                                     period="2020-01..2020-02").to_csv(index=False).encode()


def test_request_diagnostics_reads_pinned_family_evidence_and_keeps_reasons():
    from cloud.orchestrator.prepare import ReferenceIdentityError

    data = _residual_bytes()
    request, ref = _request(data)
    selected = deliver.request_diagnostics(request, "ipcch", _Reader({(ref["uri"], ref["generation"]): data}))

    assert set(selected) == {6} and selected[6]["maximum_phase"]["evidence_bytes"] == data
    assert selected[6]["country_confidence"] == {"status": "unavailable", "reason": "no_eligible_area_history"}
    with pytest.raises(ReferenceIdentityError):
        deliver.request_diagnostics(request, "ipcch", _Reader({(ref["uri"], ref["generation"]): data + b" "}))
    with pytest.raises(ValueError, match="structural"):
        deliver.request_diagnostics({**request, "validation_level": None}, "ipcch", _Reader({}))


def test_manifest_evidence_replays_identically_from_the_frozen_bundle(tmp_path, monkeypatch):
    import json

    import pandas as pd

    from cloud.orchestrator import delivery_bundle
    from cloud.orchestrator import delivery_outputs as do

    def tables(system, predictions, *, census, area_lookup, country_errors=None, maximum_phase=None):
        return pd.DataFrame(), pd.DataFrame({"ISO3": ["AAA"]}).merge(maximum_phase, on="ISO3")

    monkeypatch.setattr(do, "country_tables", tables)
    predictions = pd.DataFrame({"polygon_id": ["a", "b"], "phase2_worse_score": [0.1, 0.3],
                                "phase3_worse_score": [0.0, 0.1], "phase4_worse_score": [0.0, 0.0],
                                "phase5_worse_score": [0.0, 0.0], "overall_phase_pred": [1, 2]})
    common = {"package_id": "pkg/scope_6m", "polygons": ["a", "b"], "census": pd.DataFrame(),
              "area_lookup": pd.DataFrame(), "iso_by_polygon": pd.Series({"a": "AAA", "b": "AAA"}), "origin": "2026-10",
              "training_cutoff": "2026-04"}
    data = _residual_bytes()
    request, ref = _request(data)
    declared = deliver.request_diagnostics(request, "ipcch", _Reader({(ref["uri"], ref["generation"]): data}))[6]
    declarations = do.normalise_declarations(
        "ipcch", 6, {f: {k: v for k, v in e.items() if k != "evidence_bytes"} for f, e in declared.items()})
    delivered = do.scope_diagnostics("ipcch", 6, predictions, declarations=declarations,
                                     evidence_bytes=lambda family: declared[family]["evidence_bytes"], **common)
    record = deliver.freeze_diagnostic_evidence(tmp_path, "ipcch", 6, declarations, delivered)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/ipcch_diagnostic_declarations.json").write_text(json.dumps({"6m": record}, default=str))

    replay_declarations, evidence_bytes = delivery_bundle.frozen_declarations(tmp_path, "ipcch", 6)
    replayed = do.scope_diagnostics("ipcch", 6, predictions, declarations=replay_declarations,
                                    evidence_bytes=evidence_bytes, **common)

    assert replay_declarations == declarations
    pd.testing.assert_frame_equal(replayed["availability"], delivered["availability"])
    pd.testing.assert_frame_equal(replayed["confidence"], delivered["confidence"])
    assert (tmp_path / "inputs/evidence/ipcch_6m_maximum_phase.csv").read_bytes() == data
    assert delivery_bundle.is_portable("inputs/evidence/ipcch_6m_maximum_phase.csv")
    assert delivered["confidence"].loc[0, "country_maximum_phase_history_month_count"] == 2
    with pytest.raises(FileExistsError):  # frozen evidence is create-only
        deliver.freeze_diagnostic_evidence(tmp_path, "ipcch", 6, declarations, delivered)


def test_streamed_audit_equals_one_concatenated_write(tmp_path):
    import pandas as pd

    from cloud.orchestrator import delivery_outputs as do

    parts = [pd.DataFrame({"polygon_id": ["1", "2"], "staleness_months": pd.array([0, None], dtype="Int64"),
                           "value": [0.1, None], "flag": [True, False]}) for _ in range(3)]
    writer = deliver._AuditWriter(tmp_path / "streamed.csv")
    for part in parts:
        writer.append(part)
    writer.close()
    do.write_table(pd.concat(parts, ignore_index=True), tmp_path / "concat.csv")
    assert (tmp_path / "streamed.csv").read_bytes() == (tmp_path / "concat.csv").read_bytes()
    other = deliver._AuditWriter(tmp_path / "bad.csv")
    other.append(parts[0])
    with pytest.raises(do.OutputSchemaError, match="dtypes"):
        other.append(parts[0].astype({"staleness_months": "float64"}))
