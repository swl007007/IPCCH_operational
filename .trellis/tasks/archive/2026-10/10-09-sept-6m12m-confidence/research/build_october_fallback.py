"""D18/D21: back up the October smoke fallback and rebuild ``cloud_pipeline/fallback/october_2026`` from the
confidence rerun, in the same compact layout (``compact-october-fallback-v1``).

Usage: python build_october_fallback.py --download DIR --replay DIR --cloud-run JSON [--execute]

Gates (all required, checked before anything is written): the comparison report passed for this download,
the relocated replay passed (members, rescore all_equal, current validation), the cloud run status is
``succeeded``, the old fallback matches its ``retained_inventory.json`` and the fill audit matches the
delivery manifest. Then: create-only backup to the legacy archive (hash-verified), staged rebuild (hash-
verified), swap by rename, final inventory verification, removal of the swapped-out copy.
Without ``--execute`` only the gates run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
CP = REPO / "cloud_pipeline"
FALLBACK = CP / "fallback/october_2026"
BACKUP_ROOT = REPO.parent / "legacy_archive/IPCCH_monthly_operational/2026-10-09-october-smoke-pre-confidence"
BACKUP = BACKUP_ROOT / "october_2026"
CHECK = HERE.parent / "october_confidence_check.json"
REPORTS = ("delivery.json", "diagnostic_availability.csv", "fewsnet_assembly.json",
           "fewsnet_diagnostic_declarations.json", "fewsnet_normalization_audit.json", "ipcch_assembly.json",
           "ipcch_diagnostic_declarations.json")
TABLES = {"fewsnet": ("country_confidence", "country_predictions", "polygon_confidence", "polygon_model_mapping",
                      "polygon_predictions"),
          "ipcch": ("country_confidence", "country_predictions", "polygon_model_mapping", "polygon_predictions",
                    "polygon_training_errors")}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(root: Path, inventory: dict) -> list[str]:
    bad = [f["path"] for f in inventory["files"]
           if not (root / f["path"]).is_file() or (root / f["path"]).stat().st_size != f["size_bytes"]
           or sha(root / f["path"]) != f["sha256"]]
    listed = {f["path"] for f in inventory["files"]} | {"retained_inventory.json"}
    extra = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
                   and p.relative_to(root).as_posix() not in listed)
    return bad + [f"unexpected:{p}" for p in extra]


def gates(download: Path, replay: Path, cloud_run: dict) -> dict:
    check = json.loads(CHECK.read_text())
    member = json.loads((replay / "member_check.json").read_text())
    log = (replay / "rescore.log").read_text()
    validation = json.loads((replay / "current_validation.json").read_text())
    manifest = json.loads((download / "manifest.json").read_text())
    audit = next(f for f in manifest["files"] if f["path"] == "reports/feature_fill_audit.csv")
    result = {
        "comparison_passed_for_this_download": check["passed"] and Path(check["new"]).resolve() == download.resolve(),
        "replay_members": member["passed"],
        "replay_rescore": "RESCORE_EXIT=0" in log and '"all_equal": true' in log,
        "replay_validation": validation.get("status") == "passed",
        "cloud_run_succeeded": cloud_run["run_status"]["status"] == "succeeded"
                               and cloud_run["run_status"]["run_id"] == manifest["provenance"]["run_id"],
        "old_fallback_matches_inventory": not verify(FALLBACK, json.loads((FALLBACK / "retained_inventory.json").read_text())),
        "fill_audit_matches_manifest": sha(download / audit["path"]) == audit["sha256"],
    }
    result["passed"] = all(result.values())
    return result


def fill_counts(audit: Path) -> dict:
    frame = pd.read_csv(audit, usecols=["system", "horizon_months", "fill_method"], dtype=str)
    counts = frame.groupby(["system", "horizon_months", "fill_method"]).size()
    out: dict = {}
    for (system, horizon, method), n in counts.items():
        out.setdefault(f"{system}/{horizon}m", {})[method] = int(n)
    return out


def disclosures(download: Path, old: dict) -> dict:
    manifest = json.loads((download / "manifest.json").read_text())
    fews = json.loads((download / "reports/fewsnet_assembly.json").read_text())
    ipcch = json.loads((download / "reports/ipcch_assembly.json").read_text())
    availability = pd.read_csv(download / "reports/diagnostic_availability.csv", dtype=str, keep_default_na=False)
    summary = (availability.groupby(["model_system", "horizon_months", "diagnostic_family", "status", "reason"])
               .size().reset_index(name="rows"))
    summary["horizon_months"] = summary["horizon_months"].astype(int)
    summary = summary.sort_values(["model_system", "horizon_months", "diagnostic_family", "status", "reason"])
    bases = {}
    for system, report in (("fewsnet", fews), ("ipcch", ipcch)):
        for horizon, families in report["diagnostic_declarations"].items():
            for family, item in families.items():
                bases[f"{system}/{horizon}/{family}"] = {k: item["evidence_identity"][k] for k in ("basis", "period")}
    prepared = next(r for r in manifest["provenance"]["verified_refs"] if r["field"] == "prepared_snapshot.manifest")
    return {
        "run_id": manifest["provenance"]["run_id"], "origin_month": fews["origin_month"], "targets": old["targets"],
        "prepare_id": old["prepare_id"],
        "prepared_manifest": {k: prepared[k] for k in ("uri", "generation", "sha256")},
        "provider_latest_completed_month": old["provider_latest_completed_month"],
        "provider_latest_completed_month_source": "carried from oct-final-20261008a disclosures: same prepared "
                                                  "manifest ref (uri/generation/sha256 above)",
        "wfp_acled": old["wfp_acled"],
        "fill_method_counts": fill_counts(download / "reports/feature_fill_audit.csv"),
        "fewsnet_disclosure": {"zscore_dependency_disclosure": fews["zscore_dependency_disclosure"],
                               "fewsnet_scoring_window": fews["fewsnet_scoring_window"]},
        "ipcch_disclosure": {"ipcch_chunking": ipcch["ipcch_chunking"]},
        "diagnostic_evidence_bases": bases,
        "diagnostic_availability": summary.to_dict(orient="records"),
    }


README = """# Accepted October 2026 fallback (with confidence diagnostics)

