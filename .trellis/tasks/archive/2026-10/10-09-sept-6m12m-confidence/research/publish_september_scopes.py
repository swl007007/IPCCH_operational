"""Step 6: publish the September-origin 6m/12m scopes into ``september_manual/scopes/`` (design section 6).

Source: the validated workdir delivery (~/work/sept-6m12m-20261009/delivery) and run sidecars.
Writes into a staging sibling, verifies every hash against its source (or recorded transform),
then renames the staging directory to ``september_manual/scopes``. Root h5 files and
``september_manual/inventory.json`` are checked before and after and never written.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
SEPT = REPO / "september_manual"
WORK = Path.home() / "work/sept-6m12m-20261009"
OUT = WORK / "delivery"
RUN = WORK / "run"
SYSTEMS = ("fewsnet", "ipcch")
PUBLISHED = (6, 12)
SCOPE_TABLES = {"fewsnet": ("polygon_predictions", "country_predictions", "polygon_model_mapping", "polygon_confidence",
                            "country_confidence"),
                "ipcch": ("polygon_predictions", "country_predictions", "polygon_model_mapping",
                          "polygon_training_errors", "country_confidence")}
REPORTS = ("delivery.json", *[f"{s}_diagnostic_declarations.json" for s in SYSTEMS],
           *[f"{s}_assembly.json" for s in SYSTEMS], "fewsnet_normalization_audit.json")


def sha(path) -> str:
    digest = hashlib.sha256()
    for attempt in range(5):
        try:
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 22), b""):
                    digest.update(block)
            return digest.hexdigest()
        except OSError:
            if attempt == 4:
                raise
            digest = hashlib.sha256()
            time.sleep(2)


def ident(path) -> dict:
    return {"sha256": sha(path), "size": Path(path).stat().st_size}


def root_h5_check() -> dict:
    inventory = json.loads((SEPT / "inventory.json").read_text())["files"]
    mismatches = [rel for rel, entry in inventory.items()
                  if (sha(SEPT / rel), (SEPT / rel).stat().st_size) != (entry["sha256"], entry["size"])]
    return {"files": len(inventory), "mismatches": mismatches, "inventory_sha256": sha(SEPT / "inventory.json"),
            "readme_sha256": sha(SEPT / "README.md")}


def filter_availability(source: Path, target: Path) -> dict:
    """Byte-level line filter: header plus rows whose horizon_months is 6 or 12 (D11)."""
    kept = dropped = 0
    with source.open("rb") as handle, target.open("xb") as out:
        header = handle.readline()
        columns = header.decode().rstrip("\n").split(",")
        if columns[:2] != ["model_system", "horizon_months"]:
            raise SystemExit(f"unexpected availability header {columns}")
        out.write(header)
        for line in handle:
            horizon = line.split(b",", 2)[1]
            if horizon in (b"6", b"12"):
                out.write(line)
                kept += 1
            else:
                if horizon != b"0":
                    raise SystemExit(f"unexpected horizon {horizon!r}")
                dropped += 1
    return {"kept_rows": kept, "dropped_0m_rows": dropped}


def main() -> int:
    target = SEPT / "scopes"
    if target.exists():
        raise SystemExit(f"{target} exists; refusing to overwrite")
    manifest = json.loads((OUT / "manifest.json").read_text())
    if manifest["validation"]["status"] != "passed":
        raise SystemExit("workdir delivery validation did not pass")
    september_run = json.loads((RUN / "september_run.json").read_text())
    if not september_run["g5"]["passed"]:
        raise SystemExit("G5 did not pass")
    before = root_h5_check()
    if before["mismatches"]:
        raise SystemExit(f"september_manual root files differ from inventory before publish: {before['mismatches']}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    staging = SEPT / f".scopes.staging-{stamp}"
    staging.mkdir()
    files, sources = {}, {}

    def copy(source: Path, relative: str, note: str = "copy") -> None:
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as handle, destination.open("xb") as out:
            shutil.copyfileobj(handle, out, length=1 << 22)
        sources[relative] = {"source": str(source.relative_to(WORK)), "transform": note, **ident(source)}

    for horizon in PUBLISHED:
        for system in SYSTEMS:
            for name in SCOPE_TABLES[system]:
                copy(OUT / f"scopes/{horizon}m/{system}/{name}.csv", f"{horizon}m/{system}/{name}.csv")
    for system in SYSTEMS:
        for name in ("country_population_reference.csv", "polygons.geojson"):
            copy(OUT / system / name, f"shared/{system}/{name}")
    for name in REPORTS:
        copy(OUT / "reports" / name, f"reports/{name}")
    copy(RUN / "september_run.json", "reports/september_run.json")
    (staging / "reports").mkdir(exist_ok=True)
    filtered = filter_availability(OUT / "reports/diagnostic_availability.csv",
                                   staging / "reports/diagnostic_availability.csv")
    sources["reports/diagnostic_availability.csv"] = {
        "source": "delivery/reports/diagnostic_availability.csv",
        "transform": "rows with horizon_months in {6, 12} (D11); header and row bytes unchanged", **filtered,
        **ident(OUT / "reports/diagnostic_availability.csv")}
    # Verify staged bytes.
    for path in sorted(p for p in staging.rglob("*") if p.is_file()):
        relative = path.relative_to(staging).as_posix()
        files[relative] = ident(path)
        source = sources[relative]
        if source["transform"] == "copy" and (files[relative]["sha256"], files[relative]["size"]) != (
                source["sha256"], source["size"]):
            raise SystemExit(f"staged copy differs from source: {relative}")
    baseline = json.loads((CP / "bootstrap/baseline.json").read_text())
    workdir_only = {}
    for relative in ("reports/feature_fill_audit.csv", "reports/diagnostic_availability.csv",
                     "reports/fewsnet_feature_fill_audit.csv", "reports/ipcch_feature_fill_audit.csv",
                     *[f"scopes/0m/{s}/{n}.csv" for s in SYSTEMS for n in SCOPE_TABLES[s]],
                     "manifest.json", "webapp_model_bundle.tar.gz"):
        path = OUT / relative
        if path.exists():
            workdir_only[relative] = {**ident(path), "location": str(path)}
    frozen_evidence = {p.relative_to(OUT).as_posix(): ident(p) for p in sorted((OUT / "inputs/evidence").glob("*.csv"))}
    inventory = {
        "schema_version": "september-origin-scopes-v1",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": "September-origin (feature month 2026-09) 6m/12m FEWSNET + IPCCH scope tables with confidence "
                       "diagnostics, scored by the accepted cloud packages through cloud.orchestrator.deliver. "
                       "The h5 delivery in the parent folder is unchanged and has its own inventory.json.",
        "origin_month": september_run["origin_month"],
        "targets": {"6m": "2027-03", "12m": "2027-09"},
        "files": dict(sorted(files.items())),
        "sources": dict(sorted(sources.items())),
        "provenance": {
            "run_id": september_run["run_id"],
            "prepared_snapshot": september_run["prepared_snapshot"],
            "october_request": september_run["october_request"],
            "downloads": september_run["downloads"],
            "source_choices": september_run["source_choices"],
            "baseline_json_sha256": september_run["baseline_id"],
            "request_sha256": september_run["request_sha256"],
            "models": [{k: m[k] for k in ("system", "horizon_months", "package_id", "feature_schema_sha256")}
                       for m in baseline["models"]],
            "evidence": {rel: entry for rel, entry in baseline["files"].items() if rel.startswith("evidence/")},
            "evidence_frozen_in_run": frozen_evidence,
            "workdir_validation": manifest["validation"]["status"],
            "workdir_bundle_inventory_sha256": sha(OUT / "manifest.json"),
            "environment": {"interpreter": september_run["interpreter"], "python": september_run["python"],
                            "requirements_lock_sha256": september_run["requirements_lock_sha256"]},
            "workdir_only_artifacts": workdir_only,
            "unpublished": "0m scope tables and the full feature-fill audit stay in the workdir (D11/D16); "
                           "hashes are recorded above.",
        },
    }
    (staging / "inventory.json").write_text(json.dumps(inventory, indent=1, sort_keys=False) + "\n")
    return finish(staging, target, files, before, filtered)


def rename_with_retry(staging: Path, target: Path) -> int:
    """DrvFS/Dropbox can transiently deny a directory rename while it holds handles."""
    for attempt in range(1, 31):
        try:
            os.rename(staging, target)
            return attempt
        except PermissionError:
            if attempt == 30:
                raise
            time.sleep(10)


def resume(staging: Path) -> int:
    """Re-verify an already staged directory against its own inventory, then rename it into place."""
    target = SEPT / "scopes"
    if target.exists():
        raise SystemExit(f"{target} exists; refusing to overwrite")
    before = root_h5_check()
    if before["mismatches"]:
        raise SystemExit(f"root files differ from inventory: {before['mismatches']}")
    inventory = json.loads((staging / "inventory.json").read_text())
    files = inventory["files"]
    present = {p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()} - {"inventory.json"}
    if present != set(files):
        raise SystemExit("staged membership differs from its inventory")
    for relative, entry in files.items():
        if (sha(staging / relative), (staging / relative).stat().st_size) != (entry["sha256"], entry["size"]):
            raise SystemExit(f"staged file differs from its inventory: {relative}")
        source = inventory["sources"][relative]
        if source["transform"] == "copy":
            if (sha(WORK / source["source"]), entry["size"]) != (source["sha256"], source["size"]) or \
                    entry["sha256"] != source["sha256"]:
                raise SystemExit(f"staged copy differs from workdir source: {relative}")
    filtered = {k: inventory["sources"]["reports/diagnostic_availability.csv"][k] for k in ("kept_rows", "dropped_0m_rows")}
    return finish(staging, target, files, before, filtered)


def finish(staging: Path, target: Path, files: dict, before: dict, filtered: dict) -> int:
    attempts = rename_with_retry(staging, target)
    # Post-rename verification.
    for relative, entry in files.items():
        if (sha(target / relative), (target / relative).stat().st_size) != (entry["sha256"], entry["size"]):
            raise SystemExit(f"published file differs after rename: {relative}")
    after = root_h5_check()
    result = {"published": str(target.relative_to(REPO)), "files": len(files) + 1, "rename_attempts": attempts,
              "inventory_sha256": sha(target / "inventory.json"), "root_before": before, "root_after": after,
              "root_unchanged": before == after and not after["mismatches"], "availability": filtered}
    (HERE.parent / "publish_september_scopes.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    return 0 if result["root_unchanged"] else 1


if __name__ == "__main__":
    sys.exit(resume(Path(sys.argv[2])) if len(sys.argv) > 2 and sys.argv[1] == "--resume-staging" else main())
