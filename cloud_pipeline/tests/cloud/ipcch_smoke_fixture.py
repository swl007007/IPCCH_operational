"""Task 10-29 smoke fixture: a complete IPCCH fixture bundle (fixture: true) for a small roster, fake providers and a
validated v2 smoke request - local only, no cloud, no real asset (R14, R16, R36, R48)."""

import hashlib
import io
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from cloud.ipcch import acled as ac
from cloud.ipcch import climate as cl
from cloud.ipcch import climate_run
from cloud.orchestrator import delivery_request_v2 as v2
from tests.cloud.test_ipcch_assembly import ROSTER, inputs
from tests.cloud.test_ipcch_initial import write_bundle

EXTRA = "1315"                                    # declared fixed-source exception carried by the fixture geometry
ACLED_TABLES = {
    "fixed/acled/acled_admin1_to_poly.csv": "acled_country,admin1,poly_ids\nAland,A1,pA1\nAland,A2,pA2\nBland,B1,pB1\n",
    "fixed/acled/admin1_population.csv": "poly_id,iso3,pop_denominator\npA1,AAA,1000\npA2,AAA,2000\npB1,BBB,500\n",
    "fixed/acled/admin1_neighbours.csv": "poly_id,neighbour_poly_id\npA1,pA2\npA2,pA1\npA2,pB1\npB1,pA2\n",
    "fixed/acled/coverage_start.csv": ("iso3,layer_group,determined,effective_start_ym,in_f1f2_regions,acled_region\n"
                                       "AAA,,True,2010-01,True,R1\nBBB,,True,2010-01,True,R2\n"),
    "fixed/acled/unit_admin1_weights.csv": "admin_code,poly_id,weight\n11,pA1,1.0\n12,pA2,1.0\n13,pB1,1.0\n",
    "fixed/acled/unit_iso3.csv": "admin_code,iso3\n11,AAA\n12,AAA\n13,BBB\n",
}
POPULATION = "admin_code,reference_period,population_estimate\n11,2026-04,1000.0\n12,2026-04,2000.0\n13,2025-01,300.0\n"
# delivered calendar reproducing the fixture windows (s1 03-01..06-30, s2 08-01..10-31, no cross-year)
CALENDAR = ("admin_code,s1_calendar_valid,s1_cross_year,s1_sos_month,s1_sos_day,s1_eos_month,s1_eos_day,"
            "s2_calendar_valid,s2_cross_year,s2_sos_month,s2_sos_day,s2_eos_month,s2_eos_day\n"
            + "".join(f"{a},1,0,3,1,6,30,1,0,8,1,10,31\n" for a in (11, 12, 13)))
DELIVERED_THROUGH = 2026
# fixture country reference (the existing census columns), never the real operational asset (R48)
COUNTRY_REFERENCE = ("ISO3,country,country_en,referenced_population,population_reference_year,population_reference_date,"
                     "population_measure,population_source,population_vintage,population_source_url,census_genc_codes\n"
                     "AAA,Aland,Aland,3000,2026,2026-01-01,total,fixture,fixture-v1,https://example.invalid/aaa,AA\n"
                     "BBB,Bland,Bland,300,2026,2026-01-01,total,fixture,fixture-v1,https://example.invalid/bbb,BB\n")                         # like the accepted handoff: windows/seasons end with 2026


def build_bundle(base):
    """Fixture bundle under ``base`` (the declared fixture root): write_bundle + population, ACLED tables, geometry."""
    import geopandas
    from shapely.geometry import box

    bundle, man = write_bundle(base, inputs(), fixture=True)
    for rel in [r for r in man["files"] if r == "fixed/season_windows.csv" or r.startswith("history/climate_gs_")]:
        p = bundle / rel                          # truncate at the delivered horizon: no pre-seeded future seasons
        f = pd.read_csv(p, dtype=str, keep_default_na=False)
        f[f["season_year"].astype(int) <= DELIVERED_THROUGH].to_csv(p, index=False, lineterminator="\n")
        man["files"][rel] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    ident = bundle / "fixed/area_identity.csv"                # delivery join key: fixture iso3_reference (R32)
    f = pd.read_csv(ident, dtype=str, keep_default_na=False)
    f["iso3_reference"] = f["admin_code"].map({"11": "AAA", "12": "AAA", "13": "BBB"})
    f.to_csv(ident, index=False, lineterminator="\n")
    man["files"]["fixed/area_identity.csv"] = {"sha256": hashlib.sha256(ident.read_bytes()).hexdigest()}
    man["files"].pop("fixed/geometry/g.shp")
    (bundle / "fixed" / "geometry" / "g.shp").unlink()
    for rel, text in {**ACLED_TABLES, "fixed/population_reference.csv": POPULATION,
                      "fixed/season_calendar.csv": CALENDAR}.items():
        p = bundle / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        man["files"][rel] = {"sha256": hashlib.sha256(text.encode()).hexdigest()}
    codes = [str(a) for a in ROSTER] + [EXTRA]
    gdf = geopandas.GeoDataFrame({"admin_code": codes}, geometry=[box(i, 0, i + 1, 1) for i in range(len(codes))],
                                 crs="EPSG:4326")
    gdf.to_file(bundle / "fixed" / "geometry" / "g.shp")
    for p in (bundle / "fixed" / "geometry").iterdir():
        man["files"][f"fixed/geometry/{p.name}"] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    man["roster_policy"] = {"fixed/geometry/g.dbf": {"out_of_roster_admins": [int(EXTRA)],
                                                     "policy": "byte_preserved_not_filtered"}}
    (bundle / "handoff_manifest.json").write_text(json.dumps(man))
    return bundle, man


