"""Portable delivery bundle and relocated rescore/re-export (design section 8).

The archive carries what scoring needs and nothing more: runtime code, the six
accepted packages, pinned requirements, frozen O scoring inputs (FEWSNET Stage3
frames per horizon + identity/population, IPCCH O rows), shared geometry/population
references, scope tables and reports. Full raw/normalised histories stay outside the
archive but are listed with their hashes in the full inventory (``manifest.json``).

Relocated replay (no repository checkout, no cloud credentials):

    cd <extracted> && PYTHONPATH=runtime python -m cloud.orchestrator.delivery_bundle rescore --root . --output rescored
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (0, 6, 12)
SYSTEMS = ("fewsnet", "ipcch")
RUNTIME_PACKAGES = ("cloud", "fewsnet_partitioned_rf_pipeline", "model_pipeline", "tools")
ARCHIVE = "webapp_model_bundle.tar.gz"
AVAILABILITY = "reports/diagnostic_availability.csv"
# Portable scoring inputs by role; every other inputs/ file and all sources/history are
# inventoried with their hashes but kept out of the portable archive.
PORTABLE_INPUTS = re.compile(r"^inputs/(fewsnet_scope_(0|6|12)m_inference\.csv|fewsnet_identity_population\.csv|"
                             r"ipcch_origin_rows\.csv|evidence/.+)$")
SCOPE_TABLES = {"fewsnet": ("polygon_predictions", "country_predictions", "polygon_model_mapping",
                            "polygon_confidence", "country_confidence"),
                "ipcch": ("polygon_predictions", "country_predictions", "polygon_model_mapping",
                          "polygon_training_errors", "country_confidence")}
# Anchored continuous-field contract; IDs, dates, periods, provenance and discrete fields compare exactly.
CONTINUOUS = re.compile(r"^(lat|lon|population|population_estimate|referenced_population|probability_crisis|threshold|"
                        r"area_classification_threshold|country_outcome_crisis_threshold|area_population_weight_sum|"
                        r"phase[2-5]_worse_score|.+_area_dispersion|.+_error_rate|country_error_.+_sum|"
                        r"country_error_known_population_coverage|country_maximum_phase_error_probability_.+)$")


def is_portable(relative: str) -> bool:
    if relative.startswith(("inputs/", "sources/", "history/")):
        return bool(PORTABLE_INPUTS.match(relative))
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def install_runtime_and_models(root: Path, *, repo: Path, fewsnet_packages: dict, ipcch_package_root: Path,
                               lock_file: Path) -> None:
    root = Path(root)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for package in RUNTIME_PACKAGES:
        shutil.copytree(Path(repo) / package, root / "runtime" / package, ignore=ignore)
    sources = {f"fewsnet/model_package/{horizon}m": Path(path) for horizon, path in fewsnet_packages.items()}
    sources["ipcch/model_package"] = Path(ipcch_package_root)
    for target, source in sources.items():
        shutil.copytree(source, root / target, ignore=ignore)
    shutil.copyfile(lock_file, root / "requirements.lock.txt")
    # Exact inventory of each accepted package directory as scored (validated before packaging).
    inventory = {target: _directory_inventory(source) for target, source in sources.items()}
    (root / "model_inventory.json").write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _directory_inventory(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): _sha256(path) for path in sorted(Path(directory).rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}


IPCCH_SCOPE_FILES = ("feature_columns.json", "feature_contract.csv", "model_metadata.json", "phase2_worse_model.json",
                     "phase3_worse_model.json", "phase4_worse_model.json", "phase5_worse_model.json")


def write_bundle_docs(root: Path, *, origin: str, prepare_id: str) -> None:
    """README, pip requirements and bundle_manifest.json (emitted before the inventory)."""
    root = Path(root)
    shutil.copyfile(root / "requirements.lock.txt", root / "requirements.txt")
    (root / "README.md").write_text(
        f"# FEWSNET + IPCCH delivery, origin {origin}\n\n"
        "Horizon tables are under `scopes/{0m,6m,12m}/{fewsnet,ipcch}/`; geometry and population references are\n"
        "shared per system. Diagnostics without accepted evidence are blank; reasons are in\n"
        "`reports/diagnostic_availability.csv`. Fill provenance is in `reports/feature_fill_audit.csv`.\n\n"
        "Offline rescore/re-export (Python 3.12.3, no repository checkout or cloud credentials):\n\n"
        "    python3.12 -m venv .venv && .venv/bin/pip install --no-deps -r requirements.txt\n"
        "    PYTHONPATH=runtime .venv/bin/python -m cloud.orchestrator.delivery_bundle rescore --root . --output rescored\n",
        encoding="utf-8")
    manifest = {"schema_version": "fewsnet-ipcch-bundle-v1", "origin_month": origin, "prepare_id": prepare_id,
                "systems": list(SYSTEMS), "horizons_months": list(HORIZONS), "scope_tables": SCOPE_TABLES,
                "frozen_scoring_inputs": PORTABLE_INPUTS.pattern}
    (root / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


ROOT_ONLY = ("manifest.json", ARCHIVE)  # excluded from the inventory only at the delivery root


def _inventoried(root: Path) -> list[Path]:
    return sorted(path for path in Path(root).rglob("*")
                  if path.is_file() and path.relative_to(root).as_posix() not in ROOT_ONLY)


def validate_delivery(root: Path) -> dict:
    """Pre-package structural validation of the delivery root (recorded in the root manifest).

    Exact 30-table scope inventory with frozen September headers, equal per-system row counts
    across horizons and polygon/country tables, shared references, sidecar reports and frozen
    scoring inputs. Relocated replay is separate, later evidence.
    """
    from cloud.orchestrator import delivery_outputs as do

    root = Path(root)
    checks, failures = {}, []
    expected = {f"scopes/{h}m/{system}/{name}.csv" for h in HORIZONS for system, names in SCOPE_TABLES.items()
                for name in names}
    found = {path.relative_to(root).as_posix() for path in root.glob("scopes/*/*/*.csv")}
    checks["scope_inventory_exact"] = found == expected
    rows = {}
    for relative in sorted(expected & found):
        _, horizon, system, name = relative.split("/")
        with (root / relative).open(encoding="utf-8", newline="") as handle:
            header = pd.read_csv(handle, nrows=0).columns.tolist()
        if header != list(do.SEPTEMBER_HEADERS[system][name.removesuffix(".csv")]):
            failures.append(f"header:{relative}")
        rows[relative] = sum(1 for _ in pd.read_csv(root / relative, dtype=str, usecols=[header[0]]).itertuples())
    checks["frozen_headers"] = not [f for f in failures if f.startswith("header:")]
    for system, names in SCOPE_TABLES.items():
        polygon = {rows.get(f"scopes/{h}m/{system}/{n}.csv") for h in HORIZONS for n in names if "country" not in n}
        country = {rows.get(f"scopes/{h}m/{system}/{n}.csv") for h in HORIZONS for n in names if "country" in n}
        checks[f"{system}_row_counts_consistent"] = len(polygon) == 1 and len(country) == 1 and None not in polygon | country
    shared = [f"{system}/{name}" for system in SYSTEMS for name in ("polygons.geojson", "country_population_reference.csv")]
    checks["shared_references"] = all((root / relative).is_file() for relative in shared)
    reports = ["reports/diagnostic_availability.csv", "reports/feature_fill_audit.csv", "reports/delivery.json",
               *[f"reports/{system}_diagnostic_declarations.json" for system in SYSTEMS]]
    checks["reports"] = all((root / relative).is_file() for relative in reports)
    frozen = ["inputs/fewsnet_identity_population.csv", "inputs/ipcch_origin_rows.csv",
              *[f"inputs/fewsnet_scope_{h}m_inference.csv" for h in HORIZONS]]
    checks["frozen_scoring_inputs"] = all((root / relative).is_file() for relative in frozen)
    groups = (("content", _content_checks), ("row_identity", _identity_checks),
              ("country_consistency", _country_consistency_checks), ("availability", _availability_coverage_checks),
              ("diagnostics_regenerated", _diagnostics_regeneration_checks),
              ("portable_members", _portable_member_checks))
    for name, check in groups:  # independent groups: one exception never hides another group's result
        try:
            found = check(root)
        except Exception as exc:  # recorded as a failed check; build_archive refuses
            found = {name: False}
            failures.append(f"{name}:{type(exc).__name__}: {exc}")
        for key, value in found.items():
            checks[key] = bool(value)
            if not value:
                failures.append(f"check:{key}")
    return {"stage": "pre_package", "status": "passed" if all(checks.values()) else "failed", "checks": checks,
            "failures": failures, "scope_row_counts": rows}


def _keys(path: Path, column: str) -> pd.Series:
    return pd.read_csv(path, dtype=str, keep_default_na=False, usecols=[column])[column]


def _content_checks(root: Path) -> dict[str, bool]:
    """Native keys against the frozen identity rosters, country keys against the pinned references and
    required prediction values via the existing validators. Allowed blanks (missing FEWSNET
    population, unsupported diagnostics) are not touched."""
    from cloud.orchestrator import delivery_outputs as do
    from fewsnet_partitioned_rf_pipeline.local.outputs import _read_local_prediction_csv, validate_local_prediction_frame
    from model_pipeline.run_operational_launch_inference import add_calendar_months

    origin = json.loads((root / "reports/delivery.json").read_text())["origin_month"]
    rosters = {"fewsnet": _keys(root / "inputs/fewsnet_identity_population.csv", "admin_code"),
               "ipcch": _keys(root / "inputs/ipcch_origin_rows.csv", "area_id")}
    checks = {}
    for system in SYSTEMS:
        roster = rosters[system]
        census = set(_keys(root / f"{system}/country_population_reference.csv", "ISO3"))
        checks[f"{system}_roster_nonempty_unique"] = len(roster) > 0 and not roster.duplicated().any()
        polygon_name = "polygon_confidence" if system == "fewsnet" else "polygon_training_errors"
        for horizon in HORIZONS:
            scope = root / f"scopes/{horizon}m/{system}"
            target = add_calendar_months(origin, horizon)
            key = "admin_code" if system == "fewsnet" else "polygon_id"
            same = [set(_keys(scope / "polygon_predictions.csv", key)), set(_keys(scope / "polygon_model_mapping.csv", "polygon_id")),
                    set(_keys(scope / f"{polygon_name}.csv", "polygon_id"))]
            unique = all(not _keys(scope / f"{name}.csv", column).duplicated().any() for name, column in (
                ("polygon_predictions", key), ("polygon_model_mapping", "polygon_id"), (polygon_name, "polygon_id")))
            checks[f"{system}_{horizon}m_polygon_keys"] = unique and all(keys == set(roster) for keys in same)
            countries = [_keys(scope / name, "ISO3") for name in ("country_predictions.csv", "country_confidence.csv")]
            expected = census if system == "fewsnet" else set(countries[0])
            checks[f"{system}_{horizon}m_country_keys"] = (
                len(countries[0]) > 0 and all(not c.duplicated().any() for c in countries)
                and set(countries[0]) == set(countries[1]) == expected and expected <= census)
            if system == "fewsnet":
                frame = _read_local_prediction_csv(scope / "polygon_predictions.csv")
                validate_local_prediction_frame(frame, expected_admin_codes=roster, feature_month=origin,
                                                target_month=target, horizon_months=horizon,
                                                suite_version=str(frame["suite_version"].iloc[0]))
                checks[f"fewsnet_{horizon}m_predictions_valid"] = True
            else:
                frame = pd.read_csv(scope / "polygon_predictions.csv", dtype={"polygon_id": str, "area_id": str})
                do.validate_ipcch_phases(frame)
                scores = frame[[f"{t}_score" for t in do.PHASE_TARGETS]].apply(pd.to_numeric, errors="coerce")
                checks[f"ipcch_{horizon}m_predictions_valid"] = bool(
                    np.isfinite(scores.to_numpy(dtype=float)).all()
                    and frame["feature_period"].astype(str).eq(origin).all()
                    and frame["target_period"].astype(str).eq(target).all()
                    and pd.to_numeric(frame["scope_months"]).eq(horizon).all())
    return checks


def _text(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _identity_checks(root: Path) -> dict[str, bool]:
    """Row-level native identity: every output row carries its own roster identity, not just a roster key."""
    from fewsnet_partitioned_rf_pipeline.local.outputs import _IDENTITY_POPULATION_COLUMNS

    checks = {}
    identity = _text(root / "inputs/fewsnet_identity_population.csv")
    columns = [c for c in _IDENTITY_POPULATION_COLUMNS if c in identity]
    reference = identity[columns].set_index("admin_code").sort_index()
    origin_rows = _text(root / "inputs/ipcch_origin_rows.csv")
    pairs = origin_rows[["area_id", "admin_code"]].set_index("area_id").sort_index()
    for horizon in HORIZONS:
        scope = root / f"scopes/{horizon}m"
        predictions = _text(scope / "fewsnet/polygon_predictions.csv")
        mapping = _text(scope / "fewsnet/polygon_model_mapping.csv")
        checks[f"fewsnet_{horizon}m_row_identity"] = (
            len(columns) == len(_IDENTITY_POPULATION_COLUMNS)
            and predictions[columns].set_index("admin_code").sort_index().equals(reference)
            and mapping["polygon_id"].equals(mapping["admin_code"]) and set(mapping["admin_code"]) == set(reference.index))
        predictions = _text(scope / "ipcch/polygon_predictions.csv")
        mapping = _text(scope / "ipcch/polygon_model_mapping.csv")
        rows_ok = True
        for frame in (predictions, mapping):
            rows_ok &= frame["polygon_id"].equals(frame["area_id"]) and frame[["area_id", "admin_code"]].set_index(
                "area_id").sort_index().equals(pairs)
        checks[f"ipcch_{horizon}m_row_identity"] = bool(rows_ok)
    return checks


# Country fields that depend on historical evidence (blank or evidence-derived); every other
# country field is recomputed from the delivered polygon predictions and must match.
EVIDENCE_COUNTRY_FIELDS = re.compile(r"^country_(error_.+|confidence_flag|confidence_thresholds|maximum_phase_error_"
                                     r"probability_.+|maximum_phase_history_month_count|maximum_phase_uncertainty_.+)$")


def _country_consistency_checks(root: Path) -> dict[str, bool]:
    """Current country predictions/outcomes equal the unchanged aggregation of the delivered polygons
    (missing FEWSNET population handled by the aggregator itself, never filled here)."""
    import io

    from cloud.orchestrator import delivery_outputs as do
    from fewsnet_partitioned_rf_pipeline.local.outputs import _read_local_prediction_csv

    checks = {}
    lookup = pd.read_csv(root / "inputs/ipcch_origin_rows.csv", dtype={"area_id": str, "admin_code": str},
                         usecols=["area_id", "country", "country_en"])
    for system in SYSTEMS:
        census = pd.read_csv(root / f"{system}/country_population_reference.csv", dtype=str,
                             keep_default_na=False).replace({"": pd.NA})
        for horizon in HORIZONS:
            scope = root / f"scopes/{horizon}m/{system}"
            if system == "fewsnet":
                predictions = _read_local_prediction_csv(scope / "polygon_predictions.csv")
            else:
                predictions = pd.read_csv(scope / "polygon_predictions.csv", float_precision="round_trip",
                                          dtype={"polygon_id": str, "area_id": str, "admin_code": str})
            country, confidence = do.country_tables(system, predictions, census=census,
                                                    area_lookup=None if system == "fewsnet" else lookup)
            ok = True
            for name, frame in (("country_predictions", country), ("country_confidence", confidence)):
                delivered = _text(scope / f"{name}.csv")
                recomputed = pd.read_csv(io.StringIO(frame.to_csv(index=False)), dtype=str, keep_default_na=False)
                fields = [c for c in delivered.columns if not EVIDENCE_COUNTRY_FIELDS.match(c)]
                if list(recomputed.columns) != list(delivered.columns):
                    ok = False
                    continue
                same, _, _ = _compare_frames(delivered[fields].sort_values("ISO3").reset_index(drop=True),
                                             recomputed[fields].sort_values("ISO3").reset_index(drop=True))
                ok &= same
            checks[f"{system}_{horizon}m_country_consistent"] = bool(ok)
    return checks


def _availability_coverage_checks(root: Path) -> dict[str, bool]:
    """Exactly one availability row per system/horizon/family/entity, with a valid status and reason."""
    from cloud.orchestrator import delivery_outputs as do
    from cloud.orchestrator.delivery_manifest import UNAVAILABLE_REASONS

    table = _text(root / AVAILABILITY)
    keys = ["model_system", "horizon_months", "diagnostic_family", "level", "entity_id"]
    found = list(map(tuple, table[keys].itertuples(index=False)))
    rosters = {"fewsnet": _keys(root / "inputs/fewsnet_identity_population.csv", "admin_code"),
               "ipcch": _keys(root / "inputs/ipcch_origin_rows.csv", "area_id")}
    expected = set()
    for system in SYSTEMS:
        for horizon in HORIZONS:
            countries = _keys(root / f"scopes/{horizon}m/{system}/country_confidence.csv", "ISO3")
            for family, level in do.DIAGNOSTIC_FAMILIES[system].items():
                for entity in (rosters[system] if level == "polygon" else countries):
                    expected.add((system, str(horizon), family, level, str(entity)))
    status_ok = table["status"].isin(["available", "limited", "unavailable"])
    reason_ok = table["reason"].isin(UNAVAILABLE_REASONS).where(table["status"].ne("available"), table["reason"].eq(""))
    reason_present = table["reason"].ne("") | table["status"].eq("available")
    return {"availability_complete": len(found) > 0 and len(found) == len(set(found)) and set(found) == expected,
            "availability_status_valid": bool(status_ok.all() and reason_ok.all() and reason_present.all())}


def _portable_member_checks(root: Path) -> dict[str, bool]:
    """Mandatory archive members: six packages (their exact inventories), runtime, docs, mapping targets."""
    checks = {}
    recorded = json.loads((root / "model_inventory.json").read_text())
    for horizon in HORIZONS:
        directory = root / f"fewsnet/model_package/{horizon}m"
        manifest = json.loads((directory / "local_model_manifest.json").read_text())
        checksums = json.loads((directory / "checksums.json").read_text())
        actual = _directory_inventory(directory)
        checks[f"fewsnet_{horizon}m_package_exact"] = (
            set(actual) == set(manifest["files"]) == set(recorded[f"fewsnet/model_package/{horizon}m"])
            and all(actual[name] == digest for name, digest in checksums.items())
            and actual == recorded[f"fewsnet/model_package/{horizon}m"])
    ipcch = _directory_inventory(root / "ipcch/model_package")
    required = {"model_package_manifest.json", *[f"scope_{h}m/{name}" for h in HORIZONS for name in IPCCH_SCOPE_FILES]}
    checks["ipcch_package_exact"] = required <= set(ipcch) and ipcch == recorded["ipcch/model_package"]
    checks["runtime_entry"] = all((root / "runtime" / package).is_dir() for package in RUNTIME_PACKAGES) and (
        root / "runtime/cloud/orchestrator/delivery_bundle.py").is_file()
    lock = root / "requirements.lock.txt"
    checks["runtime_dependencies"] = lock.is_file() and lock.stat().st_size > 0 and (
        root / "requirements.txt").read_bytes() == lock.read_bytes()
    checks["docs"] = (root / "README.md").is_file() and (root / "bundle_manifest.json").is_file()
    targets = set()
    for horizon in HORIZONS:
        for system in SYSTEMS:
            targets.update(_keys(root / f"scopes/{horizon}m/{system}/polygon_model_mapping.csv", "model_package"))
    checks["mapping_targets_present"] = bool(targets) and all((root / target).is_dir() for target in targets)
    return checks


def diagnostics_summary(root: Path) -> list[dict]:
    """Counts by system/horizon/family/level/status/reason: a successful delivery never implies diagnostics exist."""
    path = Path(root) / "reports/diagnostic_availability.csv"
    if not path.is_file():
        return []
    keys = ["model_system", "horizon_months", "diagnostic_family", "level", "status", "reason"]
    table = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=keys)
    counts = table.groupby(keys, sort=True).size().reset_index(name="entities")
    return counts.to_dict(orient="records")


def write_inventory(root: Path, *, provenance: dict | None = None) -> dict:
    """Full immutable inventory of the delivery root (relative paths, sha256, size), the
    pre-package validation status and a separate diagnostic availability summary."""
    root = Path(root)
    inventory = {
        "schema_version": "fewsnet-ipcch-delivery-inventory-v1",
        "files": [{"path": path.relative_to(root).as_posix(), "sha256": _sha256(path), "size_bytes": path.stat().st_size,
                   "portable": is_portable(path.relative_to(root).as_posix())} for path in _inventoried(root)],
        "provenance": provenance or {},
        "validation": validate_delivery(root),
        "diagnostics_availability_summary": diagnostics_summary(root),
    }
    with (root / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(inventory, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return inventory


def verify_inventory(root: Path) -> dict:
    """Seal check: every inventoried file (portable or not) still has its hash and nothing was added."""
    root = Path(root)
    inventory = json.loads((root / "manifest.json").read_text())
    listed = {entry["path"]: entry["sha256"] for entry in inventory["files"]}
    present = {path.relative_to(root).as_posix() for path in _inventoried(root)}
    if present != set(listed):
        raise ValueError(f"inventory changed: added {sorted(present - set(listed))[:5]}, "
                         f"removed {sorted(set(listed) - present)[:5]}")
    changed = [relative for relative, digest in listed.items() if _sha256(root / relative) != digest]
    if changed:
        raise ValueError(f"inventoried files changed after sealing: {changed[:5]}")
    return inventory


def build_archive(root: Path) -> Path:
    """Create-only portable archive of the inventoried portable files; refuses an unvalidated or
    changed inventory; member hashes verified."""
    root = Path(root)
    inventory = verify_inventory(root)
    if inventory["validation"]["status"] != "passed":
        raise ValueError(f"pre-package validation failed: {inventory['validation']['checks']}")
    portable = [entry for entry in inventory["files"] if entry["portable"]]
    archive = root / ARCHIVE
    with tarfile.open(archive, "x:gz") as tar:
        for entry in portable:
            tar.add(root / entry["path"], arcname=entry["path"], recursive=False)
        manifest_info = tarfile.TarInfo("manifest.json")
        data = (root / "manifest.json").read_bytes()
        manifest_info.size = len(data)
        import io
        tar.addfile(manifest_info, io.BytesIO(data))
    expected = {entry["path"]: entry["sha256"] for entry in portable}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "manifest.json":
                continue
            digest = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
            if expected.pop(member.name, None) != digest:
                raise ValueError(f"archive member hash mismatch: {member.name}")
    if expected:
        raise ValueError(f"archive is missing portable members: {sorted(expected)[:5]}")
    return archive


def frozen_declarations(root: Path, system: str, horizon: int):
    """(normalised declarations, evidence_bytes) replaying exactly what delivery froze.

    The declarations file is required: a bundle never silently replays as "unavailable".
    """
    from cloud.orchestrator import delivery_outputs as do

    saved = json.loads((Path(root) / f"reports/{system}_diagnostic_declarations.json").read_text())[f"{horizon}m"]
    declarations = do.normalise_declarations(
        system, horizon, {family: {k: v for k, v in entry.items() if k not in ("frozen_path", "evidence_identity")}
                          for family, entry in saved.items()})

    def evidence_bytes(family):
        return (Path(root) / saved[family]["frozen_path"]).read_bytes()

    return declarations, evidence_bytes


def regenerate_diagnostics(root: Path, system: str, horizon: int, predictions: pd.DataFrame, polygons, *, origin: str,
                           census: pd.DataFrame, lookup, iso: pd.Series) -> dict:
    """One scope's diagnostic tables and availability from the frozen declarations/evidence bytes
    through the same ``scope_diagnostics`` path as delivery (used by rescore and validation)."""
    from cloud.orchestrator import delivery_outputs as do

    root = Path(root)
    declarations, evidence_bytes = frozen_declarations(root, system, horizon)
    if system == "fewsnet":
        package_id = f"{predictions['suite_version'].iloc[0]}/{horizon}m"
        report = root / f"fewsnet/model_package/{horizon}m/training_report.json"
        accepted, cutoff = (do.fewsnet_validation_period(report.parent) if report.is_file() else None), None
    else:
        package_id = f"{predictions['model_package_id'].iloc[0]}/scope_{horizon}m"
        manifest = root / "ipcch/model_package/model_package_manifest.json"
        accepted, cutoff = None, (do.ipcch_training_cutoff_month(manifest.parent) if manifest.is_file() else None)
    return do.scope_diagnostics(system, horizon, predictions, declarations=declarations, evidence_bytes=evidence_bytes,
                                package_id=package_id, polygons=polygons, census=census, area_lookup=lookup,
                                iso_by_polygon=iso, origin=origin, accepted_period=accepted, training_cutoff=cutoff)


def _diagnostics_regeneration_checks(root: Path) -> dict[str, bool]:
    """Delivered diagnostic tables and availability rows equal their regeneration from the frozen
    declarations/evidence and the delivered predictions: no 'available' row without bound evidence,
    no reason that contradicts the (blank or supported) diagnostics."""
    import io

    from fewsnet_partitioned_rf_pipeline.local.outputs import _read_local_prediction_csv

    origin = json.loads((root / "reports/delivery.json").read_text())["origin_month"]
    lookup = pd.read_csv(root / "inputs/ipcch_origin_rows.csv", dtype={"area_id": str, "admin_code": str},
                         usecols=["area_id", "country", "country_en"])
    census = {system: pd.read_csv(root / f"{system}/country_population_reference.csv", dtype=str,
                                  keep_default_na=False).replace({"": pd.NA}) for system in SYSTEMS}
    iso = lookup.merge(census["ipcch"][["country", "ISO3"]], on="country", how="left").set_index("area_id")["ISO3"]
    delivered = _text(root / AVAILABILITY)

    def as_text(frame):
        return pd.read_csv(io.StringIO(frame.to_csv(index=False)), dtype=str, keep_default_na=False)

    checks = {}
    for system in SYSTEMS:
        for horizon in HORIZONS:
            scope = root / f"scopes/{horizon}m/{system}"
            if system == "fewsnet":
                predictions = _read_local_prediction_csv(scope / "polygon_predictions.csv")
            else:
                predictions = pd.read_csv(scope / "polygon_predictions.csv", float_precision="round_trip",
                                          dtype={"polygon_id": str, "area_id": str, "admin_code": str})
            polygons = _keys(scope / "polygon_model_mapping.csv", "polygon_id")
            diag = regenerate_diagnostics(root, system, horizon, predictions, polygons, origin=origin,
                                          census=census[system], lookup=None if system == "fewsnet" else lookup,
                                          iso=iso)
            rows = delivered[(delivered["model_system"] == system) & (delivered["horizon_months"] == str(horizon))]
            regenerated = sorted(map(tuple, as_text(diag["availability"]).itertuples(index=False)))
            same = sorted(map(tuple, rows.itertuples(index=False))) == regenerated and len(regenerated) > 0
            for name, frame in ((diag["polygon_name"], diag["polygon_table"]), ("country_confidence", diag["confidence"])):
                same &= _compare_frames(_text(scope / f"{name}.csv"), as_text(frame))[0]
            checks[f"{system}_{horizon}m_diagnostics_regenerated"] = bool(same)
    return checks


def rescore(root: Path, output: Path) -> dict:
    """Rescore all six packages from frozen inputs and re-export the scope tables (offline)."""
    from cloud.orchestrator import delivery_outputs as do
    from fewsnet_partitioned_rf_pipeline.local.outputs import enrich_local_predictions
    from fewsnet_partitioned_rf_pipeline.local.package import load_local_model_package
    from model_pipeline.ipcch_launch_runtime.adapters import validate_monthly_input
    from model_pipeline.run_operational_launch_inference import add_calendar_months, run_scope

    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    origin = json.loads((root / "reports/delivery.json").read_text())["origin_month"]
    identity = pd.read_csv(root / "inputs/fewsnet_identity_population.csv", dtype={"admin_code": str},
                           float_precision="round_trip")
    rows = pd.read_csv(root / "inputs/ipcch_origin_rows.csv", low_memory=False, float_precision="round_trip",
                       dtype={"admin_code": str, "area_id": str})
    monthly, _ = validate_monthly_input(rows, origin)
    lookup = rows[["area_id", "country", "country_en"]]
    census = {system: pd.read_csv(root / f"{system}/country_population_reference.csv", dtype=str,
                                  keep_default_na=False).replace({"": pd.NA}) for system in SYSTEMS}
    iso = lookup.merge(census["ipcch"][["country", "ISO3"]], on="country", how="left").set_index("area_id")["ISO3"]
    summary, availability = {}, []
    for horizon in HORIZONS:
        target = add_calendar_months(origin, horizon)
        package = load_local_model_package(root / f"fewsnet/model_package/{horizon}m")
        frame = pd.read_csv(root / f"inputs/fewsnet_scope_{horizon}m_inference.csv", dtype={"admin_code": str},
                            float_precision="round_trip", low_memory=False)
        fews = enrich_local_predictions(package.predictor.predict_frame(frame), identity,
                                        model_artifact_path=f"fewsnet/model_package/{horizon}m",
                                        source_input="inputs/fewsnet_normalized_panel.csv")
        ipcch, _ = run_scope(monthly_rows=monthly, model_package_root=root / "ipcch/model_package", feature_month=origin,
                             scope_months=horizon, target_month=target, source_input="inputs/ipcch_origin_rows.csv",
                             include_uncertainty=False)
        ipcch.insert(0, "polygon_id", ipcch["area_id"].astype(str))
        for system, predictions, lookup_frame, package_path in (
                ("fewsnet", fews, None, f"fewsnet/model_package/{horizon}m"),
                ("ipcch", ipcch, lookup, f"ipcch/model_package/scope_{horizon}m")):
            scope = output / f"scopes/{horizon}m/{system}"
            ordered = predictions[list(do.SEPTEMBER_HEADERS[system]["polygon_predictions"])]
            do.write_table(ordered, scope / "polygon_predictions.csv", system=system, name="polygon_predictions")
            mapping = do.polygon_mapping(system, predictions, origin=origin, target=target, horizon=horizon,
                                         package_path=package_path)
            do.write_table(mapping, scope / "polygon_model_mapping.csv", system=system, name="polygon_model_mapping")
            diag = regenerate_diagnostics(root, system, horizon, predictions, mapping["polygon_id"], origin=origin,
                                          census=census[system], lookup=lookup_frame, iso=iso)
            do.write_table(diag["country"], scope / "country_predictions.csv", system=system, name="country_predictions")
            do.write_table(diag["confidence"], scope / "country_confidence.csv", system=system, name="country_confidence")
            do.write_table(diag["polygon_table"], scope / f"{diag['polygon_name']}.csv", system=system,
                           name=diag["polygon_name"])
            availability.append(diag["availability"])
        summary[horizon] = {"fewsnet_rows": len(fews), "ipcch_rows": len(ipcch)}
    do.write_table(pd.concat(availability, ignore_index=True), output / AVAILABILITY)
    return summary


def _compare_frames(a: pd.DataFrame, b: pd.DataFrame, atol: float = 1e-12) -> tuple[bool, float, list[str]]:
    """Text frames: exact text for IDs/discrete fields; ``atol`` (rtol 0) only for named continuous columns."""
    ok, max_diff, bad = list(a.columns) == list(b.columns) and len(a) == len(b), 0.0, []
    if ok:
        for column in a.columns:
            if not CONTINUOUS.search(column):
                if not a[column].equals(b[column]):
                    bad.append(column)  # IDs, dates, periods, provenance, discrete: exact text
                continue
            blank_a, blank_b = a[column].eq(""), b[column].eq("")
            left, right = pd.to_numeric(a[column], errors="coerce"), pd.to_numeric(b[column], errors="coerce")
            parsed = (left.notna() | blank_a) & (right.notna() | blank_b)
            finite = np.isfinite(left.where(~blank_a, 0).to_numpy(float)) & np.isfinite(right.where(~blank_b, 0).to_numpy(float))
            if not blank_a.equals(blank_b) or not parsed.all() or not finite.all():
                bad.append(column)  # malformed, non-finite or blank-mask mismatch
                continue
            both = ~blank_a
            if both.any():
                max_diff = max(max_diff, float(np.max(np.abs(left[both] - right[both]))))
    return ok and not bad and max_diff <= atol, max_diff, bad


def compare_scopes(delivered: Path, rescored: Path, atol: float = 1e-12) -> dict:
    """Exact inventory of all 30 scope tables; exact text for IDs/discrete fields; ``atol``
    (rtol 0) only for named continuous columns. An empty or partial set fails."""
    expected = {f"scopes/{h}m/{system}/{name}.csv" for h in HORIZONS for system, names in SCOPE_TABLES.items()
                for name in names}
    found = {path.relative_to(rescored).as_posix() for path in Path(rescored).glob("scopes/*/*/*.csv")}
    delivered_found = {path.relative_to(delivered).as_posix() for path in Path(delivered).glob("scopes/*/*/*.csv")}
    results = {"_inventory": {"equal": found == expected and delivered_found == expected,
                              "missing": sorted(expected - found), "unexpected": sorted(found - expected),
                              "delivered_missing": sorted(expected - delivered_found),
                              "delivered_unexpected": sorted(delivered_found - expected)}}
    for relative in sorted(expected & found & delivered_found):
        a = pd.read_csv(Path(delivered) / relative, dtype=str, keep_default_na=False)
        b = pd.read_csv(Path(rescored) / relative, dtype=str, keep_default_na=False)
        equal, max_diff, bad = _compare_frames(a, b, atol=atol)
        results[relative] = {"equal": equal, "max_abs_diff": max_diff, "exact_mismatch_columns": bad}
    results[AVAILABILITY] = _compare_availability(Path(delivered) / AVAILABILITY, Path(rescored) / AVAILABILITY)
    return results


def _compare_availability(delivered: Path, rescored: Path) -> dict:
    """Complete entity/family/status/reason/ref coverage, order-independent; empty never passes."""
    if not delivered.is_file() or not rescored.is_file():
        return {"equal": False, "reason": "missing sidecar"}
    tables = [pd.read_csv(path, dtype=str, keep_default_na=False) for path in (delivered, rescored)]
    rows = [sorted(map(tuple, table.itertuples(index=False))) for table in tables]
    return {"equal": list(tables[0].columns) == list(tables[1].columns) and len(rows[0]) > 0 and rows[0] == rows[1],
            "delivered_rows": len(rows[0]), "rescored_rows": len(rows[1])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Portable delivery rescore/re-export.")
    commands = parser.add_subparsers(dest="command", required=True)
    re = commands.add_parser("rescore")
    re.add_argument("--root", required=True)
    re.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    summary = rescore(Path(args.root), Path(args.output))
    comparison = compare_scopes(Path(args.root), Path(args.output))
    passed = len(comparison) == 32 and AVAILABILITY in comparison and all(v["equal"] for v in comparison.values())
    print(json.dumps({"summary": summary, "all_equal": passed, "tables": comparison}, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
