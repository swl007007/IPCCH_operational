"""Task 10-29: run-level climate update across the 13 bases (routing, per-base persistence, blocking after saves)."""

import pandas as pd
import pytest

from cloud.common.object_store import LocalObjectStore
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_run as cr
from cloud.ipcch.stores import StoreRoot, VersionedTable

ROSTER = ["1", "2"]
WINDOWS = pd.DataFrame({"admin_code": ROSTER, "season_year": [2026, 2026], "season": ["s1", "s1"],
                        "gs_start_date": ["2026-03-01", "2026-03-01"], "gs_end_date_exclusive": ["2026-07-01", "2026-09-01"]})


def tables(tmp_path):
    store = LocalObjectStore(tmp_path)
    cache = {}

    def get(base, temporal):
        if (base, temporal) not in cache:
            t = VersionedTable(store, StoreRoot("real", "gs://b/ipcch-v2/real"), cl.table_name(base, temporal))
            if temporal == cl.MONTHLY:
                t.commit(pd.DataFrame([{"admin_code": a, "month": "2026-07", "value": 0.0, "n_sources": 1, "ens_sd": float("nan"),
                                        "method_id": "accepted"} for a in ROSTER]), {"action": "initialise"}, expected_generation="0")
            cache[(base, temporal)] = t
        return cache[(base, temporal)]
    return get


def providers(missing_base=None):
    def monthly(base):
        def fetch(source, month):
            if base == missing_base:
                return cl.SourceOutcome(source, "unavailable", detail="not published")
            return cl.SourceOutcome(source, "published", pd.DataFrame({"admin_code": ROSTER, "value": [1.0, 2.0]}))
        return fetch

    def seasonal(base):
        return lambda source, year, season, w: cl.SourceOutcome(
            source, "published", pd.DataFrame({"admin_code": list(w["admin_code"]), "value": [5.0] * len(w)}))
    return cr.ClimateProviders(monthly, seasonal)


def test_full_run_saves_every_base(tmp_path):
    get = tables(tmp_path)
    rep = cr.update_all(get, origin="2026-08", roster=ROSTER, windows=WINDOWS, providers=providers())
    assert all(rep["monthly"][b]["saved"] == ["2026-08"] for b in cl.BASES)
    assert all(rep["seasonal"][b]["saved"] == ["2026-s1"] for b in cl.BASES)
    frame, _ = cl.read_seasonal(get("spei03", cl.SEASONAL))
    assert frame["admin_code"].tolist() == ["1", "2"]                   # both windows completed by the end of 2026-08
    assert rep["methods"]["spei03"]["gs"]["spei_fit"] == cl.SPEI_FIT_SEASONAL


def test_origin_without_source_blocks_after_earlier_bases_saved(tmp_path):
    get = tables(tmp_path)
    with pytest.raises(cl.ClimateSourceMissing, match="climate run report"):
        cr.update_all(get, origin="2026-08", roster=ROSTER, windows=WINDOWS, providers=providers(missing_base="sm_z"))
    order = list(cl.BASES)
    for b in order[:order.index("sm_z")]:
        assert "2026-08" in set(cl.read_monthly(get(b, cl.MONTHLY))[0]["month"])   # kept (R41)
    assert "2026-08" not in set(cl.read_monthly(get("sm_z", cl.MONTHLY))[0]["month"])


def test_default_routing():
    class P:
        def __init__(self, name):
            self.name = name

        def bound(self, base):
            return (self.name, base)

        def bound_season(self, base=None):
            return (self.name, base)

        fetch = "vegetation-monthly"
    r = cr.default_providers(P("ee"), P("ee-gs"), P("veg"), P("veg-gs"), P("drought"), P("drought-gs"))
    assert r.monthly("prcp_z") == ("ee", "prcp_z") and r.monthly("spei03") == ("drought", "spei03")
    assert r.monthly("evi_anom") == "vegetation-monthly" and r.seasonal("evi_anom") == ("veg-gs", None)
    assert r.seasonal("spi03") == ("drought-gs", "spi03") and r.seasonal("sm_z") == ("ee-gs", "sm_z")
