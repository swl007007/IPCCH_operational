"""Task 10-31 CP0: READ-ONLY demand preflight against the live real retained store (GCS reads only; no EE call, no
TableProducer.run, no export, no write).

Computes, with the product's own planning helpers and the same inputs generation uses:
* O from the given M (default: the current UTC month), and the season windows exactly as Generation._season_windows
  derives them (shim object: store/root/report only);
* per climate base: monthly months_to_update(saved, O) and seasonal pending_seasons(table, windows, O);
* table producer: demand(tables, O, windows) and required_tables(need, TableRefs(year_chunks(O.year))) -> job names,
  kinds and years; destination pattern {producer_asset_root}{job.name}__{output_version(run_id, M)};
* GPP candidates (gpp.update_gpp rule) and nightlight candidates (nightlight rule).

usage: demand_preflight.py OUT_JSON [M]
"""

import json
import sys
from datetime import datetime, timezone

import pandas as pd
from google.cloud import storage

from cloud.common.object_store import GCSObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_tables as ct
from cloud.ipcch import entrypoint_v2 as ep
from cloud.ipcch import gpp, nightlight, retained
from cloud.ipcch import initial
from cloud.ipcch import table_producers as tp
from cloud.ipcch.generation import Generation
from cloud.ipcch.stores import StoreRoot, VersionedTable
from cloud.batch import remote_sources as rs

CONFIG = "deploy/ipcch_v2_deployment.food-crisis-test.json"


class Shim:                                   # the attributes Generation._season_windows reads
    def __init__(self, store, root):
        self.store, self.root, self.report = store, root, {}


def add_months(m, k):
    p = pd.Period(m, "M") + k
    return f"{p.year:04d}-{p.month:02d}"


def main(out, M=None):
    M = M or datetime.now(timezone.utc).strftime("%Y-%m")
    O = add_months(M, -2)
    cfg = ep.load_config(CONFIG)
    store = GCSObjectStore(storage.Client())
    root = StoreRoot("real", cfg["store_roots"]["real"])
    roster = [str(a) for a in initial._read(store, root, "fixed/roster.csv")["admin_code"]]
    shim = Shim(store, root)
    windows = Generation._season_windows(shim, roster, O)
    tables = lambda base, temporal: VersionedTable(store, root, cl.table_name(base, temporal))
    body = {"M": M, "O": O, "targets": [add_months(M, k) for k in (0, 6, 12)], "roster": len(roster),
            "season_windows": {"rows": int(len(windows)), "through": int(windows["season_year"].max()),
                               "extension": shim.report.get("season_windows_extension")},
            "climate": {"monthly": {}, "seasonal": {}}}
    for base in cl.BASES:
        frame, _ = cl.read_monthly(tables(base, cl.MONTHLY))
        months = cl.months_to_update(set(frame["month"]), O)
        body["climate"]["monthly"][base] = {"saved_last": max(frame["month"]), "to_update": months,
                                           "sources": list(cl.SOURCES[base])}
        del frame
        pend = cl.pending_seasons(tables(base, cl.SEASONAL), windows, O)
        body["climate"]["seasonal"][base] = [
            {"season_year": int(y), "season": s, "areas": int(len(g))}
            for (y, s), g in pend.groupby(["season_year", "season"], sort=True)]
        del pend
    need = tp.demand(tables, origin=O, windows=windows)
    refs = ct.TableRefs(year_chunks=ct.year_chunks(int(O[:4])))
    jobs = tp.required_tables(need, refs)
    body["table_producer"] = {
        "demand": need, "year_chunks": [list(c) for c in refs.year_chunks],
        "jobs": [{"name": j.name, "kind": j.kind, "key": getattr(j, "key", None), "years": list(j.years)} for j in jobs],
        "job_count": len(jobs), "producer_asset_root": cfg["producer_asset_root"],
        "destination_pattern": cfg["producer_asset_root"] + "<job.name>__M" + M.replace("-", "") + "_<run_id>_<sha256(run_id)[:8]>",
        "output_version_example": tp.output_version("ipcch-real-0000000000000000", M)}
    # GPP (gpp.update_gpp candidate rule) and nightlight (nightlight rule)
    gh = VersionedTable(store, root, gpp.HISTORY_TABLE)
    gframe, _ = retained.read_series(gh)
    ledger = VersionedTable(store, root, gpp.LEDGER_TABLE)
    status = retained.latest_gpp_status(ledger)
    unpublished = sorted(m for m, s in status.items() if s == "unpublished")
    adapter = set(gframe.loc[gframe["method_id"] == gpp.METHOD_ID, "month"]) if "method_id" in gframe else set()
    unledgered = sorted(m for m in adapter if status.get(m) != "published")
    gcands = sorted(set(rs.months_between(max(gframe["month"]), O)) | {m for m in unpublished if m <= O} | set(unledgered))
    body["gpp"] = {"history_last_month": max(gframe["month"]), "ledger_status": status, "candidates": gcands,
                   "url_template": rs.SOURCE_CONTRACTS[gpp.FAMILY].export["url"]}
    del gframe
    nh = VersionedTable(store, root, nightlight.HISTORY_TABLE)
    nframe, _ = retained.read_series(nh)
    body["nightlight"] = {"history_last_month": max(nframe["month"]),
                          "candidates": rs.months_between(max(nframe["month"]), O)}
    with open(out, "x") as f:
        json.dump(body, f, indent=1, sort_keys=True, default=str)
    print(json.dumps({"M": M, "O": O, "monthly_to_update": {b: v["to_update"] for b, v in body["climate"]["monthly"].items()},
                      "seasonal_pending": {b: len(v) for b, v in body["climate"]["seasonal"].items()},
                      "jobs": [j["name"] for j in body["table_producer"]["jobs"]],
                      "gpp_candidates": gcands, "nightlight_candidates": body["nightlight"]["candidates"]}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
