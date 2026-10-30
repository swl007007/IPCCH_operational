"""Task 10-29: IPCCH WFP_Price keep/refresh under the Supervisor contract correction (research HDX processed series,
declared-interval replacement, R27-R29/R59 semantics; never the WFP Trend country converter)."""

import math

import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import retained, wfp
from cloud.ipcch.stores import StoreError, StoreRoot, VersionedTable

ROSTER = ["1", "2", "3"]
REF = {"uri": "gs://ops/wfp_price_monthly_2026-10.csv", "generation": "7", "sha256": "ab" * 32}


def seeded(tmp_path):
    store, root = LocalObjectStore(tmp_path), StoreRoot("real", "gs://b/ipcch-v2/real")
    t = VersionedTable(store, root, wfp.HISTORY_TABLE)
    rows = [{"admin_code": a, "month": m, "value": v, "method_id": "delivered:interim"}
            for m, v in (("2026-05", 101.0), ("2026-06", 102.0), ("2026-07", 103.0)) for a in ROSTER]
    t.commit(pd.DataFrame(rows), {"action": "initialise"}, expected_generation="0")
    return store, root, t


def test_keep_leaves_history_and_reports_coverage(tmp_path):
    store, root, t = seeded(tmp_path)
    head = t.head()
    rep = wfp.apply(store, root, {"action": "keep"}, roster=ROSTER)
    assert rep["coverage_end"] == "2026-07" and "nearest market" in rep["method"] and t.head() == head


def test_refresh_replaces_exactly_the_declared_interval(tmp_path):
    store, root, t = seeded(tmp_path)
    text = "admin_code,month,value\n1,2026-07,110.5\n2,2026-07,\n1,2026-08,111.0\n3,2026-08,95.25\n"
    rep = wfp.apply(store, root, {"action": "refresh", "file": REF, "start": "2026-07", "end": "2026-08"},
                    roster=ROSTER, text=text)
    assert rep["coverage_end"] == "2026-08" and rep["replaced_rows"] == 3 and rep["rows"] == 4
    f = retained.read_series(t)[0].set_index(["admin_code", "month"])["value"]
    assert f[("1", "2026-06")] == 102.0                                          # outside the interval untouched
    assert f[("1", "2026-07")] == 110.5 and math.isnan(f[("2", "2026-07")])     # replaced; blank stays missing
    assert ("3", "2026-07") not in f.index and ("2", "2026-08") not in f.index   # no carry-forward / fill
    assert set(retained.read_series(t)[0].query("month >= '2026-07'")["method_id"]) == {f"refresh:{REF['sha256'][:16]}"}


@pytest.mark.parametrize("text,match", [
    ("admin_code,month,value\n1,2026-09,100\n", "outside the declared interval"),
    ("admin_code,month,value\n1315,2026-08,100\n", "unknown modeled-area"),
    ("admin_code,month,value\n1,2026-08,abc\n", "unparseable value 'abc' for area 1"),
    ("admin_code,month,value\n1,2026-08,inf\n", "infinite value for area 1"),
    ("admin_code,month,value\n1,2026-08,1\n1,2026-08,2\n", "duplicate keys"),
    ("ISO3,period,WFP_Price\nSOM,2026-08,101\n", "exactly admin_code, month, value"),
])
def test_invalid_refresh_leaves_history_intact(tmp_path, text, match):
    store, root, t = seeded(tmp_path)
    head = t.head()
    with pytest.raises(StoreError, match=match):
        wfp.apply(store, root, {"action": "refresh", "file": REF, "start": "2026-08", "end": "2026-08"}, roster=ROSTER,
                  text=text)
    assert t.head() == head                                                      # R27: failed refresh writes nothing
