"""Inventory a verified local delivery and make its application handoff archive."""
import argparse
import json
import platform
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.refresh_h5_inputs import sha256, write_json


def package(root):
    if (root / "reports/training_confidence_policy.json").exists():
        assert json.loads((root / "reports/training_confidence_verification.json").read_text())["status"] == "passed"
    verification = json.loads((root / "reports/final_verification.json").read_text())
    assert verification["status"] == "passed"
    assert json.loads((root / "reports/saved_input_preservation.json").read_text())["status"] == "passed"
    old = json.loads((root / "reports/previous_artifact_hashes.json").read_text())
    for path, digest in old["files"].items():
        assert sha256(Path(path)) == digest, path
    source = json.loads((root / "reports/source_manifest.json").read_text())
    for item in source["files"]:
        assert sha256(root / item["path"]) == item["sha256"]
    write_json(root / "reports/final_integrity.json", {"status": "passed",
        "previous_artifacts_unchanged": len(old["files"]), "source_snapshots_unchanged": len(source["files"])})
    small_inputs = {"fewsnet_april_features.csv", "fewsnet_identity_population.csv", "ipcch_april_panel.csv"}
    members = [p for p in sorted(root.rglob("*")) if p.is_file() and
        (p.relative_to(root).parts[0] in {"fewsnet", "ipcch", "runtime", "reports"} or
         p.name in {"README.md", "requirements.txt"} or (p.parent == root / "inputs" and p.name in small_inputs))]
    identity = {"run_id": root.name, "feature_month": "2026-04", "target_month": "2026-09", "horizon_months": 5,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "source_commit": source["commit"], "status": "passed", "models": verification["models"]}
    inventory = lambda paths: [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in paths]
    write_json(root / "bundle_manifest.json", {**identity, "scope": "portable models, April inputs, geometry, polygon/country predictions, reports and runtime; no historical panels/raw snapshots", "files": inventory(members)})
    archive = root / "webapp_model_bundle.tar.gz"
    with tarfile.open(archive, "x:gz", compresslevel=6) as tar:
        for p in [*members, root / "bundle_manifest.json"]:
            tar.add(p, arcname=str(p.relative_to(root)), recursive=False)
    # Verify archive bytes against member hashes, independently of filesystem paths.
    import hashlib
    bundle = json.loads((root / "bundle_manifest.json").read_text())
    with tarfile.open(archive, "r:gz") as tar:
        assert len(tar.getmembers()) == len(members) + 1
        for item in bundle["files"]:
            with tar.extractfile(item["path"]) as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    training_commits = {
        "fewsnet": json.loads((root / "reports/fewsnet_training.json").read_text())["source_git_commit"],
        "ipcch": json.loads((root / "reports/ipcch_training.json").read_text())["source_git_commit"]}
    write_json(root / "manifest.json", {**identity, "code_commit": code_commit, "training_code_commits": training_commits,
        "requirements": (root / "requirements.txt").read_text().splitlines(), "archive_verified": True,
        "files": inventory([p for p in sorted(root.rglob("*")) if p.is_file() and p.name != "manifest.json"])})
    print(json.dumps({"status": "passed", "root": str(root), "archive": str(archive), "archive_bytes": archive.stat().st_size}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    package(parser.parse_args().root)
