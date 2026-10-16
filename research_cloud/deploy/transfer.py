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
resumed transfer); anything else is a conflict. Receipts are JSONL (with the bucket), one line per object, appended as
each finishes. A rerun skips an object only if its verified receipt matches the bucket/object/path/manifest identity
AND the current local bytes and the remote generation/checksums still equal it; a torn last line is set aside and its
object re-verified; malformed complete lines stop the run. ``--verify REPORT`` is the final fresh verification of every
entry (current local bytes vs manifest, remote generation/md5/crc32c/declared sha256; no writes) used for acceptance.
Builders refuse incomplete preservation manifests and package directories without package.json; ``--expect-files``
checks coverage. Originals are only read.

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
# Large files go up as resumable uploads in bounded requests: with the SDK default (100 MiB per request, 60 s timeout)
# every input >= ~68 MB failed with RetryError while three uploaders shared the workstation uplink (O-053).
CHUNK_BYTES = 16 * 1024 * 1024          # a multiple of 256 KiB, as GCS requires
REQUEST_TIMEOUT_S = (60, 600)           # (connect, read) per request


class TransferError(Exception):
    pass


def from_preservation(manifest_path, prefix):
    m = json.load(open(manifest_path))
    if not m.get("complete") or m.get("walk_errors") or any(not c.get("ok") for c in m.get("recorded_checks", [])):
        raise TransferError(f"{manifest_path}: preservation manifest is not complete (walk errors or failed checks)")
    if not m["files"] or len(m["files"]) != m["totals"]["files"]:
        raise TransferError(f"{manifest_path}: no files, or the file list disagrees with its totals")
    root = m["root"]
    return [{"local": os.path.join(root, f["path"]), "object": f"{prefix.rstrip('/')}/{f['path']}", "sha256": f["sha256"],
             "bytes": f["bytes"], "manifest": os.path.basename(manifest_path)} for f in m["files"]]


# inventory vocabulary (research_cloud/inventory/dropbox_local.py): files on a native Linux filesystem are recorded as
# "local (non-DrvFS)"; Dropbox files present on disk as "local". Anything else (online-only, missing, error) is refused.
LOCAL_STATUSES = ("local", "local (non-DrvFS)")


def inventory_basis(e):
    """Why an inventory entry's sha256 is the frozen identity, or raise. ``match`` is True (the freshly computed P1
    hash equals the recorded/declared hash) or the string "no_recorded_value" (nothing was declared; the P1 fresh hash
    is the identity). Strings are never accepted by truthiness."""
    if e.get("local_status") not in LOCAL_STATUSES:
        raise TransferError(f"{e['id']}: inventory local_status {e.get('local_status')!r} is not local; refusing")
    if not e.get("actual_sha256") or not isinstance(e.get("actual_bytes"), int):
        raise TransferError(f"{e['id']}: inventory entry has no fresh hash/size; refusing")
    if e.get("match") is True:
        if e.get("actual_sha256") != e.get("recorded_sha256") or (
                e.get("recorded_bytes") is not None and e["recorded_bytes"] != e["actual_bytes"]):
            raise TransferError(f"{e['id']}: inventory says match but hashes/sizes differ; refusing")
        return "recorded hash matched"
    if e.get("match") == "no_recorded_value" and not e.get("recorded_sha256"):
        return "P1 fresh hash (no recorded value)"
    raise TransferError(f"{e['id']}: inventory match {e.get('match')!r} is not a hash match; refusing")


def from_inventory(inventory_path, prefix):
    inv = json.load(open(inventory_path))
    out, seen = [], set()
    for ns, block in inv["namespaces"].items():
        for e in block["files"]:
            basis = inventory_basis(e)
            if e["path"] in seen:          # shared files appear in both namespaces; transferred once
                continue
            seen.add(e["path"])
            out.append({"local": e["path"], "object": f"{prefix.rstrip('/')}/{e['id']}/{os.path.basename(e['path'])}",
                        "sha256": e["actual_sha256"], "bytes": e["actual_bytes"],
                        "manifest": f"input-inventory ({basis})"})
    return out


def from_packages(packages_dir, prefix, names=None):
    out = []
    for name in sorted(names or os.listdir(packages_dir)):
        pj = os.path.join(packages_dir, name, "package.json")
        if not os.path.exists(pj):
            raise TransferError(f"{name}: package directory without package.json; refusing an incomplete package set")
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
    record = {"bucket": bucket.name, "local": entry["local"], "object": entry["object"], "manifest": entry.get("manifest"),
              "bytes": local["bytes"], "local_sha256": local["sha256"], "local_md5": local["md5"],
              "local_crc32c": local["crc32c"], "declared_sha256": entry["sha256"]}
    if local["sha256"] != entry["sha256"] or local["bytes"] != entry["bytes"]:
        return {**record, "status": "rejected: local bytes differ from the frozen manifest"}
    blob = bucket.blob(entry["object"])
    blob.chunk_size = CHUNK_BYTES
    blob.metadata = {"sha256": entry["sha256"]}
    blob.md5_hash = local["md5"]                     # GCS validates the upload against this
    state = "uploaded"
    try:
        blob.upload_from_filename(entry["local"], if_generation_match=0, checksum=None, timeout=REQUEST_TIMEOUT_S)
    except PreconditionFailed:
        state = "already present"
    blob.reload()
    record.update(cloud_md5=blob.md5_hash, cloud_crc32c=blob.crc32c, generation=blob.generation,
                  cloud_declared_sha256=(blob.metadata or {}).get("sha256"))
    ok = blob.md5_hash == local["md5"] and blob.crc32c == local["crc32c"] and record["cloud_declared_sha256"] == entry["sha256"]
    record["status"] = f"verified ({state})" if ok else f"conflict ({state}): cloud object differs"
    return record


