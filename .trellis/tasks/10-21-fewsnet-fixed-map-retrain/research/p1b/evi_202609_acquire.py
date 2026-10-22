"""Bounded EVI 2026-09 acquisition with the existing preparation acquirer and zonal statistics.

Uses cloud.orchestrator.prepare.CloudSourceAcquirer (exact discovered EE image, contract
export spec, create-only GCS retention under <output_root>/prepared/<prepare_id>/, persisted
provider task record) and cloud.batch.remote_sources.zonal_statistics on both pinned rosters.
This is a source acquisition, not a prepare run: no plan, status or prepared manifest is written.

Usage: python evi_202609_acquire.py --runtime-root <cloud_pipeline> --out <dir>
"""
import argparse, hashlib, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_ROOT = "gs://food-crisis-test-ipcch-data"
PREPARE_ID = "fewsnet-retrain-evi202609-20261022"
DEADLINE = datetime(2026, 10, 22, 12, 45, tzinfo=timezone.utc)


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime_root))
    import ee, requests
    import pandas as pd
    from google.cloud import storage
    from cloud.common.object_store import GCSObjectStore
    from cloud.orchestrator.prepare import CloudSourceAcquirer
    from cloud.batch.remote_sources import native_geometries, zonal_statistics

    args.out.mkdir(parents=True, exist_ok=False)
    receipt = {"started_utc": now(), "output_root": OUTPUT_ROOT, "prepare_id": PREPARE_ID,
               "deadline_utc": DEADLINE.isoformat(), "earth_engine_project": "feisty-flames-511718-d4"}
    ee.Initialize(project="feisty-flames-511718-d4")
    client = storage.Client(project="feisty-flames-511718-d4")
    acquirer = CloudSourceAcquirer(ee=ee, client=client, http=requests.Session(), store=GCSObjectStore(client),
                                   output_root=OUTPUT_ROOT, deadline_utc=DEADLINE)
    published = acquirer.published_months("evi", start_month="2026-09", end_month="2026-09")
    receipt["discovered"] = published
    provider_id = published["2026-09"]
    with tempfile.TemporaryDirectory() as workdir:
        raster = acquirer.acquire("evi", "2026-09", provider_id=provider_id, prepare_id=PREPARE_ID,
                                  workdir=Path(workdir))
        receipt["raster_ref"] = raster.ref
        receipt["acquired_utc"] = now()
        for system in ("fewsnet", "ipcch"):
            root = args.runtime_root / "bootstrap/assets" / system
            roster = pd.read_csv(root / "roster.csv", dtype=str).iloc[:, 0].tolist()
            geometries = native_geometries(json.loads((root / "geometry.geojson").read_text()), roster=roster)
            stats = zonal_statistics(raster.path, geometries, family="evi", month="2026-09")
            path = args.out / f"{system}_evi_2026-09.csv"
            stats.to_csv(path, index=False)
            receipt[system] = {"rows": len(stats), "areas_with_value": int(stats["EVI__mean"].notna().sum()),
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    receipt["completed_utc"] = now()
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    print(json.dumps(receipt, default=str)[:1500])


if __name__ == "__main__":
    main()
