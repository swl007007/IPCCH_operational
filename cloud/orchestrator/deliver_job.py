"""Cloud Run DEBUG entry (CP3 local/cloud parity only; never publishes a release).

Scores a fixed assembly from an inputs manifest that pins every object by URI, generation and
SHA-256 (``delivery-debug-inputs-v1``: ``{"files": {logical_path: ref}, "prepared_manifest": ref}``).
Nothing is selected by prefix or "latest"; every byte is streamed to disk at its generation and
hash-checked. Each system runs in its own process; outputs are finalized, packaged and uploaded
create-only. The production request path is ``delivery_job``.

    python -m cloud.orchestrator.deliver_job run --inputs-uri gs://B/.../inputs_manifest.json \
        --inputs-generation G --inputs-sha256 S --bucket-root gs://B --run-name <name>   # -> deliveries/debug-<name>/
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from cloud.orchestrator.delivery_job import LocalPinnedReader, PinnedDownloader, upload_tree

INPUTS_SCHEMA = "delivery-debug-inputs-v1"
REPO = Path(__file__).resolve().parents[2]


def stage_inputs(downloader: PinnedDownloader, manifest_ref: dict, inputs: Path) -> dict:
    """Fetch the pinned inputs manifest and every file it names into ``inputs/<logical path>``."""
    manifest = json.loads(downloader.fetch(manifest_ref).read_text())
    if manifest.get("schema_version") != INPUTS_SCHEMA:
        raise ValueError(f"inputs manifest schema must be {INPUTS_SCHEMA}")
    for logical, ref in manifest["files"].items():
        relative = Path(logical)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"logical path escapes the inputs root: {logical}")
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        downloader.fetch(ref).rename(target)  # same filesystem: no second in-memory copy
        downloader.paths.pop(f"{ref['uri']}#{ref['generation']}")
    prepared_path = downloader.fetch(manifest["prepared_manifest"])
    prepared = json.loads(prepared_path.read_text())
    index = {}
    for family in prepared["families"].values():
        for ref in family.get("outputs", {}).values():
            index[f"{ref['uri']}#{ref['generation']}"] = str(downloader.fetch(ref))
    return {"inputs": str(inputs), "prepared_manifest": str(prepared_path), "reader_index": index,
            "inputs_manifest": manifest}


def run_system(spec_path: Path, system: str, out: Path) -> None:
    from cloud.orchestrator.deliver import deliver, load_prepared_features

    spec = json.loads(Path(spec_path).read_text())
    inputs = Path(spec["inputs"])
    manifest = json.loads(Path(spec["prepared_manifest"]).read_text())
    deliver(origin=manifest["origin_month"], out=out, prepared_families=manifest["families"],
            prepared_features=load_prepared_features(manifest, LocalPinnedReader(spec["reader_index"])),
            ipcch_panel=inputs / "ipcch_panel.csv", ipcch_template=inputs / "ipcch_april_panel.csv",
            ipcch_package_root=inputs / "ipcch_package", fewsnet_raw=inputs / "fewsnet_refreshed_raw.csv",
            fewsnet_packages={h: inputs / f"fewsnet_package/{h}m" for h in (0, 6, 12)},
            census={s: inputs / f"{s}_country_population_reference.csv" for s in ("fewsnet", "ipcch")},
            geometry={s: inputs / f"{s}_polygons.geojson" for s in ("fewsnet", "ipcch")}, system=system)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--inputs-uri", required=True)
    run.add_argument("--inputs-generation", required=True)
    run.add_argument("--inputs-sha256", required=True)
    run.add_argument("--bucket-root", required=True)
    run.add_argument("--run-name", required=True)
    run.add_argument("--work-dir", default="/tmp/deliver-debug")
    system = commands.add_parser("system")
    system.add_argument("--spec", required=True)
    system.add_argument("--system", choices=["fewsnet", "ipcch"], required=True)
    system.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "system":
        run_system(Path(args.spec), args.system, Path(args.out))
        return 0

    from google.cloud import storage

    from cloud.orchestrator import delivery_bundle
    from cloud.orchestrator.deliver import finalize

    client = storage.Client()
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=False)
    downloader = PinnedDownloader(client, work / "downloads")
    spec = stage_inputs(downloader, {"uri": args.inputs_uri, "generation": args.inputs_generation,
                                     "sha256": args.inputs_sha256}, work / "inputs")
    spec_path = work / "spec.json"
    spec_path.write_text(json.dumps(spec))
    out = work / "delivery"
    for name in ("ipcch", "fewsnet"):  # separate processes: bounded memory
        subprocess.run([sys.executable, "-m", "cloud.orchestrator.deliver_job", "system", "--spec", str(spec_path),
                        "--system", name, "--out", str(out)], check=True)
    finalize(out)
    prepared = json.loads(Path(spec["prepared_manifest"]).read_text())
    (out / "reports/delivery.json").write_text(json.dumps(
        {"origin_month": prepared["origin_month"], "prepare_id": prepared["prepare_id"], "debug": True,
         "inputs_manifest": {"uri": args.inputs_uri, "generation": args.inputs_generation,
                             "sha256": args.inputs_sha256}}, indent=2, sort_keys=True) + "\n")
    inputs = Path(spec["inputs"])
    lock = REPO / "requirements.lock.txt"
    delivery_bundle.install_runtime_and_models(
        out, repo=REPO, fewsnet_packages={h: inputs / f"fewsnet_package/{h}m" for h in (0, 6, 12)},
        ipcch_package_root=inputs / "ipcch_package",
        lock_file=lock if lock.exists() else REPO / "deploy/october_delivery/requirements.lock.txt")
    delivery_bundle.write_bundle_docs(out, origin=prepared["origin_month"], prepare_id=prepared["prepare_id"])
    inventory = delivery_bundle.write_inventory(out, provenance={"debug_inputs_manifest": args.inputs_uri,
                                                                 "generation": args.inputs_generation,
                                                                 "sha256": args.inputs_sha256})
    validation = inventory["validation"]["status"]
    if validation == "passed":
        delivery_bundle.build_archive(out)
    refs = upload_tree(client, out, args.bucket_root, f"debug-{args.run_name}")
    print(json.dumps({"validation": validation, "uploaded": len(refs),
                      "manifest": refs.get("manifest.json"), "archive": refs.get("webapp_model_bundle.tar.gz")}))
    return 0 if validation == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
