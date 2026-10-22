"""Finish the EVI 2026-09 acquisition from its retained export shards (no new EE export).

The first run (evi_202609_acquire.py) completed the Earth Engine export, then failed on a
wrong attribute name before writing statistics. This reads the shards under the same
prefix at their current generations, records generation/sha256, mosaics them with
remote_sources.mosaic_shards and applies remote_sources.zonal_statistics to both rosters.
"""
import argparse, hashlib, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

PREFIX = "prepared/fewsnet-retrain-evi202609-20261022/sources/evi/evi_2026-09"
BUCKET = "food-crisis-test-ipcch-data"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime_root))
    import pandas as pd
    from google.cloud import storage
    from cloud.batch.remote_sources import mosaic_shards, native_geometries, zonal_statistics

    args.out.mkdir(parents=True, exist_ok=False)
    client = storage.Client(project="feisty-flames-511718-d4")
    receipt = {"started_utc": datetime.now(timezone.utc).isoformat(), "prefix": f"gs://{BUCKET}/{PREFIX}",
               "provider_id": "MODIS/061/MOD13A3/2026_09_01", "ee_task_id": "TEE3NHA7YUJMWU7LHH2KTKOS",
               "shards": []}
    with tempfile.TemporaryDirectory() as workdir:
        paths = []
        for blob in sorted(client.list_blobs(BUCKET, prefix=PREFIX), key=lambda b: b.name):
            data = blob.download_as_bytes(if_generation_match=blob.generation)
            local = Path(workdir) / blob.name.rsplit("/", 1)[-1]
            local.write_bytes(data)
            paths.append(str(local))
            receipt["shards"].append({"uri": f"gs://{BUCKET}/{blob.name}", "generation": str(blob.generation),
                                      "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        if not paths:
            raise SystemExit("no shards found")
        mosaic = mosaic_shards(paths, str(Path(workdir) / "evi_2026-09_mosaic.tif"))
        for system in ("fewsnet", "ipcch"):
            root = args.runtime_root / "bootstrap/assets" / system
            roster = pd.read_csv(root / "roster.csv", dtype=str).iloc[:, 0].tolist()
            geometries = native_geometries(json.loads((root / "geometry.geojson").read_text()), roster=roster)
            stats = zonal_statistics(mosaic, geometries, family="evi", month="2026-09")
            path = args.out / f"{system}_evi_2026-09.csv"
            stats.to_csv(path, index=False, lineterminator="\n")
            receipt[system] = {"rows": len(stats), "areas_with_value": int(stats["EVI__mean"].notna().sum()),
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    receipt["completed_utc"] = datetime.now(timezone.utc).isoformat()
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("fewsnet", "ipcch")}))


if __name__ == "__main__":
    main()
