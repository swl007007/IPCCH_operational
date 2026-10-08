"""Final local CP3 delivery run with bound source hashes and relocated offline replay (task evidence).

1. hash every loaded source/input/package file (start), 2. deliver IPCCH then FEWSNET in
separate processes (bounded memory), 3. finalize sidecars, install runtime + six packages,
write inventory (provenance = start hashes) and portable archive, 4. extract the archive
outside the repository and rescore/re-export offline (PYTHONPATH=runtime, no cloud
credentials), 5. re-hash sources (end) and fail if anything changed.

Usage: python run_final_local_delivery.py <prepare_id> <out_dir> <relocated_dir> [<fewsnet_checkpoint_dir>]

With a checkpoint, FEWSNET resumes from that run's hash-bound assembly/normalisation outputs
(read-only; verified by ``deliver``); its files and the local pinned prepared cache are part
of the start/end source hashes.
"""
import json, os, subprocess, sys, tarfile, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from cloud.common.object_refs import sha256_file
from cloud.orchestrator import delivery_bundle
from cloud.orchestrator.deliver import finalize

prepare_id, out, relocated = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
checkpoint = Path(sys.argv[4]) if len(sys.argv) > 4 else None
V3 = REPO / "Outcome/model_delivery/202609_h5/20260923_country_confidence_v3"
FEWS = REPO / "Outcome/fewsnet_partitioned_rf/model_artifacts/local-202604-57cb3b981198-510375f58cd8"
IPCCH = REPO / "model_artifacts/launch_2026_04"
FROZEN = Path.home() / ".venvs/ipcch-h5-202609/bin/python"
SOURCES = [V3 / "inputs/ipcch_panel.csv", V3 / "inputs/ipcch_april_panel.csv", V3 / "inputs/fewsnet_refreshed_raw.csv",
           *[V3 / f"{s}/{n}" for s in ("fewsnet", "ipcch") for n in ("country_population_reference.csv", "polygons.geojson")],
           *sorted(p for p in FEWS.rglob("*") if p.is_file()), *sorted(p for p in IPCCH.rglob("*") if p.is_file())]
# Every runtime file, not only Python (partition CSVs, schema/feature-contract JSON, ...).
CODE = [path for package in delivery_bundle.RUNTIME_PACKAGES for path in sorted((REPO / package).rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
SOURCES += [*CODE, Path(__file__).resolve(), REPO / ".trellis/tasks/10-07-october-cloud-delivery/research/cp3_evidence/run_local_delivery.py",
            REPO / "deploy/october_delivery/requirements.lock.txt"]
EXTERNAL = [*sorted(p for p in (Path("/tmp/oct-prepared-cache") / prepare_id).glob("*") if p.is_file())]
if checkpoint is not None:
    EXTERNAL += [checkpoint / name for name in ("inputs/fewsnet_base_panel.csv", "inputs/fewsnet_extra_observations.csv",
                                                "inputs/fewsnet_fill_sources.json", "inputs/fewsnet_extended_raw.csv",
                                                "inputs/fewsnet_normalized_panel.csv",
                                                "reports/fewsnet_normalization_audit.json")]


def hashes():
    return {**{str(p.relative_to(REPO)): sha256_file(p) for p in SOURCES}, **{str(p): sha256_file(p) for p in EXTERNAL}}


start = hashes()
runner = REPO / ".trellis/tasks/10-07-october-cloud-delivery/research/cp3_evidence/run_local_delivery.py"
for system in ("ipcch", "fewsnet"):
    extra = [str(checkpoint)] if system == "fewsnet" and checkpoint is not None else []
    subprocess.run([str(FROZEN), "-B", str(runner), prepare_id, str(out), system, *extra], check=True, cwd=REPO)
finalize(out)
(out / "reports/delivery.json").write_text(json.dumps({"origin_month": "2026-10", "prepare_id": prepare_id}, indent=2) + "\n")
delivery_bundle.install_runtime_and_models(out, repo=REPO, fewsnet_packages={h: FEWS / f"{h}m" for h in (0, 6, 12)},
                                           ipcch_package_root=IPCCH, lock_file=REPO / "deploy/october_delivery/requirements.lock.txt")
delivery_bundle.write_bundle_docs(out, origin="2026-10", prepare_id=prepare_id)
delivery_bundle.write_inventory(out, provenance={"source_sha256_at_start": start, "prepare_id": prepare_id,
                                                  "fewsnet_checkpoint": str(checkpoint) if checkpoint else None})
archive = delivery_bundle.build_archive(out)
relocated.mkdir(parents=True, exist_ok=False)
with tarfile.open(archive, "r:gz") as tar:
    tar.extractall(relocated, filter="data")
# No cloud credentials: drop GOOGLE/CLOUDSDK/GCLOUD variables and point gcloud/ADC lookup at an empty
# config directory; HOME is preserved (never repurposed).
empty_config = Path(tempfile.mkdtemp(prefix="oct-empty-gcloud-"))
env = {k: v for k, v in os.environ.items() if not k.startswith(("GOOGLE", "CLOUDSDK", "GCLOUD"))}
env["CLOUDSDK_CONFIG"] = str(empty_config)
env["PYTHONPATH"] = str(relocated / "runtime")
result = subprocess.run([str(FROZEN), "-B", "-m", "cloud.orchestrator.delivery_bundle", "rescore", "--root", ".",
                         "--output", "rescored"], cwd=relocated, env=env, capture_output=True, text=True)
end = hashes()
# Written after the inventory/archive and bound to their hashes; deliberately outside the
# inventory (no self-hash cycle).
report = {"pre_package_validation": json.loads((out / "manifest.json").read_text())["validation"]["status"],
          "relocation": {"rescore_exit": result.returncode, "rescore_stdout": result.stdout,
                         "rescore_stderr": result.stderr, "relocated_root": str(relocated),
                         "empty_cloud_config": str(empty_config), "home_preserved": env.get("HOME") == os.environ.get("HOME")},
          "sources_unchanged": start == end, "source_sha256_at_end": end, "archive": str(archive),
          "archive_sha256": sha256_file(archive), "inventory_sha256": sha256_file(out / "manifest.json")}
with (out.parent / f"{out.name}_relocation_receipt.json").open("x") as handle:
    json.dump(report, handle, indent=2)
print(json.dumps({k: v for k, v in report.items() if k not in ("relocation", "source_sha256_at_end")}, indent=2))
sys.exit(0 if result.returncode == 0 and start == end else 1)
