"""Task 10-31: pure acceptance checks (no I/O). Tested by test_incremental_checks.py under the guard.

* fingerprint(frame): sha256 per (region, week) over the canonical sorted WEEKLY_COLUMNS rows.
* compare_acled(pre, post, start, end, regions, expected_interval): every pre (region, week) outside the replaced
  interval x regions is byte-identical after; no new keys outside; the interval keys equal EXACTLY the fingerprint of
  the pinned export's parse_export rows (values, not only counts).
* kept_unchanged(pre_tables, post_tables, names): HEAD generation/version/content sha unchanged per kept table.
* lineage(task_records, production, post_tables, retained_inputs, table_bases, origin, run_id): records and production
  bound to run_id, no duplicate task/destination; receipt tables == jobs; task record (completed, task_id, asset) ->
  receipt (same task_id + asset) -> HEAD.record.produced_tables (month == O, published, IDs from this run) -> batch
  retained_inputs (version, sha256, HEAD generation) == post-run HEAD. Unconsumed assets need an explicit unavailable
  disposition; ``all_assets_consumed`` reports the strongest (exact set) outcome.
"""

import hashlib

WEEKLY_COLUMNS = ("week", "region", "country", "admin1", "type", "events", "fatalities", "exposure")


def fingerprint(frame):
    cols = list(WEEKLY_COLUMNS)
    canon = frame[cols].astype(str).sort_values(cols, kind="mergesort")
    return {f"{r}|{w}": {"rows": int(len(g)), "sha256": hashlib.sha256(g.to_csv(index=False).encode()).hexdigest()}
            for (r, w), g in canon.groupby(["region", "week"], sort=True)}


def _inside(key, start, end, regions):
    region, week = key.split("|", 1)
    return start <= week <= end and region in regions


def compare_acled(pre, post, start, end, regions, expected_interval):
    """``expected_interval``: fingerprint of the pinned export's parse_export rows (CSV round-trip), interval keys only."""
    regions = set(regions)
    inside = lambda k: _inside(k, start, end, regions)
    lost_or_changed_outside = sorted(k for k, v in pre.items() if not inside(k) and post.get(k) != v)
    new_outside = sorted(k for k in post if k not in pre and not inside(k))
    got = {k: v for k, v in post.items() if inside(k)}
    want = {k: v for k, v in expected_interval.items() if inside(k)}
    checks = {"outside_preserved": not lost_or_changed_outside, "no_new_keys_outside": not new_outside,
              "expected_covers_only_interval": len(want) == len(expected_interval),
              "interval_equals_pinned_export": got == want}
    return {"checks": checks, "passed": all(checks.values()), "interval_keys": sorted(got),
            "interval_rows": sum(v["rows"] for v in got.values()),
            "interval_mismatch": sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))[:20],
            "lost_or_changed_outside": lost_or_changed_outside[:20], "new_outside": new_outside[:20]}


def kept_unchanged(pre_tables, post_tables, names):
    out = {}
    for n in names:
        a, b = pre_tables.get(n), post_tables.get(n)
        out[n] = bool(a and b and (a["head_generation"], a["version"], a["content_sha256"]) ==
                      (b["head_generation"], b["version"], b["content_sha256"]))
    return out


KEYS = ("AQUA", "TERRA", "CHIRPS", "PERSIANN", "ERA5LAND")


def job_key(table_name):
    """Source key of a producer table name (VI sensor / precipitation source); ET0/PATCH32 have none."""
    hit = [k.lower() for k in KEYS if f"_{k}_" in table_name]
    return hit[0] if hit else None


def lineage(task_records, production, post_tables, retained_inputs, table_bases, origin, run_id):
    """Incremental join of THIS run (see module docstring). An unconsumed produced asset passes only with an explicitly
    evidenced unavailable disposition (its source listed in a consuming table record's ``unavailable``); every demanded
    table base must append O with a published source fed by this run's assets."""
    ids = [(r.get("asset_id"), r.get("task_id")) for r in task_records]
    completed = {r["asset_id"]: r for r in task_records if r.get("state") == "completed" and r.get("task_id")}
    receipts = production.get("receipts") or []
    jobs = list(production.get("jobs") or [])
    demand = production.get("demand") or {}
    receipt_joined = {r["asset_id"]: (r["asset_id"] in completed and completed[r["asset_id"]]["task_id"] == r.get("task_id")
                                      and r.get("state") == "completed" and int(r.get("rows") or 0) > 0) for r in receipts}
    consumed, saved, unavailable = {}, {}, {}
    for table in table_bases:
        rec = (post_tables.get(table) or {}).get("record") or {}
        consumed[table] = sorted({i for v in (rec.get("produced_tables") or {}).values() for i in v})
        unavailable[table] = dict(rec.get("unavailable") or {})
        saved[table] = {"month_is_origin": rec.get("month") == origin, "published": list(rec.get("published") or []),
                        "ids_from_this_run": bool(consumed[table]) and set(consumed[table]) <= set(completed)}
    used = {i for v in consumed.values() for i in v}
    receipt_table = {r["asset_id"]: r.get("table") for r in receipts}
    dispositions = {}
    for asset in sorted(set(completed) - used):
        key = job_key(receipt_table.get(asset) or "")
        evidence = {t: u[key] for t, u in unavailable.items() if key and key in u}
        dispositions[asset] = {"source_key": key, "unavailable_evidence": evidence, "explained": bool(evidence)}
    batch_link = {}
    for table in table_bases:
        head, pinned = post_tables.get(table) or {}, retained_inputs.get(table) or {}
        batch_link[table] = bool(head) and str(pinned.get("generation")) == str(head.get("head_generation")) and \
            pinned.get("version") == head.get("version") and pinned.get("sha256") == head.get("content_sha256")
    checks = {"demand_nonempty": any(v for part in demand.values() for v in part.values()),
              "jobs_nonempty": bool(jobs),
              "bound_to_run": production.get("run_id") == run_id and bool(task_records)
              and all(r.get("run_id") == run_id for r in task_records),
              "no_duplicate_task_or_destination": len({a for a, _ in ids}) == len(ids) and len({t for _, t in ids}) == len(ids),
              "receipt_tables_equal_jobs": sorted(r.get("table") for r in receipts) == sorted(jobs),
              "receipts_join_completed_task_records": bool(receipt_joined) and all(receipt_joined.values())
              and set(receipt_joined) == set(completed),
              "each_table_base_appends_O_from_this_run": all(v["month_is_origin"] and v["published"] and v["ids_from_this_run"]
                                                             for v in saved.values()),
              "unconsumed_assets_explained": all(d["explained"] for d in dispositions.values()),
              "batch_retained_inputs_equal_post_heads": all(batch_link.values())}
    return {"checks": checks, "passed": all(checks.values()), "all_assets_consumed": used == set(completed) and bool(used),
            "receipt_joined": receipt_joined, "consumed": consumed, "saved": saved, "unavailable": unavailable,
            "unconsumed_dispositions": dispositions, "batch_link": batch_link, "completed_assets": sorted(completed)}
