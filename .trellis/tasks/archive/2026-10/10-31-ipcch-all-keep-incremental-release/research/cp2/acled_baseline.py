"""Task 10-31 CP0/CP2: READ-ONLY ACLED weekly retained-history fingerprint by (region, week).

Reads the real store's `acled_agg_weekly` frame, HEAD record and HEAD generation from ONE consistent snapshot
(`VersionedTable.read`, the dtypes `acled.saved_weekly` uses), and writes: HEAD identity, coverage records, row count, max week, rows inside the approved
refresh interval, and a sha256 per (region, week) over the canonical sorted rows. Run before and after the monthly
run; comparing the two proves outside-interval/regions preservation row-for-row and the appended interval content.

usage: acled_baseline.py OUT_JSON [START END]   (defaults 2026-10-17 2026-10-23)
"""

import json
import sys

from google.cloud import storage

from cloud.common.object_store import GCSObjectStore
from cloud.ipcch import acled as ac
from cloud.ipcch import entrypoint_v2 as ep
from cloud.ipcch.stores import StoreRoot, VersionedTable

sys.path.insert(0, __import__('os').path.dirname(__file__))
import incremental_checks as ic  # noqa: E402

CONFIG = "deploy/ipcch_v2_deployment.food-crisis-test.json"


def main(out, start="2026-10-17", end="2026-10-23"):
    cfg = ep.load_config(CONFIG)
    store = GCSObjectStore(storage.Client())
    root = StoreRoot("real", cfg["store_roots"]["real"])
    table = VersionedTable(store, root, "acled_agg_weekly")
    # ONE consistent snapshot: frame, HEAD record and HEAD generation together (same dtypes as acled.saved_weekly)
    frame, head, generation = table.read({"week": str, "region": str, "country": str, "admin1": str, "type": str})
    records = list(head["record"]["coverage"])
    assert tuple(ic.WEEKLY_COLUMNS) == tuple(ac.WEEKLY_COLUMNS)
    per = ic.fingerprint(frame)
    inside = frame[(frame["week"] >= start) & (frame["week"] <= end)]
    body = {"head_generation": str(generation), "head_version": head.get("version"), "head_sha256": head.get("sha256"),
            "content": head.get("content"), "rows": int(len(frame)), "max_week": str(frame["week"].max()),
            "min_week": str(frame["week"].min()), "regions": sorted(frame["region"].unique().tolist()),
            "coverage_records": records, "last_refresh": head.get("record", {}).get("last_refresh"),
            "interval": [start, end], "rows_inside_interval": int(len(inside)),
            "rows_inside_interval_by_region": inside.groupby("region").size().astype(int).to_dict(),
            "region_week": per}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({k: body[k] for k in ("head_generation", "head_version", "rows", "min_week", "max_week",
                                           "rows_inside_interval")} | {"regions": len(body["regions"]),
                                                                       "region_weeks": len(per),
                                                                       "coverage_records": len(records)}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], *sys.argv[2:4])