def acled_interval(origin):
    """Saturday on/before the first day of O-12 .. Friday on/after the last day of O (the R44 first-refresh lookback)."""
    o = pd.Period(origin, "M")
    first, last = (o - 12).start_time, o.end_time.normalize()
    start = first - pd.Timedelta(days=(first.weekday() - 5) % 7)
    end = last + pd.Timedelta(days=(4 - last.weekday()) % 7)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def acled_export(start, end):
    """Weekly regional-aggregate rows (both regions) for every Saturday week in [start, end] (the request puts it with a
    UTF-8 BOM, as the ACLED Data Export Tool writes it)."""
    weeks = pd.date_range(start, pd.Timestamp(end) - pd.Timedelta(days=6), freq="7D")
    rows = []
    for i, w in enumerate(weeks):
        for region, country, admin1 in (("R1", "Aland", "A1"), ("R1", "Aland", "A2"), ("R2", "Bland", "B1")):
            rows.append({"week": w.strftime("%Y-%m-%d"), "region": region, "country": country, "admin1": admin1,
                         "event_type": "Battles", "sub_event_type": "Armed clash", "events": str(i % 3),
                         "fatalities": str(i % 2), "population_exposure": "10", "disorder_type": "Political violence",
                         "centroid_latitude": "0", "centroid_longitude": "0"})
    return pd.DataFrame(rows)[list(ac.EXPORT_COLUMNS)].to_csv(index=False)


class Refs:
    """Immutable refresh files by {uri, generation, sha256} (exact-generation read + sha check)."""

    def __init__(self):
        self.objects = {}

    def put(self, name, text, bom=False):
        data = (b"\xef\xbb\xbf" if bom else b"") + text.encode()
        ref = {"uri": f"gs://ops-smoke/inputs/{name}", "generation": str(100 + len(self.objects)),
               "sha256": hashlib.sha256(data).hexdigest()}
        self.objects[(ref["uri"], ref["generation"])] = data
        return ref

    def read(self, ref):
        data = self.objects[(ref["uri"], ref["generation"])]
        assert hashlib.sha256(data).hexdigest() == ref["sha256"]
        return data


def smoke_request(refs, envelope_path, execution_month="2027-03", run_id="smoke-run-1", inference=False,
                  combination_id="ipcch-test-scoring"):
    o = str(pd.Period(execution_month, "M") - 2)
    start, end = acled_interval(o)
    acled = {"action": "refresh", "file": refs.put("acled.csv", acled_export(start, end), bom=True), "start": start, "end": end,
             "regions": ["R1", "R2"]}
    keep = {"action": "keep"}
    envelope = refs.put("envelope.json", open(envelope_path, encoding="utf-8").read())
    ipcch = {"model_combination": {"combination_id": combination_id, "envelope": envelope},
             **({"country_reference": refs.put("country_reference.csv", COUNTRY_REFERENCE)} if inference else {}),
             "acled": acled, "research_inputs": {f: keep for f in v2.RESEARCH_FAMILIES}, "history_snapshot": keep,
             "wfp": keep}
    data = {"schema_version": v2.SCHEMA_VERSION, "run_id": run_id, "mode": "smoke", "execution_month": execution_month,
            "operations": {"ipcch_generation": True, "ipcch_inference": inference, "fewsnet_generation": False,
                           "fewsnet_inference": False},
            "ipcch": ipcch, "fewsnet": None, "publication": "candidate",
            "runtime": {"image_uri": "us-central1-docker.pkg.dev/p/r/img@sha256:" + "a" * 64,
                        "environment_manifest": refs.put("env", "e")},
            "release": {"namespace": "smoke", "expected_pointer_generation": "0"},
            "operator": "ops@example.org", "prepared_at": "2026-10-30T05:00:00Z"}
    return v2.validate_request_v2(data, request_uri=f"gs://ops-smoke/requests/{run_id}/run_manifest.json",
                                  request_generation="1", now_utc=datetime(2026, 10, 30, 6, tzinfo=timezone.utc),
                                  production_namespace="prod", smoke_namespace="smoke", current_ipcch_execution_month=None)


def climate_providers(codes=None):
    codes = codes or [str(a) for a in ROSTER] + [EXTRA]

    def monthly(base):
        return lambda source, month: cl.SourceOutcome(source, "published", pd.DataFrame(
            {"admin_code": codes, "value": np.linspace(0.1, 0.4, len(codes))}))

    def seasonal(base):
        return lambda source, year, season, win: cl.SourceOutcome(source, "published", pd.DataFrame(
            {"admin_code": list(win["admin_code"].astype(str)), "value": 0.5}))
    return climate_run.ClimateProviders(monthly, seasonal)


class NoGpp:
    def _head(self, url):
        return 404


class NoNightlight:
    def published_months(self, family, *, start_month, end_month):
        return {}

    def start_exports(self, family, months, *, prepare_id):
        pass
