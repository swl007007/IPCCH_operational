"""CP5 read-only retained-store inventory (task 10-30): every ``<table>/HEAD.json`` under one v2 store root with its
object generation and parsed HEAD (version, content URI, sha256, rows), the number of immutable version objects per
table, and the full bytes of every ledger/acceptance/pairing HEAD content (small tables) so source actions between two
inventories are established from actual version records, never inferred from unchanged coverage.

usage: store_inventory.py STORE_ROOT_URI OUT_JSON      (ADC credentials; reads only)
"""

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone

from google.cloud import storage

FULL_CONTENT = ("ledger", "acceptance", "binding", "pairing", "manifest")   # small tables kept whole


def main(root: str, out: str, client=None) -> dict:
    bucket_name, _, prefix = root.removeprefix("gs://").partition("/")
    client = client or storage.Client()
    bucket = client.bucket(bucket_name)
    heads, versions = {}, Counter()
    for blob in client.list_blobs(bucket_name, prefix=prefix.rstrip("/") + "/"):
        rel = blob.name[len(prefix.rstrip("/")) + 1:]
        if rel.endswith("/HEAD.json"):
            heads[rel[: -len("/HEAD.json")]] = blob.generation
        elif "/versions/" in rel:
            versions[rel.split("/versions/")[0]] += 1
    tables = {}
    for table, generation in sorted(heads.items()):
        data = bucket.blob(f"{prefix.rstrip('/')}/{table}/HEAD.json").download_as_bytes(if_generation_match=generation)
        head = json.loads(data)
        entry = {"head_generation": str(generation), "head_sha256": hashlib.sha256(data).hexdigest(),
                 "version": head.get("version"), "content": head.get("content"), "content_sha256": head.get("sha256"),
                 "rows": head.get("rows"), "record": head.get("record"), "version_objects": versions[table]}
        if any(k in table for k in FULL_CONTENT) and head.get("content"):
            cb, _, cp = head["content"].removeprefix("gs://").partition("/")
            content = client.bucket(cb).blob(cp).download_as_bytes()
            if hashlib.sha256(content).hexdigest() != head.get("sha256"):
                raise SystemExit(f"{table}: HEAD content differs from its recorded sha256")
            entry["content_text"] = content.decode("utf-8", errors="replace")
        tables[table] = entry
    body = {"schema": "ipcch-cp5-store-inventory-v1", "root": root,
            "read_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tables": tables, "table_count": len(tables),
            "orphan_version_tables": sorted(set(versions) - set(heads))}
    with open(out, "w") as f:
        json.dump(body, f, indent=1, sort_keys=True)
    print(json.dumps({"root": root, "tables": len(tables), "versions": sum(versions.values())}))
    return body


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
