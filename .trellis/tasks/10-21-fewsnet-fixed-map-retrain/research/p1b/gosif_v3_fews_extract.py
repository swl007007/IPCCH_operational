"""Extract FEWS gpp_mean for 2025 from GOSIF-GPP v3 with the repository's zonal statistics.

Downloads each v3 monthly Mean .tif.gz from the provider (public HTTP), records size/hash,
decompresses it, compares it with the user's local 2025 TIF when present, and applies
`cloud.batch.remote_sources.zonal_statistics` (family gosif_mean, DATA/centre-in-polygon
mean) on the pinned FEWS geometry keyed by admin_code. v2 history is not touched.

Usage: python gosif_v3_fews_extract.py --runtime-root <cloud_pipeline> --out <dir>
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://data.globalecology.unh.edu/data/GOSIF-GPP_v3/Monthly/Mean/GOSIF_GPP_{m}_Mean.tif.gz"
LOCAL = Path("/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/Processed_Dataset/GOSIF_GPP_Monthly/GOSIF_GPP_mean")
MONTHS = [f"2025-{m:02d}" for m in range(1, 13)]


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.runtime_root))
    from cloud.batch.remote_sources import native_geometries, zonal_statistics

    out = args.out
    (out / "raw").mkdir(parents=True, exist_ok=False)
    geometry_path = args.runtime_root / "bootstrap/assets/fewsnet/geometry.geojson"
    roster_path = args.runtime_root / "bootstrap/assets/fewsnet/roster.csv"
    roster = pd.read_csv(roster_path, dtype=str)["admin_code"].tolist()
    geometries = native_geometries(json.loads(geometry_path.read_text()), roster=roster)
    receipt = {"started_utc": now(), "geometry": {"path": str(geometry_path), "sha256": sha256(geometry_path)},
               "roster": {"path": str(roster_path), "sha256": sha256(roster_path)},
               "method": "cloud.batch.remote_sources.zonal_statistics family=gosif_mean (mean, DATA, all_touched=False)",
               "months": {}}
    frames = []
    session = requests.Session()
    for month in MONTHS:
        tag = month.replace("-", ".M")
        url = URL.format(m=tag)
        gz = out / "raw" / f"GOSIF_GPP_{tag}_Mean.tif.gz"
        started = now()
        response = session.get(url, timeout=(30, 900), stream=True)
        response.raise_for_status()
        with gz.open("xb") as handle:
            for chunk in response.raw.stream(1 << 20, decode_content=False):
                handle.write(chunk)
        wire = response.raw.tell()
        declared = response.headers.get("content-length")
        if declared is not None and int(declared) != wire:
            raise IOError(f"{month}: {wire} bytes vs Content-Length {declared}")
        tif = out / "raw" / f"GOSIF_GPP_{tag}_Mean.tif"
        with gzip.open(gz, "rb") as src, tif.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        local = LOCAL / tif.name
        record = {"url": url, "http_status": response.status_code,
                  "headers": {k: response.headers[k] for k in ("content-length", "last-modified", "etag", "date")
                              if k in response.headers},
                  "retrieval_started_utc": started, "retrieval_completed_utc": now(),
                  "gz_sha256": sha256(gz), "gz_bytes": gz.stat().st_size,
                  "tif_sha256": sha256(tif), "local_tif_sha256": sha256(local) if local.exists() else None}
        record["local_tif_identical"] = record["tif_sha256"] == record["local_tif_sha256"]
        stats = zonal_statistics(str(tif), geometries, family="gosif_mean", month=month)
        record["areas_with_value"] = int(stats["GPP_Mean__mean"].notna().sum())
        receipt["months"][month] = record
        frames.append(stats)
        tif.unlink()
        print(month, record["areas_with_value"], record["local_tif_identical"], flush=True)
    table = pd.concat(frames, ignore_index=True)
    table.to_csv(out / "fewsnet_gosif_v3_mean_2025.csv", index=False)
    receipt["output"] = {"path": "fewsnet_gosif_v3_mean_2025.csv", "rows": len(table),
                         "sha256": sha256(out / "fewsnet_gosif_v3_mean_2025.csv")}
    receipt["completed_utc"] = now()
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
