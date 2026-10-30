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


def build_bundle(base):
    """Fixture bundle under ``base`` (the declared fixture root): write_bundle + population, ACLED tables, geometry."""
    import geopandas
    from shapely.geometry import box

    bundle, man = write_bundle(base, inputs(), fixture=True)
    man["files"].pop("fixed/geometry/g.shp")
    (bundle / "fixed" / "geometry" / "g.shp").unlink()
    for rel, text in {**ACLED_TABLES, "fixed/population_reference.csv": POPULATION}.items():
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


def acled_export(origin_months):
    """Weekly regional-aggregate rows (both regions) for every Saturday week overlapping the given months."""
    weeks = pd.date_range("2025-12-27", "2027-01-30", freq="7D")
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

    def put(self, name, text):
        data = text.encode()
        ref = {"uri": f"gs://ops-smoke/inputs/{name}", "generation": str(100 + len(self.objects)),
               "sha256": hashlib.sha256(data).hexdigest()}
        self.objects[(ref["uri"], ref["generation"])] = data
        return ref

    def read(self, ref):
        data = self.objects[(ref["uri"], ref["generation"])]
        assert hashlib.sha256(data).hexdigest() == ref["sha256"]
        return data


def smoke_request(refs, execution_month="2027-03", run_id="smoke-run-1", inference=False, batch=None):
    acled = {"action": "refresh", "file": refs.put("acled.csv", acled_export(None)), "start": "2025-12-27",
             "end": "2027-02-05", "regions": ["R1", "R2"]}
    keep = {"action": "keep"}
    ipcch = {"model_combination": {"combination_id": "ipcch-test-scoring", "package_manifest": refs.put("pm", "x")},
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
    return v2.validate_request_v2(data, request_uri="gs://ops-smoke/requests/smoke-run-1/run_manifest.json",
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