Use `scopes/0m/`, `scopes/6m/` and `scopes/12m/` for the accepted final CSVs. `shared/` provides geometry/population references; `reports/` and `replay_evidence/` retain assembly, availability and verification evidence. Targets are October 2026, April 2027 and October 2027.

This folder is the cloud rerun `{run_id}` (2026-10-09, runtime image `{image}`). It used the same inputs as the earlier smoke run `oct-final-20261008a`: prepared snapshot `full-window-20261008c`, ACLED/WFP keep, the same assets and the six unchanged model packages. Every prediction, mapping and country prediction value equals that smoke run (exact; continuous columns max abs diff {max_diff}). The difference is that the confidence columns are now populated from the baseline diagnostic evidence (`replay_evidence/october_confidence_check.json`):

- FEWSNET 0m/6m/12m: Stage3 research-run proxies `h0_validation_error_proxy_stage3_fs1_lag4_2021_2024`, `h6_validation_error_proxy_stage3_fs2_lag8_2021_2024`, `h12_validation_error_proxy_stage3_fs3_lag12_2021_2024` (2021-02..2024-10). These are not held-out errors of the delivered packages; the 0m proxy uses a 4-month lag and is more pessimistic than true 0m error. Five polygons without Stage3 history stay blank (`no_eligible_area_history`).
- IPCCH 0m/6m/12m: `training_resubstitution` (in-sample, optimistic), plus the maximum-phase complete-month residual-transfer bootstrap. Countries without complete history stay blank (`no_complete_history`); single-month countries have no interval.

The previous smoke fallback (confidence blank) is preserved byte-for-byte outside the repository in `legacy_archive/IPCCH_monthly_operational/2026-10-09-october-smoke-pre-confidence/october_2026/`.

`manifest.json` is the unchanged full-delivery manifest; many expanded runtime/input files are inside `webapp_model_bundle.tar.gz` only, so it is not an inventory of this compact folder. `retained_inventory.json` describes this folder. The archive and manifest match their recorded download identities (`replay_evidence/download.json`). A relocated offline replay of the archive reproduced all 30 tables and the availability table (`replay_evidence/rescore.log`, `member_check.json`, `current_validation.json`). Provider lag, fill counts and diagnostic availability are in `replay_evidence/oct-confidence-disclosures.json`; `replay_evidence/cloud_run.json` records the cloud execution. Do not treat fallback files as a newly refreshed monthly run.

