"""Compose the October delivery for both systems and all three horizons (CP3).

Inputs: a successful prepared snapshot (manifest + per-system feature CSVs), the
accepted September input panels (history/fixed reuse), the six accepted packages,
the population references and native geometries. Output layout (design section 8):

    {fewsnet,ipcch}/{polygons.geojson,country_population_reference.csv}
    scopes/{0m,6m,12m}/{fewsnet,ipcch}/<five September tables>
    inputs/   frozen O scoring inputs (+ FEWS extended/normalised panels)
    reports/  feature_fill_audit.csv, diagnostic_availability.csv, assembly.json

No training; ACLED/WFP refreshes use the CP1 converter outputs when provided.
"""

from __future__ import annotations

import io
import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from cloud.batch.remote_sources import SYSTEM_FAMILIES
from cloud.common.object_refs import sha256_file
from cloud.orchestrator import delivery_inputs as di
from cloud.orchestrator import delivery_outputs as do
from cloud.orchestrator import delivery_scoring as ds
from cloud.orchestrator.causal_fill import AUDIT_COLUMNS, bind_model_features
from model_pipeline.run_operational_launch_inference import add_calendar_months

HORIZONS = ds.HORIZONS
FEWSNET_LABEL_SOURCES = ("fews_ipc", "fews_ipc_crisis", "fews_ha")  # label family: observed only, never filled


def file_ref(path: Path) -> dict:
    """Immutable local ref; streamed hash (never a second full copy in memory)."""
    return {"uri": Path(path).resolve().as_uri(), "generation": "1", "sha256": sha256_file(path)}


def load_prepared_features(manifest: Mapping, reader) -> dict[str, dict[str, pd.DataFrame]]:
    """Per system, per family: prepared feature CSVs read at their pinned generation."""
    from cloud.orchestrator.prepare import read_pinned

    features = {system: {} for system in SYSTEM_FAMILIES}
    for family, entry in manifest["families"].items():
        for system, ref in entry.get("outputs", {}).items():
            features[system][family] = pd.read_csv(io.BytesIO(read_pinned(reader, ref)),
                                                   dtype={"admin_code": str, "month": str})
    return features


def request_diagnostics(request: Mapping, system: str, reader) -> dict[int, dict[str, dict]]:
    """Per-horizon, per-family declarations for ``deliver`` from a structurally valid request.

    Available evidence is read at its pinned generation and must match its sha256
    (``read_pinned``); unavailable entries keep their declared reason.
    """
    from cloud.orchestrator.prepare import read_pinned

    if request.get("validation_level") != "structural":
        raise ValueError("request must pass structural validation first")
    out: dict[int, dict[str, dict]] = {}
    for entry in request["diagnostics"]:
        if entry["system"] != system:
            continue
        if entry["status"] == "available":
            item = {"status": "available", "ref": dict(entry["evidence"]),
                    "evidence_model_package_id": entry["evidence_model_package_id"],
                    "evidence_horizon_months": entry["evidence_horizon_months"],
                    "evidence_bytes": read_pinned(reader, entry["evidence"])}
        else:
            item = {"status": "unavailable", "reason": entry["reason"]}
        out.setdefault(entry["horizon_months"], {})[entry["family"]] = item
    return out