def read_receipts(path):
    """Receipt records; an incomplete final line (interrupted write) is moved to PATH.tail and its object is simply
    re-verified; any malformed complete line stops the run."""
    if not os.path.exists(path):
        return []
    data = open(path, "rb").read()
    lines = data.split(b"\n")
    records = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            if i == len(lines) - 1 and not data.endswith(b"\n"):          # torn tail only
                with open(path + ".tail", "ab") as f:
                    f.write(line + b"\n")
                with open(path, "wb") as f:
                    f.write(data[: len(data) - len(line)])
                break
            raise TransferError(f"{path}: malformed receipt line {i + 1}")
    return records


def resumable(bucket, entry, rec):
    """A previous verified receipt counts only for the same bucket/object/manifest identity AND after re-checking the
    current local bytes and the remote object's generation and server checksums against it."""
    if not (rec.get("status", "").startswith("verified") and rec.get("bucket") == bucket.name
            and rec.get("object") == entry["object"] and rec.get("local") == entry["local"]
            and rec.get("declared_sha256") == entry["sha256"] and rec.get("bytes") == entry["bytes"]):
        return False
    local = local_hashes(entry["local"])
    if (local["sha256"], local["md5"], local["crc32c"]) != (entry["sha256"], rec["local_md5"], rec["local_crc32c"]):
        return False
    blob = bucket.get_blob(entry["object"])
    return bool(blob) and (blob.generation, blob.md5_hash, blob.crc32c) == (rec["generation"], rec["local_md5"], rec["local_crc32c"])


def verify_one(bucket, entry, rec):
    """Final fresh verification (no writes): current local bytes vs the frozen manifest and the receipt, and the
    remote object's generation, server md5/crc32c and declared sha256."""
    local = local_hashes(entry["local"])
    blob = bucket.get_blob(entry["object"])
    out = {"bucket": bucket.name, "object": entry["object"], "local_sha256": local["sha256"],
           "manifest_sha256": entry["sha256"], "receipt_generation": (rec or {}).get("generation")}
    if blob is None:
        return {**out, "status": "missing remote object"}
    out.update(generation=blob.generation, cloud_md5=blob.md5_hash, cloud_crc32c=blob.crc32c,
               cloud_declared_sha256=(blob.metadata or {}).get("sha256"))
    ok = (local["sha256"] == entry["sha256"] and local["bytes"] == entry["bytes"] and blob.md5_hash == local["md5"]
          and blob.crc32c == local["crc32c"] and out["cloud_declared_sha256"] == entry["sha256"]
          and (rec is None or rec.get("generation") == blob.generation))
    return {**out, "status": "verified" if ok else "mismatch"}


def main(argv=None, bucket=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--receipts", required=True)
    ap.add_argument("--from-preservation")
    ap.add_argument("--from-inventory")
    ap.add_argument("--from-packages")
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--verify", metavar="REPORT", help="final fresh verification of every entry (no writes)")
    ap.add_argument("--expect-files", type=int, help="coverage: the transfer list must hold exactly this many files")
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
    if args.expect_files is not None and len(entries) != args.expect_files:
        raise SystemExit(f"coverage: {len(entries)} transfer entries, expected {args.expect_files}")
    if bucket is None:
        from google.cloud import storage
        bucket = storage.Client(project=PROJECT, client_options={"quota_project_id": PROJECT}).bucket(args.bucket)
    receipts = {}
    for rec in read_receipts(args.receipts):
        if rec.get("object") and rec.get("status", "").startswith("verified"):
            receipts[rec["object"]] = rec
    if args.verify:
        return run_verify(bucket, entries, receipts, args)
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        resumed = list(pool.map(lambda e: e["object"] in receipts and resumable(bucket, e, receipts[e["object"]]), entries))
    done = {e["object"] for e, ok in zip(entries, resumed) if ok}
    todo = [e for e in entries if e["object"] not in done][: args.limit]
    lock, counts, t0 = threading.Lock(), {}, time.time()
    with open(args.receipts, "a") as out, concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(transfer_one, bucket, e): e for e in todo}
        for fut in concurrent.futures.as_completed(futures):
            try:
                rec = fut.result()
            except Exception as e:      # noqa: BLE001 - recorded per object; a rerun retries it
                cause = getattr(e, "cause", None) or e.__cause__ or e.__context__
                rec = {"object": futures[fut]["object"], "local": futures[fut]["local"],
                       "status": f"error: {type(e).__name__}",          # exception types only, never remote text
                       "error_cause": type(cause).__name__ if cause is not None else None}
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


def run_verify(bucket, entries, receipts, args):
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(lambda e: verify_one(bucket, e, receipts.get(e["object"])), entries))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    report = {"bucket": bucket.name, "entries": len(entries), "counts": counts,
              "bytes": sum(e["bytes"] for e in entries), "seconds": round(time.time() - t0, 1),
              "complete": counts.get("verified", 0) == len(entries), "objects": results}
    with open(args.verify, "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "objects"}))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