For inspection, extract the archive to a new empty directory and follow its bundled README. Normal operations and migration are described in the cloud pipeline's README and OPERATIONS documents.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", required=True)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--cloud-run", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    download, replay = Path(args.download).resolve(), Path(args.replay).resolve()
    cloud_run = json.loads(Path(args.cloud_run).read_text())
    record = {"gates": gates(download, replay, cloud_run)}
    print(json.dumps(record["gates"], indent=1), flush=True)
    if not record["gates"]["passed"] or not args.execute:
        return 0 if record["gates"]["passed"] else 1

    old_inventory = json.loads((FALLBACK / "retained_inventory.json").read_text())
    # 1. create-only backup of the smoke fallback
    if BACKUP_ROOT.exists():
        raise SystemExit(f"{BACKUP_ROOT} already exists; refusing to overwrite")
    BACKUP.mkdir(parents=True)
    for item in [*old_inventory["files"], {"path": "retained_inventory.json"}]:
        target = BACKUP / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FALLBACK / item["path"], target)
    backup_bad = verify(BACKUP, old_inventory)
    if backup_bad or sha(BACKUP / "retained_inventory.json") != sha(FALLBACK / "retained_inventory.json"):
        raise SystemExit(f"backup verification failed: {backup_bad[:10]}")
    (BACKUP_ROOT / "README.md").write_text(
        "# October 2026 smoke fallback before confidence diagnostics\n\n"
        "`october_2026/` is a byte-for-byte copy of `cloud_pipeline/fallback/october_2026/` as it was before "
        "2026-10-09: the cloud run `oct-final-20261008a` (image sha256:41944ea0...), whose confidence columns were "
        "blank (`missing_evidence`). Every file matches its `retained_inventory.json`. It was replaced by the "
        "confidence rerun, whose predictions are identical (task `.trellis/tasks/10-09-sept-6m12m-confidence`, "
        "`research/october_confidence_check.json`). Recovery material only; not an operational input.\n")
    record["backup"] = {"path": str(BACKUP), "files": len(old_inventory["files"]) + 1, "verified": True,
                        "retained_inventory_sha256": sha(BACKUP / "retained_inventory.json")}
    print("backup verified", flush=True)

    # 2. staged rebuild
    staging = FALLBACK.with_name("october_2026.staging-confidence")
    if staging.exists():
        raise SystemExit(f"{staging} exists")
    copies = {"manifest.json": "manifest.json", "webapp_model_bundle.tar.gz": "webapp_model_bundle.tar.gz"}
    copies.update({f"reports/{name}": f"reports/{name}" for name in REPORTS})
    for system, names in TABLES.items():
        copies[f"{system}/country_population_reference.csv"] = f"shared/{system}/country_population_reference.csv"
        copies[f"{system}/polygons.geojson"] = f"shared/{system}/polygons.geojson"
        for horizon in (0, 6, 12):
            for name in names:
                copies[f"scopes/{horizon}m/{system}/{name}.csv"] = f"scopes/{horizon}m/{system}/{name}.csv"
    manifest = {f["path"]: f["sha256"] for f in json.loads((download / "manifest.json").read_text())["files"]}
    for source, target in copies.items():
        if source in manifest and sha(download / source) != manifest[source]:
            raise SystemExit(f"{source} differs from the delivery manifest")
        (staging / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(download / source, staging / target)
    evidence = staging / "replay_evidence"
    evidence.mkdir()
    shutil.copyfile(download / "download.json", evidence / "download.json")
    for name in ("member_check.json", "rescore.log", "current_validation.json"):
        shutil.copyfile(replay / name, evidence / name)
    shutil.copyfile(CHECK, evidence / "october_confidence_check.json")
    (evidence / "cloud_run.json").write_text(json.dumps(cloud_run, indent=1, sort_keys=True) + "\n")
    old_disclosures = json.loads((FALLBACK / "replay_evidence/oct-final-disclosures.json").read_text())
    (evidence / "oct-confidence-disclosures.json").write_text(
        json.dumps(disclosures(download, old_disclosures), indent=1) + "\n")
    check = json.loads(CHECK.read_text())
    max_diff = max(v["max_abs_diff"] for v in check["predictions"].values())
    (staging / "README.md").write_text(README.format(run_id=cloud_run["run_status"]["run_id"],
                                                     image=cloud_run["image_uri"].split("/")[-1],
                                                     max_diff=max_diff))
    files = sorted((p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()), key=str.lower)
    inventory = {"schema_version": old_inventory["schema_version"],
                 "files": [{"path": p, "size_bytes": (staging / p).stat().st_size, "sha256": sha(staging / p)}
                           for p in files]}
    (staging / "retained_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    if verify(staging, inventory):
        raise SystemExit("staged fallback verification failed")

    # 3. swap, verify, remove the swapped-out copy (its verified backup is in the legacy archive)
    swapped = FALLBACK.with_name("october_2026.pre-confidence")
    FALLBACK.rename(swapped)
    staging.rename(FALLBACK)
    final_bad = verify(FALLBACK, inventory)
    if final_bad:
        raise SystemExit(f"final fallback verification failed: {final_bad[:10]}")
    if verify(BACKUP, old_inventory):
        raise SystemExit("backup changed; keeping the swapped-out copy")
    shutil.rmtree(swapped)
    record["fallback"] = {"files": len(inventory["files"]) + 1, "verified": True,
                          "retained_inventory_sha256": sha(FALLBACK / "retained_inventory.json"),
                          "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (HERE.parent / "build_october_fallback.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
