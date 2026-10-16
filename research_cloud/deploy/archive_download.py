"""Byte download acceptance of a transferred archive root (the accepted-exception archives: scen-b43ef6a-v1 and
confirm-onset-v1; design: every extant material must be preserved *and downloadable* before cloud-only eligibility).

For every file of the frozen preservation manifest, the object named by its verified transfer receipt is downloaded
at exactly the receipt's generation into a fresh directory, hashed while streaming, and must equal the manifest's
bytes and sha256. The downloaded set must equal the manifest's file set (no missing, no extra). Direct GCS reads with
the operator's credentials (the quoted, authorized archive download path); target project as the quota project.

  python -m research_cloud.deploy.archive_download --manifest M.json --receipts R.jsonl --dest DIR --out REPORT.json
      [--workers 8]
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time

PROJECT = "food-crisis-modeling-enso"


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--manifest", "--receipts", "--dest", "--out"):
        ap.add_argument(k, required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    from google.cloud import storage
    m = json.load(open(args.manifest))
    if not m.get("complete") or len(m["files"]) != m["totals"]["files"]:
        raise SystemExit("preservation manifest is not complete")
    rec = {}
    for line in open(args.receipts):
        r = json.loads(line)
        if r["status"].startswith("verified"):
            rec[r["local"]] = r                         # latest verified receipt per local path
    os.makedirs(args.dest, exist_ok=False)
    client = storage.Client(project=PROJECT, client_options={"quota_project_id": PROJECT})

    def one(f):
        r = rec.get(os.path.join(m["root"], f["path"]))
        row = {"path": f["path"], "bytes_expected": f["bytes"], "sha256_expected": f["sha256"]}
        if r is None or r["local_sha256"] != f["sha256"]:
            return {**row, "status": "no verified receipt for this file"}
        blob = client.bucket(r["bucket"]).blob(r["object"], generation=r["generation"])
        dst = os.path.join(args.dest, f["path"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        blob.download_to_filename(dst, raw_download=True, checksum="md5")
        h, n = hashlib.sha256(), 0
        with open(dst, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 22), b""):
                h.update(block)
                n += len(block)
        ok = n == f["bytes"] and h.hexdigest() == f["sha256"]
        return {**row, "object": r["object"], "generation": r["generation"], "bytes": n, "sha256": h.hexdigest(),
                "status": "verified" if ok else "mismatch"}

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, m["files"]))
    on_disk = {os.path.relpath(os.path.join(d, x), args.dest) for d, _, fs in os.walk(args.dest) for x in fs}
    expected = {f["path"] for f in m["files"]}
    report = {"root": m["root"], "manifest_files": len(expected), "verified": sum(r["status"] == "verified" for r in rows),
              "bytes": sum(r.get("bytes") or 0 for r in rows), "seconds": round(time.time() - t0, 1),
              "set_equal": on_disk == expected, "missing": sorted(expected - on_disk)[:20],
              "extra": sorted(on_disk - expected)[:20], "problems": [r for r in rows if r["status"] != "verified"][:50]}
    report["ok"] = report["verified"] == len(expected) and report["set_equal"]
    json.dump({**report, "rows": rows}, open(args.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "problems"}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
