"""G9 data staging: upload manifest-listed files to GCS with fresh hash verification (resumable, never overwrites).

For every entry ``{"local", "object", "sha256", "bytes"}`` of a transfer list:

1. one fresh read of the local bytes computes sha256, md5 and crc32c together; the sha256 must equal the frozen manifest
   (preservation/inventory/package manifest - including manifests whose hashes came from a cache) and the size must
   equal the manifest size, else the file is rejected and not uploaded;
2. upload with ``if_generation_match=0`` (create only, never overwrite), sending the local md5 so GCS itself rejects a
   corrupted upload; the manifest sha256 is attached as *declared* metadata ``sha256`` (GCS does not compute sha256);
3. the object is read back: its server-computed md5 and crc32c must equal the local values; the receipt records path,
   object, bytes, local sha256/md5/crc32c, cloud md5/crc32c and the object generation.

An object that already exists is accepted only if its server md5/crc32c and declared sha256 equal this file's (a
resumed transfer); anything else is a conflict. Receipts are JSONL, one line per object, appended as each finishes;
a rerun skips objects with a verified receipt. Originals are only read.

Transfer lists are built from: a preservation manifest (``--from-preservation MANIFEST --prefix P``), the input
inventory (``--from-inventory``), or package directories (``--from-packages DIR``).

  python -m research_cloud.deploy.transfer --bucket B --receipts R.jsonl (--from-preservation M --prefix P | ...)
      [--workers 8] [--limit N]
"""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import sys
import threading
import time

PROJECT = "food-crisis-modeling-enso"


class TransferError(Exception):
    pass


def from_preservation(manifest_path, prefix):
    m = json.load(open(manifest_path))
    root = m["root"]
    return [{"local": os.path.join(root, f["path"]), "object": f"{prefix.rstrip('/')}/{f['path']}", "sha256": f["sha256"],
             "bytes": f["bytes"], "manifest": os.path.basename(manifest_path)} for f in m["files"]]


def from_inventory(inventory_path, prefix):
    inv = json.load(open(inventory_path))
    out, seen = [], set()
    for ns, block in inv["namespaces"].items():
        for e in block["files"]:
            if e["path"] in seen:          # shared files appear in both namespaces; transferred once
                continue
            seen.add(e["path"])
            out.append({"local": e["path"], "object": f"{prefix.rstrip('/')}/{e['id']}/{os.path.basename(e['path'])}",
                        "sha256": e["actual_sha256"], "bytes": e["actual_bytes"], "manifest": "input-inventory"})
    return out


def from_packages(packages_dir, prefix, names=None):
    out = []
    for name in sorted(names or os.listdir(packages_dir)):
        pj = os.path.join(packages_dir, name, "package.json")
        if not os.path.exists(pj):
            continue
        meta = json.load(open(pj))
        files = dict(meta["files"])
        for rel, rec in sorted(files.items()):
            out.append({"local": os.path.join(packages_dir, name, rel), "object": f"{prefix.rstrip('/')}/{name}/{rel}",
                        "sha256": rec["sha256"], "bytes": rec["bytes"], "manifest": f"{name}/package.json"})
        data = open(pj, "rb").read()
        out.append({"local": pj, "object": f"{prefix.rstrip('/')}/{name}/package.json",
                    "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "manifest": "package.json (self)"})
    return out


def local_hashes(path):
    import google_crc32c
    sha, md5, crc = hashlib.sha256(), hashlib.md5(), google_crc32c.Checksum()
    size = 0
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            sha.update(block)
            md5.update(block)
            crc.update(block)
            size += len(block)
    return {"sha256": sha.hexdigest(), "md5": base64.b64encode(md5.digest()).decode(),
            "crc32c": base64.b64encode(crc.digest()).decode(), "bytes": size}


def transfer_one(bucket, entry):
    from google.api_core.exceptions import PreconditionFailed
    local = local_hashes(entry["local"])
    record = {"local": entry["local"], "object": entry["object"], "manifest": entry.get("manifest"),
              "bytes": local["bytes"], "local_sha256": local["sha256"], "local_md5": local["md5"],
              "local_crc32c": local["crc32c"], "declared_sha256": entry["sha256"]}
    if local["sha256"] != entry["sha256"] or local["bytes"] != entry["bytes"]:
        return {**record, "status": "rejected: local bytes differ from the frozen manifest"}
    blob = bucket.blob(entry["object"])
    blob.metadata = {"sha256": entry["sha256"]}
    blob.md5_hash = local["md5"]                     # GCS validates the upload against this
    state = "uploaded"
    try:
        blob.upload_from_filename(entry["local"], if_generation_match=0, checksum=None)
    except PreconditionFailed:
        state = "already present"
    blob.reload()
    record.update(cloud_md5=blob.md5_hash, cloud_crc32c=blob.crc32c, generation=blob.generation,
                  cloud_declared_sha256=(blob.metadata or {}).get("sha256"))
    ok = blob.md5_hash == local["md5"] and blob.crc32c == local["crc32c"] and record["cloud_declared_sha256"] == entry["sha256"]
    record["status"] = f"verified ({state})" if ok else f"conflict ({state}): cloud object differs"
    return record


def done_objects(receipts):
    if not os.path.exists(receipts):
        return set()
    return {json.loads(line)["object"] for line in open(receipts) if line.strip()
            and json.loads(line)["status"].startswith("verified")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--receipts", required=True)
    ap.add_argument("--from-preservation")
    ap.add_argument("--from-inventory")
    ap.add_argument("--from-packages")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    if args.from_preservation:
        entries = from_preservation(args.from_preservation, args.prefix)
    elif args.from_inventory:
        entries = from_inventory(args.from_inventory, args.prefix)
    elif args.from_packages:
        entries = from_packages(args.from_packages, args.prefix)
    else:
        raise SystemExit("one transfer-list source is required")
    if len({e["object"] for e in entries}) != len(entries):
        raise SystemExit("transfer list maps two files to one object")
    done = done_objects(args.receipts)
    todo = [e for e in entries if e["object"] not in done][: args.limit]
    from google.cloud import storage
    bucket = storage.Client(project=PROJECT, client_options={"quota_project_id": PROJECT}).bucket(args.bucket)
    lock, counts, t0 = threading.Lock(), {}, time.time()
    with open(args.receipts, "a") as out, concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(transfer_one, bucket, e): e for e in todo}
        for fut in concurrent.futures.as_completed(futures):
            try:
                rec = fut.result()
            except Exception as e:      # noqa: BLE001 - recorded per object; a rerun retries it
                rec = {"object": futures[fut]["object"], "local": futures[fut]["local"],
                       "status": f"error: {type(e).__name__}"}
            rec["time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            with lock:
                out.write(json.dumps(rec) + "\n")
                out.flush()
                key = rec["status"].split(" (")[0].split(":")[0]
                counts[key] = counts.get(key, 0) + 1
    summary = {"entries": len(entries), "already_verified": len(done), "attempted": len(todo), "counts": counts,
               "bytes_attempted": sum(e["bytes"] for e in todo), "seconds": round(time.time() - t0, 1)}
    print(json.dumps(summary))
    return 0 if set(counts) <= {"verified"} else 1


if __name__ == "__main__":
    sys.exit(main())
