"""Download the confidence-rerun delivery objects needed for replay/comparison/fallback, hash-verified.

Usage: python oct_confidence_download.py --run-id RUN --dest DIR

Fetches ``manifest.json`` (records its generation/sha256), then every manifest member that is not a large
working panel/audit (``inputs/*_panel.csv``/``*_raw.csv``/``*_series.csv``, ``*feature_fill_audit.csv``), plus
``webapp_model_bundle.tar.gz`` (not a manifest member; identity = object generation + sha256, MD5-checked).
Every member's sha256 must equal the manifest. Skipped members are listed with their manifest hashes.
Writes ``DEST/download.json``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

from google.cloud import storage

PROJECT = "manuel-remote-sensing"
BUCKET = "manuel-remote-sensing-oct-delivery-debug"
SKIP = re.compile(r"(^inputs/.*(_panel|_raw|_series)\.csv$|feature_fill_audit\.csv$)")


def file_hashes(path: Path) -> tuple[str, str]:
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            sha.update(block)
            md5.update(block)
    return sha.hexdigest(), base64.b64encode(md5.digest()).decode()


def fetch(bucket, name: str, dest: Path) -> dict:
    blob = bucket.get_blob(name)
    if blob is None:
        raise SystemExit(f"missing object {name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    blob.download_to_filename(str(tmp), if_generation_match=blob.generation, timeout=600)
    sha, md5 = file_hashes(tmp)
    if blob.md5_hash and md5 != blob.md5_hash:
        raise SystemExit(f"{name}: MD5 differs from the object metadata")
    tmp.rename(dest)
    return {"uri": f"gs://{BUCKET}/{name}", "generation": str(blob.generation), "sha256": sha, "size": blob.size}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()
    root = Path(args.dest)
    root.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client(project=PROJECT).bucket(BUCKET)
    prefix = f"deliveries/{args.run_id}"
    record = {"run_id": args.run_id, "objects": {}}
    record["objects"]["manifest.json"] = fetch(bucket, f"{prefix}/manifest.json", root / "manifest.json")
    manifest = json.loads((root / "manifest.json").read_text())
    skipped, fetched = [], 0
    for member in manifest["files"]:
        path = member["path"]
        if SKIP.search(path):
            skipped.append(member)
            continue
        target = root / path
        if target.is_file() and file_hashes(target)[0] == member["sha256"]:
            fetched += 1
            continue
        got = fetch(bucket, f"{prefix}/{path}", target)
        if got["sha256"] != member["sha256"]:
            raise SystemExit(f"{path}: sha256 differs from the delivery manifest")
        fetched += 1
    record["objects"]["webapp_model_bundle.tar.gz"] = fetch(bucket, f"{prefix}/webapp_model_bundle.tar.gz",
                                                           root / "webapp_model_bundle.tar.gz")
    record.update({"manifest_members": len(manifest["files"]), "members_fetched_and_verified": fetched,
                   "members_skipped_large_working_files": skipped})
    (root / "download.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k != "members_skipped_large_working_files"}, indent=1))
    print("skipped:", [m["path"] for m in skipped])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
