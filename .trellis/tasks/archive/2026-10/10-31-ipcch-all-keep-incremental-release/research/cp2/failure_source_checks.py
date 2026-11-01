"""Task 10-31 failure reconciliation (pure comparison of saved evidence files; no I/O beyond reading them):
store HEAD changes pre-CP1 -> post-failure, ten keeps unchanged, ACLED exact interval content + preservation + pin."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import incremental_checks as ic  # noqa: E402
from lineage_readback import ACLED, KEPT  # noqa: E402

pre = json.load(open(sys.argv[1]))["tables"]; post = json.load(open(sys.argv[2]))["tables"]
a_pre, a_post, a_exp = (json.load(open(p)) for p in sys.argv[3:6])
changed = {k: {"pre": (pre.get(k) or {}).get("version"), "post": post[k]["version"], "post_record_action": (post[k].get("record") or {}).get("action")}
           for k in post if (pre.get(k) or {}).get("head_generation") != post[k]["head_generation"]}
kept = ic.kept_unchanged(pre, post, KEPT)
acl = ic.compare_acled(a_pre["region_week"], a_post["region_week"], ACLED["start"], ACLED["end"], ACLED["regions"], a_exp["region_week"])
last = a_post.get("last_refresh") or {}
pin = {"source_sha256": (last.get("source") or {}).get("sha256") == ACLED["source_sha256"] == a_exp["source_sha256"],
       "interval": (last.get("start"), last.get("end")) == (ACLED["start"], ACLED["end"]),
       "regions": sorted(last.get("regions") or []) == sorted(ACLED["regions"]),
       "coverage_record_appended": a_post["coverage_records"][:-1] == a_pre["coverage_records"] and a_post["coverage_records"][-1] == last}
body = {"head_changes": changed, "tables_pre": len(pre), "tables_post": len(post), "new_tables": sorted(set(post) - set(pre)),
        "kept": kept, "kept_ten_unchanged": all(kept.values()) and len(kept) == 10, "acled": acl, "acled_pin": pin,
        "acled_last_refresh": last, "acled_rows": {"pre": a_pre["rows"], "post": a_post["rows"]}}
json.dump(body, open(sys.argv[6], "x"), indent=1, sort_keys=True, default=str)
print(json.dumps({"head_changes": changed, "new_tables": body["new_tables"], "kept_ten_unchanged": body["kept_ten_unchanged"],
                  "acled_checks": acl["checks"], "acled_pin": pin, "interval_rows": acl["interval_rows"], "rows": body["acled_rows"]}, indent=1))
