"""Build the FEWS retrain candidate operator baseline (operator-baseline/v1) from the accepted bootstrap.

Changed from the accepted bootstrap, nothing else:
* FEWS 0/6/12m packages -> the all-history packages (suite full-202610-ff389b11af93-02caeb861750);
* assets/fewsnet/history_panel.csv -> the accepted v2 SOURCE panel (a83f5f4b...; delivery normalizes it,
  as the accepted snapshot-overlay check did; the fit stays pinned to normalized 02caeb86...);
* assets/{system}/history/*.csv -> the exact history assets the succeeded snapshot
  fewsnet-retrain-20261022a was prepared from (pinned refs in its prepare request);
* assets/retained_{acled,wfp}.csv -> regenerated family projections of the two consumed panels;
* FEWS diagnostics -> frozen_output entries copying the accepted October confidence outputs
  (oct-confidence-20261009b), with their availability, raw evidence and declarations;
* runtime + every acceptance report -> the new image digest, citing the in-image six-slot evidence.
IPCCH packages, assets and diagnostics are byte-identical to the bootstrap.

usage: build_candidate_baseline.py OUT_DIR   (run with the repository's cloud_pipeline on PYTHONPATH)
"""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cloud.orchestrator import delivery_outputs as do
from cloud.orchestrator.delivery_job import (ACCEPTANCE_REPORT_SCHEMA, PACKAGE_MANIFEST_SCHEMA, retained_family_rows,
                                             retained_family_sha256)
from fewsnet_partitioned_rf_pipeline.local.package import LOCAL_PACKAGE_FILES

REPO = Path(__file__).resolve().parents[5] / "cloud_pipeline"
TASK = Path(__file__).resolve().parents[1]
S = Path("/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022")
OLD = REPO / "bootstrap"
FALLBACK = REPO / "fallback/october_2026"
FIT = S / "fit/full-202610-ff389b11af93-02caeb861750"
SUITE = "full-202610-ff389b11af93-02caeb861750"
PANEL = S / "panel/v2/FEWSNET_versioned_source_panel_20261022.csv"
PANEL_SHA256 = "a83f5f4b5eb33022960e43606f32afaec0cb15c10110ad1b56564790d637b722"
SNAPSHOT_REQUEST = S / "candidate/snapshot_prepare_request.json"
SNAPSHOT_REQUEST_SHA256 = "3797ead15654d65d8faedb01a6ddf83937c8726805823a2aaf0c47800d2addeb"
IMAGE = ("us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime"
         "@sha256:487a23159b3bb151245530b6cfcef71820c8a716a189e5a2a3bbcc3074c97fae")
SOURCE_DELIVERY = "oct-confidence-20261009b"
SOURCE_MANIFEST_SHA256 = "265a0fb95a8dbeda49a09d6a9fcafe149d3e4033438b38ec91d3b795a39aebe4"
OLD_PACKAGE = "local-202604-57cb3b981198-510375f58cd8"
RAW = {0: "evidence/fewsnet_0m_stage3_fs1_area.csv", 6: "evidence/fewsnet_6m_stage3_fs2_area.csv",
       12: "evidence/fewsnet_12m_stage3_fs3_area.csv"}
