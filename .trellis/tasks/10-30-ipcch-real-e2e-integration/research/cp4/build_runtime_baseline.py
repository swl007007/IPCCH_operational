"""CP4 step 5: runtime-only rebase of the accepted FEWS-retrain operator baseline (b77cb29b) onto the v2 runtime image.

Changed from the predecessor baseline, nothing else:
* runtime.image_uri and every model's environment / acceptance.runtime -> the new image digest (lock unchanged);
* every acceptance evidence string -> cites the in-image six-slot evidence of the new build (FEWS packages validated,
  loaded and scored on the frozen October inputs byte-identically to the exact-lock reference; IPCCH legacy scopes
  loaded only, no IPCCH inference) - the 2026-10-22 precedent procedure (archive 10-21 research/p4/build_candidate_baseline.py).
Every other file (packages, assets, diagnostics, rosters, geometry) is copied byte-identically; the script refuses
any other difference.

usage: build_runtime_baseline.py OUT_DIR EVIDENCE_JSON   (cloud_pipeline on PYTHONPATH; offline, no cloud call)
"""

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

from cloud.orchestrator.delivery_job import ACCEPTANCE_REPORT_SCHEMA

OLD = Path("/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022/baseline/"
           "fews-retrain-20261022")
OLD_SHA256 = "b77cb29bd648c428cce6503bd10a2834bc976290115dd98b331ff67c1dd66c8b"
LOCK_SHA256 = "2f0a7251e0436d900ddb91d0a783421b205094ffdb26ba52ccbdfb7f9bb31e3d"
REPO_IMAGE = "us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime@sha256:"
SOURCE_COMMIT = "115798f"
# FEWS prediction digests of the local current-source six-slot run (research/cp4/six-slot-local-current-source.log)
FEWS_PREDICTIONS = {"0m": "6a99ec8f792ae15f3919e3756f8d5c6bb10caba2ddc76c224edecc34a88fafc4",
                    "6m": "84e553eb67a708ef254f7db410848c7b86188036166a8936215381d1264d5043",
                    "12m": "aacb139b6da8d66e29827deefd0cf5fff310860102ccac5ac376f4ffae4d5ae7"}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_sha(body) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def check_evidence(evidence: dict) -> str:
    """The in-image evidence must name a digest of the runtime repository, a successful build of every step, and
    FEWS scoring identical to the reference (IPCCH loaded only)."""
    image = evidence["image_uri"]
    if not image.startswith(REPO_IMAGE) or len(image) != len(REPO_IMAGE) + 64:
        raise SystemExit(f"evidence image is not a runtime digest: {image}")
    if evidence["build"]["status"] != "SUCCESS" or any(s["status"] != "SUCCESS" for s in evidence["build"]["steps"]):
        raise SystemExit("the evidence build did not succeed in every step")
    if evidence["source_commit"] != SOURCE_COMMIT:
        raise SystemExit(f"evidence source {evidence['source_commit']} is not {SOURCE_COMMIT}")
    in_image = evidence["in_image_evidence"]
    matches = in_image["matches_reference"]
    if not all(matches[k] is True for k in ("fewsnet_packages", "fewsnet_predictions", "ipcch_packages", "versions")):
        raise SystemExit(f"in-image evidence does not match the reference: {matches}")
    if in_image["requirements_lock_sha256"] != LOCK_SHA256:
        raise SystemExit("in-image lock is not the exact lock")
    for horizon, expected in FEWS_PREDICTIONS.items():
        if in_image["fewsnet"][horizon]["prediction_sha256"] != expected:
            raise SystemExit(f"FEWS {horizon} in-image prediction differs from the local current-source evidence")
    if set(in_image["ipcch"]) != {"0m", "6m", "12m"}:
        raise SystemExit("IPCCH legacy scopes were not all loaded in the image")
    return image


def main(out: Path, evidence_path: Path) -> dict:
    if sha(OLD / "baseline.json") != OLD_SHA256:
        raise SystemExit("predecessor baseline identity mismatch")
    old = json.loads((OLD / "baseline.json").read_text())
    if old["runtime"]["requirements_lock_sha256"] != LOCK_SHA256:
        raise SystemExit("predecessor lock is not the exact lock")
    image = check_evidence(json.loads(evidence_path.read_text()))
    out.mkdir(parents=True, exist_ok=False)
    for relative, entry in old["files"].items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OLD / relative, target)
        if sha(target) != entry["sha256"]:
            raise SystemExit(f"{relative} differs from the predecessor baseline record")
    environment = {"image_uri": image, "requirements_lock_sha256": LOCK_SHA256}
    note = (f"runtime-only rebase of baseline {OLD_SHA256} onto {image} (source {SOURCE_COMMIT}); in-image six-slot "
            f"evidence research/cp4/build/six-slot-runtime-evidence.json (sha256 {sha(evidence_path)}): FEWS packages "
            "fully validated, loaded and scored on the frozen October FEWS inputs byte-identically to the exact-lock "
            "reference; IPCCH scopes loaded only (no IPCCH inference); packages and assets byte-identical")
    models = []
    for model in old["models"]:
        model = copy.deepcopy(model)
        if json_sha(model["manifest"]) != model["manifest_sha256"]:
            raise SystemExit(f"{model['package_id']}: manifest digest mismatch in the predecessor")
        model["environment"] = environment
        model["acceptance"] = {
            "schema_version": ACCEPTANCE_REPORT_SCHEMA, "status": "accepted", "system": model["system"],
            "horizon_months": model["horizon_months"], "package_id": model["package_id"],
            "package_manifest_sha256": model["manifest_sha256"], "feature_schema_sha256": model["feature_schema_sha256"],
            "runtime": {"image_uri": image, "environment_manifest_sha256": json_sha(environment)}, "evidence": note}
        models.append(model)
    baseline = {**old, "runtime": environment, "models": models}
    (out / "baseline.json").write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    files = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    changed = sorted(r for r in files if r == "baseline.json" or old["files"].get(r, {}).get("sha256") != files[r])
    if changed != ["baseline.json"] or set(files) - {"baseline.json"} != set(old["files"]):
        raise SystemExit(f"unexpected change set {changed}")
    unchanged_keys = {k: baseline[k] == old[k] for k in ("delivery", "sources", "files", "schema_version")}
    if not all(unchanged_keys.values()):
        raise SystemExit(f"baseline sections changed: {unchanged_keys}")
    return {"baseline": str(out / "baseline.json"), "baseline_sha256": files["baseline.json"],
            "predecessor_baseline_sha256": OLD_SHA256, "image_uri": image, "files": len(files),
            "changed": changed, "unchanged_sections": unchanged_keys}


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2])), indent=2, sort_keys=True))