def _label_audit(filled: pd.DataFrame, *, origin: str, source_ref: Mapping[str, str]) -> pd.DataFrame:
    """Observed-only rows for FEWS truth-label sources: labels are never filled."""
    window = di.month_range(str(pd.Period(origin, "M") - di.FEWSNET_FILL_WINDOW_MONTHS), origin)
    rows = filled.loc[filled[di.MONTH].isin(window), [di.KEY, di.MONTH, *FEWSNET_LABEL_SOURCES]]
    parts = []
    for source in FEWSNET_LABEL_SOURCES:
        observed = pd.to_numeric(rows[source], errors="coerce").notna()
        parts.append(pd.DataFrame({
            "system": "fewsnet", "horizon_months": pd.NA, "model_package_id": pd.NA,
            "polygon_id": rows[di.KEY].to_numpy(), "model_feature": pd.NA, "feature_month": rows[di.MONTH].to_numpy(),
            "source_feature": source, "dependency_month": rows[di.MONTH].to_numpy(),
            "source_ref": source_ref["uri"] + "#" + source_ref["generation"], "source_sha256": source_ref["sha256"],
            "observation_month": rows[di.MONTH].where(observed).to_numpy(),
            "staleness_months": pd.array([0 if flag else pd.NA for flag in observed], dtype="Int64"),
            "fill_method": ["observed" if flag else "no_eligible_history" for flag in observed],
            "derived_from_filled": (~observed).to_numpy(), "feature_value_method": pd.NA, "imputation_rule": pd.NA}))
    return pd.concat(parts, ignore_index=True)[AUDIT_COLUMNS]


