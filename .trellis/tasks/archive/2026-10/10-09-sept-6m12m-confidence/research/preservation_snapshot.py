"""Record sha256/size of artifacts that this task must leave byte-identical (Step 0 / G6 / G7)."""
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def sha(path):
    h = hashlib.sha256()
    for attempt in range(5):
        try:
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            return h.hexdigest()
        except OSError:
            if attempt == 4:
                raise
            h = hashlib.sha256()


def record(rel):
    p = REPO / rel
    return {"sha256": sha(p), "size": p.stat().st_size}


def snapshot():
    out = {"taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), "files": {}}
    singles = ["cloud_pipeline/bootstrap/baseline.json", "cloud_pipeline/dist/cloud_pipeline.tar.gz",
               "cloud_pipeline/dist/cloud_pipeline.tar.gz.sha256", "september_manual/inventory.json",
               "september_manual/README.md", "cloud_pipeline/fallback/october_2026/retained_inventory.json"]
    for rel in singles:
        out["files"][rel] = record(rel)
    sept = json.loads((REPO / "september_manual/inventory.json").read_text())["files"]
    for rel, ident in sept.items():
        r = record(f"september_manual/{rel}")
        r["inventory_match"] = (r["sha256"], r["size"]) == (ident["sha256"], ident["size"])
        out["files"][f"september_manual/{rel}"] = r
    octo = json.loads((REPO / "cloud_pipeline/fallback/october_2026/retained_inventory.json").read_text())["files"]
    for item in octo:
        rel = f"cloud_pipeline/fallback/october_2026/{item['path']}"
        r = record(rel)
        r["inventory_match"] = (r["sha256"], r["size"]) == (item["sha256"], item["size_bytes"])
        out["files"][rel] = r
    out["all_inventory_match"] = all(v.get("inventory_match", True) for v in out["files"].values())
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1])
    if target.exists():
        raise SystemExit(f"{target} exists; refusing to overwrite")
    result = snapshot()
    target.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(len(result["files"]), "files; all_inventory_match", result["all_inventory_match"])
