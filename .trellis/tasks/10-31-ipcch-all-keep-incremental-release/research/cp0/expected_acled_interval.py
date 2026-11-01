"""Task 10-31: expected ACLED interval content (LOCAL only; no cloud). The pinned prepared export (sha e660c7e8)
through the product path the runtime uses (retained.strict_csv -> acled.parse_export with the accepted bundle's ACLED
tables), then the store's CSV round-trip (stores.frame_to_csv -> csv_to_frame with saved_weekly dtypes), fingerprinted
by incremental_checks.fingerprint. Post-run, the stored interval keys must equal this EXACTLY.

usage: expected_acled_interval.py OUT_JSON"""
import hashlib, json, sys
from pathlib import Path
from cloud.ipcch import acled, generation, retained
from cloud.ipcch.stores import csv_to_frame, frame_to_csv
sys.path.insert(0, str(Path(__file__).parent))
import incremental_checks as ic  # noqa: E402

CSV = "/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/incremental-20261101/prepared/acled_regional_aggregate_20261017_20261023.csv"
SEL = "/home/swl007007/ipcch-operator/food-crisis-test/v2-inputs/incremental-20261101/prepared/selections.json"
BUNDLE = "/home/swl007007/ipcch-operator/food-crisis-test/v2-build/cp4-115798f-20261031T135044Z/tmp.oV5ZoayeBG/ipcch/handoff-bundle"
data = open(CSV, "rb").read()
assert hashlib.sha256(data).hexdigest() == "e660c7e8eb126c102145069441805bf55314914cb6297601bd5a150a87e47e8a"
choice = json.load(open(SEL))["choices"]["acled"]
tables = acled.AcledTables.from_files({k: str(Path(BUNDLE) / v) for k, v in generation.ACLED_FILES.items()})
frame = retained.strict_csv(data.decode("utf-8-sig"), "pinned ACLED refresh export", acled.EXPORT_COLUMNS)
rows, stats = acled.parse_export(frame, start=choice["start"], end=choice["end"], regions=choice["regions"], tables=tables)
back = csv_to_frame(frame_to_csv(rows[list(acled.WEEKLY_COLUMNS)]),
                    {"week": str, "region": str, "country": str, "admin1": str, "type": str})
fp = ic.fingerprint(back)
body = {"source_sha256": hashlib.sha256(data).hexdigest(), "start": choice["start"], "end": choice["end"],
        "regions": sorted(choice["regions"]), "rows": int(len(rows)), "keys": len(fp), "parse_stats": stats, "region_week": fp}
json.dump(body, open(sys.argv[1], "x"), indent=1, sort_keys=True, default=str)
print(json.dumps({k: body[k] for k in ("rows", "keys", "start", "end")} | {"weeks": sorted({k.split('|')[1] for k in fp})}))