FROZEN = f"evidence/frozen/{SOURCE_DELIVERY}"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_sha(body) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def gcs_pinned(ref: dict, destination: Path) -> None:
    """Download one pinned object generation (read-only) and verify its SHA-256."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    single_stream = {**os.environ, "CLOUDSDK_STORAGE_SLICED_OBJECT_DOWNLOAD_THRESHOLD": "0",
                     "CLOUDSDK_STORAGE_PROCESS_COUNT": "1", "CLOUDSDK_STORAGE_THREAD_COUNT": "1"}
    subprocess.run(["gcloud", "--configuration=food-crisis-test", "storage", "cp",
                    f"{ref['uri']}#{ref['generation']}", str(destination)], check=True, capture_output=True,
                   env=single_stream, timeout=1800)
    if sha(destination) != ref["sha256"]:
        raise SystemExit(f"pinned object hash mismatch: {ref['uri']}#{ref['generation']}")


def main(out: Path) -> dict:
    old = json.loads((OLD / "baseline.json").read_text())
    out.mkdir(parents=True, exist_ok=False)
    if sha(PANEL) != PANEL_SHA256 or sha(SNAPSHOT_REQUEST) != SNAPSHOT_REQUEST_SHA256:
        raise SystemExit("panel or snapshot request identity mismatch")
    source_inventory = {e["path"]: e["sha256"] for e in json.loads((FALLBACK / "manifest.json").read_text())["files"]}
    if sha(FALLBACK / "manifest.json") != SOURCE_MANIFEST_SHA256:
        raise SystemExit("accepted October source manifest identity mismatch")
    changed = {}

    def place(relative: str, source: Path) -> None:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    # unchanged bootstrap members (IPCCH packages/assets, raw evidence, populations, geometry, rosters)
    for relative in old["files"]:
        if relative.startswith("models/fewsnet/") or relative in ("assets/fewsnet/history_panel.csv",
                                                                  "assets/retained_acled.csv",
                                                                  "assets/retained_wfp.csv") \
                or "/history/" in relative:
            continue
        place(relative, OLD / relative)
    # new FEWS packages
    environment = {"image_uri": IMAGE, "requirements_lock_sha256": old["runtime"]["requirements_lock_sha256"]}
    evidence = json.loads((TASK / "p4/six-slot-runtime-evidence.json").read_text())
    evidence_note = (f"new runtime {IMAGE} (Cloud Build {evidence['build']['id']}, source {evidence['source_commit']}); "
                     "in-image six-slot evidence research/p4/six-slot-runtime-evidence.json "
                     f"(sha256 {sha(TASK / 'p4/six-slot-runtime-evidence.json')}): FEWS packages fully validated, "
                     "loaded and scored on the frozen October FEWS inputs byte-identically to the exact-lock "
                     "reference; IPCCH scopes loaded only (no IPCCH inference)")
    models = []
    for model in old["models"]:
        model = copy.deepcopy(model)
        horizon = model["horizon_months"]
        if model["system"] == "fewsnet":
            package = FIT / f"model_artifacts/{horizon}m"
            for name in LOCAL_PACKAGE_FILES:
                place(f"models/fewsnet/{horizon}m/{name}", package / name)
            package_id = f"{SUITE}/{horizon}m"
            manifest = {"schema_version": PACKAGE_MANIFEST_SCHEMA, "system": "fewsnet", "horizon_months": horizon,
                        "package_id": package_id,
                        "files": [{"path": name, "sha256": sha(package / name)} for name in LOCAL_PACKAGE_FILES]}
            schema = json.loads((package / "training_report.json").read_text())["feature_schema_sha256"]
            model.update(package_id=package_id, manifest=manifest, feature_schema_sha256=schema)
            changed[f"models/fewsnet/{horizon}m"] = package_id
        model["environment"] = environment
        model["manifest_sha256"] = json_sha(model["manifest"])
        model["acceptance"] = {
            "schema_version": ACCEPTANCE_REPORT_SCHEMA, "status": "accepted", "system": model["system"],
            "horizon_months": horizon, "package_id": model["package_id"],
            "package_manifest_sha256": model["manifest_sha256"], "feature_schema_sha256": model["feature_schema_sha256"],
            "runtime": {"image_uri": IMAGE, "environment_manifest_sha256": json_sha(environment)},
            "evidence": evidence_note}
        models.append(model)
    # assets: v2 FEWS history panel, snapshot history assets, regenerated retained families
    place("assets/fewsnet/history_panel.csv", PANEL)
    request = json.loads(SNAPSHOT_REQUEST.read_text())
    for system, assets in request["systems"].items():
        for kind in ("roster", "geometry"):
            name = "roster.csv" if kind == "roster" else "geometry.geojson"
            if sha(out / f"assets/{system}/{name}") != assets[kind]["sha256"]:
                raise SystemExit(f"snapshot {system} {kind} is not the bootstrap {kind}")
        for family, ref in assets["history"].items():
            gcs_pinned(ref, out / f"assets/{system}/history/{family}.csv")
    history = {"fewsnet": str(out / "assets/fewsnet/history_panel.csv"),
               "ipcch": str(out / "assets/ipcch/history_panel.csv")}
    for family in ("acled", "wfp"):
        with (out / f"assets/retained_{family}.csv").open("w", encoding="utf-8", newline="") as handle:
            for block in retained_family_rows(history, family):
                handle.write(block)
        if sha(out / f"assets/retained_{family}.csv") != retained_family_sha256(history, family):
            raise SystemExit(f"retained {family} does not reproduce its family projection")
    # frozen October FEWS confidence sources (byte-identical to the accepted source inventory)
    frozen_sources = {f"scopes/{h}m/fewsnet/{n}.csv" for h in (0, 6, 12)
                      for n in ("polygon_confidence", "country_confidence")}
    frozen_sources |= {"reports/diagnostic_availability.csv", "reports/fewsnet_diagnostic_declarations.json"}
    for relative in sorted(frozen_sources):
        if sha(FALLBACK / relative) != source_inventory[relative]:
            raise SystemExit(f"fallback {relative} differs from the accepted source inventory")
        place(f"{FROZEN}/{relative}", FALLBACK / relative)
    diagnostics = []
    for entry in old["delivery"]["diagnostics"]:
        if entry["system"] != "fewsnet":
            diagnostics.append(entry)
            continue
        horizon, family = entry["horizon_months"], entry["family"]
        basis, period = do.APPROVED_PROXY_EVIDENCE[("fewsnet", horizon)]
        diagnostics.append({
            "system": "fewsnet", "horizon_months": horizon, "family": family, "status": "frozen_output",
            "evidence": {"local_path": f"{FROZEN}/scopes/{horizon}m/fewsnet/{family}.csv"},
            "source_availability": {"local_path": f"{FROZEN}/reports/diagnostic_availability.csv"},
            "source_evidence": {"local_path": RAW[horizon]},
            "source_declarations": {"local_path": f"{FROZEN}/reports/fewsnet_diagnostic_declarations.json"},
            "source_delivery_id": SOURCE_DELIVERY, "evidence_model_package_id": f"{OLD_PACKAGE}/{horizon}m",
            "evidence_horizon_months": horizon, "evidence_basis": basis, "evidence_period": period})
    delivery = {**old["delivery"], "diagnostics": diagnostics}
    files = {p.relative_to(out).as_posix(): {"sha256": sha(p), "size_bytes": p.stat().st_size}
             for p in sorted(out.rglob("*")) if p.is_file()}
    baseline = {"schema_version": "operator-baseline/v1", "runtime": environment, "models": models,
                "delivery": delivery, "sources": old["sources"], "files": files}
    (out / "baseline.json").write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    unchanged = sorted(r for r in files if r in old["files"] and old["files"][r]["sha256"] == files[r]["sha256"])
    return {"baseline": str(out / "baseline.json"), "baseline_sha256": sha(out / "baseline.json"),
            "predecessor_baseline_sha256": sha(OLD / "baseline.json"), "files": len(files),
            "bytes": sum(f["size_bytes"] for f in files.values()),
            "changed_or_new": sorted(set(files) - set(unchanged)), "unchanged": len(unchanged),
            "removed": sorted(set(old["files"]) - set(files)), "packages": changed}


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=2, sort_keys=True))
