"""Pinned preparation inputs for the retrain release snapshot (create-only, production bucket).

History per system/family = the accepted `full-20261008a` history asset followed by the
accepted `full-window-20261008c` prepared outputs (no overlapping months; checked). Geometry
and roster are server-side copies of the same pinned assets. A preparation over these
inputs then only re-extracts each provider's latest month (and GOSIF mean 2025 under the v3
contract). Writes `assets_manifest.json` and the prepare request; never overwrites.

Usage: python build_snapshot_history_assets.py --runtime-root <cloud_pipeline> --work <dir>
"""
import argparse, hashlib, io, json, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from google.cloud import storage

BUCKET = "food-crisis-test-ipcch-data"
ASSET_PREFIX = "assets/fewsnet-retrain-20261022"
PREPARE_ID = "fewsnet-retrain-20261022a"
OLD = "gs://manuel-remote-sensing-oct-delivery-debug"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(client, uri, generation, expected_sha):
    bucket, name = uri[5:].split("/", 1)
    blob = client.bucket(bucket).get_blob(name, generation=int(generation))
    data = blob.download_as_bytes(raw_download=True, checksum="crc32c")
    if sha(data) != expected_sha:
        raise ValueError(f"{uri}#{generation} sha256 mismatch")
    return data


def write_create_only(client, name, data, content_type="text/csv"):
    blob = client.bucket(BUCKET).blob(name)
    blob.upload_from_string(data, content_type=content_type, if_generation_match=0)
    blob.reload()
    return {"uri": f"gs://{BUCKET}/{name}", "generation": str(blob.generation), "sha256": sha(data)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime_root))
    from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SOURCE_CONTRACTS, SYSTEM_FAMILIES
    from cloud.orchestrator.prepare import PREPARE_SCHEMA_VERSION

    args.work.mkdir(parents=True, exist_ok=False)
    client = storage.Client(project="feisty-flames-511718-d4")
    old = json.loads(Path(args.work.parent / "pinned-full-window-20261008c/prepared_manifest.json").read_text())
    report = {"started_utc": datetime.now(timezone.utc).isoformat(), "source_snapshot": old["request"],
              "systems": {}}
    systems = {}
    for system, assets in old["systems"].items():
        entry = {"history": {}}
        for kind in ("geometry", "roster"):
            data = read(client, assets[kind]["uri"], assets[kind]["generation"], assets[kind]["sha256"])
            name = f"{ASSET_PREFIX}/{system}/{assets[kind]['uri'].rsplit('/', 1)[-1]}"
            entry[kind] = write_create_only(client, name, data,
                                            "application/geo+json" if kind == "geometry" else "text/csv")
            report["systems"].setdefault(system, {})[kind] = {"from": assets[kind], "to": entry[kind]}
        for family in SYSTEM_FAMILIES[system]:
            href = assets["history"][family]
            history = pd.read_csv(io.BytesIO(read(client, href["uri"], href["generation"], href["sha256"])),
                                  dtype={"admin_code": str, "month": str})
            out = old["families"][family]["outputs"][system]
            prepared = pd.read_csv(io.BytesIO(read(client, out["uri"], out["generation"], out["sha256"])),
                                   dtype={"admin_code": str, "month": str})
            contract = SOURCE_CONTRACTS[family]
            columns = ["admin_code", "month"] + [f"{b}__{r}" for b in contract.bands for r in contract.reducers]
            if list(history.columns) != columns or list(prepared.columns) != columns:
                raise ValueError(f"{system}/{family}: column contract mismatch")
            overlap = set(history["month"]) & set(prepared["month"])
            if overlap:
                raise ValueError(f"{system}/{family}: overlapping months {sorted(overlap)[:3]}")
            combined = pd.concat([history, prepared], ignore_index=True).sort_values(
                ["admin_code", "month"], kind="mergesort")
            if combined.duplicated(["admin_code", "month"]).any():
                raise ValueError(f"{system}/{family}: duplicate keys")
            data = combined.to_csv(index=False, lineterminator="\n").encode()
            (args.work / f"{system}_{family}.csv").write_bytes(data)
            entry["history"][family] = write_create_only(client, f"{ASSET_PREFIX}/{system}/history/{family}.csv",
                                                         data)
            report["systems"][system][f"history_{family}"] = {
                "from_history": href, "from_prepared_output": out, "to": entry["history"][family],
                "rows": len(combined), "months": [combined["month"].min(), combined["month"].max()]}
        systems[system] = entry
    request = {
        "schema_version": PREPARE_SCHEMA_VERSION, "prepare_id": PREPARE_ID, "origin_month": "2026-10",
        "cutoff_utc": "2026-10-21T23:59:59Z", "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
        "systems": systems,
        "operator": ("weilun.shi via Claude executor, task 10-21-fewsnet-fixed-map-retrain; executed in-process "
                     "with cloud.orchestrator.prepare.run_prepare (local, not Cloud Run/Batch) from a clean source "
                     "commit; history = full-20261008a history + full-window-20261008c outputs"),
    }
    request_bytes = (json.dumps(request, indent=2, sort_keys=True) + "\n").encode()
    report["prepare_request"] = write_create_only(
        client, f"prepare_requests/{PREPARE_ID}/prepare_request.json", request_bytes, "application/json")
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    (args.work / "assets_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["prepare_request"]))


if __name__ == "__main__":
    main()