def deliver(*, origin: str, out: Path, prepared_families: Mapping, prepared_features: Mapping,
            ipcch_panel: Path, ipcch_template: Path, ipcch_package_root: Path,
            fewsnet_raw: Path, fewsnet_packages: Mapping[int, Path], census: Mapping[str, Path],
            geometry: Mapping[str, Path], wfp=None, acled=None, system: str,
            diagnostics: Mapping[int, Mapping] | None = None, fewsnet_checkpoint: Path | None = None) -> dict:
    """Build one system's delivery (bounded memory: run systems one at a time, then ``finalize``).

    ``diagnostics[horizon][family]`` is this system's per-family declaration, normally from
    ``request_diagnostics`` (pinned bytes under ``evidence_bytes``). Absent -> explicit
    unavailable/missing_evidence.
    """
    out = Path(out)
    (out / "inputs").mkdir(parents=True, exist_ok=True)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    report = {"origin_month": origin, "system": system, "targets": {h: add_calendar_months(origin, h) for h in HORIZONS}}
    audits, availability = _AuditWriter(out / f"reports/{system}_feature_fill_audit.csv"), []
    if system == "ipcch":
        results = _ipcch(out, report, origin=origin, prepared_families=prepared_families,
                         prepared_features=prepared_features, panel_path=ipcch_panel, template_path=ipcch_template,
                         package_root=ipcch_package_root, census_path=census["ipcch"], wfp=wfp, acled=acled)
    else:
        results = _fewsnet(out, report, origin=origin, prepared_families=prepared_families,
                           prepared_features=prepared_features, raw_path=fewsnet_raw, packages=fewsnet_packages,
                           census_path=census["fewsnet"], wfp=wfp, acled=acled, checkpoint=fewsnet_checkpoint)
    _write_scopes(out, system, origin, results, audits, availability, report, diagnostics or {})
    (out / f"reports/{system}_diagnostic_declarations.json").write_text(
        json.dumps(report.get("diagnostic_declarations", {}), indent=2, sort_keys=True, default=str) + "\n")
    (out / system).mkdir(exist_ok=True)
    shutil.copyfile(census[system], out / system / "country_population_reference.csv")
    shutil.copyfile(geometry[system], out / system / "polygons.geojson")
    audits.close()
    do.write_table(pd.concat(availability, ignore_index=True), out / f"reports/{system}_diagnostic_availability.csv")
    (out / f"reports/{system}_assembly.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    return report


class _AuditWriter:
    """Create-only CSV written one horizon at a time (never all horizons in memory).

    Every part must have the first part's columns and dtypes, so the bytes equal a single
    ``write_table(pd.concat(parts))``.
    """

    def __init__(self, path: Path):
        self.path, self.handle, self.dtypes = Path(path), None, None

    def append(self, frame: pd.DataFrame) -> None:
        if self.handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = self.path.open("x", encoding="utf-8", newline="")
            self.dtypes = frame.dtypes
            frame.to_csv(self.handle, index=False, lineterminator="\n")
            return
        if not frame.dtypes.equals(self.dtypes):
            raise do.OutputSchemaError(f"{self.path.name}: audit parts differ in columns/dtypes")
        frame.to_csv(self.handle, index=False, header=False, lineterminator="\n")

    def close(self) -> None:
        if self.handle is None:
            raise do.OutputSchemaError(f"{self.path.name}: no audit rows were produced")
        self.handle.close()


def finalize(out: Path) -> None:
    """Stream-concatenate per-system sidecars into the design's single report files.

    Byte-level line streaming after an exact header check (no DataFrame load, so
    multi-million-row audits are never duplicated in memory; blank encodings preserved).
    """
    out = Path(out)
    for name in ("feature_fill_audit", "diagnostic_availability"):
        parts = [out / f"reports/{system}_{name}.csv" for system in ("fewsnet", "ipcch")]
        headers = []
        for part in parts:
            with part.open("rb") as handle:
                headers.append(handle.readline())
        if len(set(headers)) != 1:
            raise do.OutputSchemaError(f"{name}: per-system headers differ")
        with (out / f"reports/{name}.csv").open("xb") as target:
            target.write(headers[0])
            for part in parts:
                with part.open("rb") as handle:
                    handle.readline()
                    shutil.copyfileobj(handle, target, length=1 << 20)


IPCCH_IDENTITY = ("area_id", "admin_code", "year", "month", "lat", "lon", "ISO3", "country", "country_en")


def _ipcch(out, report, *, origin, prepared_families, prepared_features, panel_path, template_path, package_root,
           census_path, wfp, acled):

    # O rows from each area's own past, then three scopes with saved medians. Only identity
    # and contract source columns are read; assembly runs per sorted-area group (bounded
    # memory, byte-identical to the whole-panel path: tests/cloud/test_ipcch_chunked.py).
    import tempfile

    contract = pd.read_csv(Path(package_root) / "scope_0m/feature_contract.csv")
    header = pd.read_csv(panel_path, nrows=0).columns
    wanted = set(IPCCH_IDENTITY) | set(contract["source_column"])
    template = pd.read_csv(template_path, low_memory=False, dtype={"admin_code": str, "area_id": str})
    with tempfile.TemporaryDirectory(prefix="ipcch-chunks-") as work:
        rows, ipcch_base_audit, report["ipcch_assembly"], report["ipcch_chunking"] = di.ipcch_assemble_chunked(
            panel_path, template, origin=origin, feature_columns=list(contract["source_column"]),
            usecols=[column for column in header if column in wanted], prepared_families=prepared_families,
            prepared_features=prepared_features.get("ipcch", {}), base_path=out / "inputs/ipcch_base_series.csv",
            make_ref=file_ref, work_dir=Path(work) / "spill", wfp=wfp, acled=acled)
    rows_path = out / "inputs/ipcch_origin_rows.csv"
    rows.to_csv(rows_path, index=False, lineterminator="\n")
    scores = ds.score_ipcch(rows, package_root, origin=origin, source_input="inputs/ipcch_origin_rows.csv")
    area_lookup = rows[["area_id", "country", "country_en"]]
    census = pd.read_csv(census_path, dtype=str, keep_default_na=False).replace({"": pd.NA})
    iso_by_area = area_lookup.merge(census[["country", "ISO3"]], on="country", how="left").set_index("area_id")["ISO3"]
    return {"scores": scores, "base_audit": ipcch_base_audit, "census": census, "lookup": area_lookup,
            "iso_by_polygon": iso_by_area, "raw_columns": None, "validation_periods": {},
            "training_cutoff": do.ipcch_training_cutoff_month(package_root)}


FEWSNET_CHECKPOINT_FILES = ("inputs/fewsnet_base_panel.csv", "inputs/fewsnet_extra_observations.csv",
                            "inputs/fewsnet_extended_raw.csv", "inputs/fewsnet_normalized_panel.csv",
                            "reports/fewsnet_normalization_audit.json")


class _HashWriter:
    """Text sink that only hashes (verifies a regenerated CSV without writing it)."""

    def __init__(self):
        import hashlib

        self.digest = hashlib.sha256()

    def write(self, text):
        self.digest.update(text.encode("utf-8"))
        return len(text)


def _verified_checkpoint(checkpoint: Path, out: Path) -> dict:
    """Hash-check a previous run's FEWSNET assembly/normalisation outputs and copy them into ``out``."""
    from fewsnet_partitioned_rf_pipeline.core.normalization import NORMALIZATION_VERSION

    checkpoint = Path(checkpoint)
    if checkpoint.resolve() == Path(out).resolve():
        raise ValueError("resume writes a new output directory; the checkpoint is read-only")
    refs = {name: file_ref(checkpoint / name) for name in FEWSNET_CHECKPOINT_FILES}
    sources = json.loads((checkpoint / "inputs/fewsnet_fill_sources.json").read_text())
    audit = json.loads((checkpoint / "reports/fewsnet_normalization_audit.json").read_text())
    checks = {
        "fill_sources.panel_rows": sources["panel_rows"]["sha256"] == refs["inputs/fewsnet_base_panel.csv"]["sha256"],
        "fill_sources.extra_observations":
            sources["extra_observations"]["sha256"] == refs["inputs/fewsnet_extra_observations.csv"]["sha256"],
        "normalization.source": audit["source_panel"]["sha256"] == refs["inputs/fewsnet_extended_raw.csv"]["sha256"],
        "normalization.output": audit["output_panel"]["sha256"] == refs["inputs/fewsnet_normalized_panel.csv"]["sha256"],
        "normalization.version": audit["normalization_version"] == NORMALIZATION_VERSION,
    }
    if not all(checks.values()):
        raise ValueError(f"FEWSNET checkpoint is not internally consistent: {checks}")
    for name in FEWSNET_CHECKPOINT_FILES:
        target = Path(out) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with (checkpoint / name).open("rb") as source, target.open("xb") as handle:
            shutil.copyfileobj(source, handle, length=1 << 20)
        if sha256_file(target) != refs[name]["sha256"]:
            raise ValueError(f"checkpoint copy changed: {name}")
    return {"checkpoint_files": refs, "checks": checks}


def _fewsnet(out, report, *, origin, prepared_families, prepared_features, raw_path, packages, census_path, wfp, acled,
             checkpoint=None):
    # Extend raw panel to O, fill base window, existing normalisation, sequential scoring.
    base_path = out / "inputs/fewsnet_base_panel.csv"
    extra_path = out / "inputs/fewsnet_extra_observations.csv"
    extended = out / "inputs/fewsnet_extended_raw.csv"
    normalized_path = out / "inputs/fewsnet_normalized_panel.csv"
    if checkpoint is None:
        raw = pd.read_csv(raw_path, low_memory=False)
        raw_columns = list(raw.columns)
        fews_base, report["fewsnet_assembly"], extra = di.fewsnet_base_panel(
            raw, origin=origin, prepared_families=prepared_families,
            prepared_features=prepared_features.get("fewsnet", {}), wfp=wfp, acled=acled)
        del raw
        fews_base.to_csv(base_path, index=False, lineterminator="\n")
        # Older provider observations are carry-forward sources outside the panel rows; the
        # audit binds a manifest naming both actual observation sources.
        extra.to_csv(extra_path, index=False, lineterminator="\n")
    else:  # resume: same base rows, re-derived fill audit must regenerate the checkpoint's extended raw
        report["fewsnet_resumed_from"] = _verified_checkpoint(checkpoint, out)
        raw_columns = list(pd.read_csv(raw_path, nrows=0).columns)
        keys = {di.KEY: str, di.MONTH: str}
        fews_base = pd.read_csv(base_path, low_memory=False, float_precision="round_trip", dtype=keys)
        extra = pd.read_csv(extra_path, low_memory=False, float_precision="round_trip", dtype=keys)
    sources_path = out / "inputs/fewsnet_fill_sources.json"
    sources_path.write_text(json.dumps({"panel_rows": file_ref(base_path), "extra_observations": file_ref(extra_path),
                                        "note": "extra observations feed carry-forward only, not normalisation rows"},
                                       indent=2, sort_keys=True) + "\n")
    fill_ref = file_ref(sources_path)
    filled, fews_base_audit = di.fewsnet_fill_window(fews_base, origin=origin, source_ref=fill_ref,
                                                     extra_observations=extra)
    label_audit = _label_audit(filled, origin=origin, source_ref=file_ref(base_path))
    del fews_base
    if checkpoint is None:
        filled[raw_columns].to_csv(extended, index=False, lineterminator="\n")
    else:
        sink = _HashWriter()
        filled[raw_columns].to_csv(sink, index=False, lineterminator="\n")
        if sink.digest.hexdigest() != report["fewsnet_resumed_from"]["checkpoint_files"][
                "inputs/fewsnet_extended_raw.csv"]["sha256"]:
            raise ValueError("re-derived FEWSNET fill does not reproduce the checkpoint extended raw panel")
        report["fewsnet_resumed_from"]["checks"]["fill_regenerates_extended_raw"] = True
    del filled
    from fewsnet_partitioned_rf_pipeline.core.normalization import normalize_panel

    if checkpoint is None:
        normalization = normalize_panel(extended, normalized_path, out / "reports/fewsnet_normalization_audit.json")
        report["fewsnet_normalization"] = {"rows": normalization.normalized_row_count,
                                          "latest_feature_month": normalization.latest_feature_month,
                                          "output_sha256": normalization.output_sha256}
    else:
        audit = json.loads((out / "reports/fewsnet_normalization_audit.json").read_text())
        report["fewsnet_normalization"] = {"rows": audit["output_panel"]["row_count"],
                                          "latest_feature_month": audit["latest_feature_month"],
                                          "output_sha256": audit["output_panel"]["sha256"]}
    # Stage3 on the O-12..O window of the full normalised panel; identity/population/universe
    # from a thin full-history read (supervisor April parity: fews_window_replay).
    # Identity/population come from the pre-fill base rows: observed population keeps its real month.
    identity_source, window = ds.load_fewsnet_scoring_inputs(normalized_path, origin, identity_path=base_path)
    report["fewsnet_scoring_window"] = {"months": list(ds.fewsnet_window(origin)), "window_rows": len(window),
                                        "full_history_rows": len(identity_source),
                                        "identity_population_source": "inputs/fewsnet_base_panel.csv (pre-fill)"}
    scores = ds.score_fewsnet(window, packages, identity_panel=identity_source, origin=origin,
                              source_input="inputs/fewsnet_normalized_panel.csv",
                              artifact_paths={h: f"fewsnet/model_package/{h}m" for h in HORIZONS})
    del window, identity_source
    census = pd.read_csv(census_path, dtype=str, keep_default_na=False).replace({"": pd.NA})
    report["zscore_dependency_disclosure"] = ds.FEWSNET_ZSCORE_DISCLOSURE
    return {"scores": scores, "base_audit": pd.concat([fews_base_audit, label_audit], ignore_index=True),
            "census": census, "lookup": None, "iso_by_polygon": pd.Series(dtype=str), "raw_columns": raw_columns,
            "validation_periods": {h: do.fewsnet_validation_period(packages[h]) for h in HORIZONS}}


def freeze_diagnostic_evidence(out: Path, system: str, horizon: int, declarations: Mapping, diag: Mapping) -> dict:
    """Write the exact evidence bytes used (create-only) for offline replay through the same
    path; returns the declarations record saved in ``reports/{system}_diagnostic_declarations.json``."""
    frozen_paths = {}
    for family, data in diag["frozen_evidence"].items():
        path = Path(out) / f"inputs/evidence/{system}_{horizon}m_{family}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
        frozen_paths[family] = path.relative_to(out).as_posix()
    return {family: {**entry, "frozen_path": frozen_paths.get(family),
                     "evidence_identity": diag["evidence_identity"].get(family)}
            for family, entry in declarations.items()}


def _write_scopes(out, system, origin, results, audits, availability, report, diagnostics):
    """Per-scope tables, audit binding to the actual saved imputers and availability sidecar."""
    for horizon in HORIZONS:
        target = add_calendar_months(origin, horizon)
        scope = out / f"scopes/{horizon}m"
        result = results["scores"][horizon]
        predictions = result["predictions"]
        base_audit, lookup = results["base_audit"], results["lookup"]
        if system == "fewsnet":
            deps, unaudited = ds.fewsnet_dependencies(result["final_missing"].columns, results["raw_columns"])
            package_path = f"fewsnet/model_package/{horizon}m"
        else:
            deps, unaudited = result["dependencies"], []
            package_path = f"ipcch/model_package/scope_{horizon}m"
        bound = bind_model_features(base_audit, deps, feature_month=origin, horizon_months=horizon,
                                    model_package_id=result["package_id"] + ("" if system == "fewsnet" else f"/scope_{horizon}m"),
                                    final_missing=result["final_missing"][list(deps)],
                                    imputation_rules=result["rules"])
        audits.append(bound)
        del bound
        report.setdefault("unaudited_identity_calendar_features", {})[system] = unaudited
        mapping = do.polygon_mapping(system, predictions, origin=origin, target=target, horizon=horizon,
                                     package_path=package_path)
        package_id = result["package_id"] + ("" if system == "fewsnet" else f"/scope_{horizon}m")
        declared = diagnostics.get(horizon) or {}
        declarations = do.normalise_declarations(system, horizon, {
            family: {k: v for k, v in entry.items() if k != "evidence_bytes"} for family, entry in declared.items()})
        diag = do.scope_diagnostics(system, horizon, predictions, declarations=declarations,
                                    evidence_bytes=lambda family: declared[family]["evidence_bytes"],
                                    package_id=package_id, polygons=mapping["polygon_id"], census=results["census"],
                                    area_lookup=lookup, iso_by_polygon=results["iso_by_polygon"], origin=origin,
                                    accepted_period=results["validation_periods"].get(horizon),
                                    training_cutoff=results.get("training_cutoff"))
        country, confidence, polygon_diag = diag["country"], diag["confidence"], diag["polygon_table"]
        availability.append(diag["availability"])
        report.setdefault("diagnostic_declarations", {})[f"{horizon}m"] = freeze_diagnostic_evidence(
            out, system, horizon, declarations, diag)
        name = diag["polygon_name"]
        if system == "fewsnet":  # frozen O scoring inputs for portable rescoring (no 775 MB panel needed)
            result["inference_frame"].to_csv(out / f"inputs/fewsnet_scope_{horizon}m_inference.csv", index=False,
                                             lineterminator="\n")
            if horizon == HORIZONS[0]:
                result["identity"].to_csv(out / "inputs/fewsnet_identity_population.csv", index=False,
                                          lineterminator="\n")
        ordered = predictions[list(do.SEPTEMBER_HEADERS[system]["polygon_predictions"])]
        do.write_table(ordered, scope / system / "polygon_predictions.csv", system=system, name="polygon_predictions")
        do.write_table(country, scope / system / "country_predictions.csv", system=system, name="country_predictions")
        do.write_table(mapping, scope / system / "polygon_model_mapping.csv", system=system, name="polygon_model_mapping")
        do.write_table(polygon_diag, scope / system / f"{name}.csv", system=system, name=name)
        do.write_table(confidence, scope / system / "country_confidence.csv", system=system, name="country_confidence")
