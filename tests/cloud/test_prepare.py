import gzip
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from cloud.batch import remote_sources as rs  # noqa: E402
from cloud.common.object_store import GenerationConflict, ObjectMetadata  # noqa: E402
from cloud.orchestrator import prepare  # noqa: E402
from cloud.orchestrator.batch_client import BatchJobConfig, build_batch_job_spec  # noqa: E402
from cloud.orchestrator.delivery_manifest import DeliveryManifestError, ReferenceIdentityError  # noqa: E402


ROOT = "gs://prep-bucket"
REQUEST_SHA = "e" * 64
GRID = np.arange(16, dtype="float32").reshape(4, 4)


class FakeNotFound(Exception):
    pass


class FakeGcs:
    """Versioned fake: ObjectStore writes, exact-generation reads and a GCS-client surface."""

    def __init__(self):
        self.versions: dict[str, list[bytes]] = {}

    def _write(self, uri, data, if_generation_match):
        current = len(self.versions.get(uri, []))
        if if_generation_match is not None and int(if_generation_match) != current:
            raise GenerationConflict(f"{uri}: expected {if_generation_match}, current {current}")
        self.versions.setdefault(uri, []).append(bytes(data))
        return ObjectMetadata(uri=uri, generation=str(current + 1))

    def write_text(self, uri, content, *, if_generation_match=None):
        return self._write(uri, content.encode("utf-8"), if_generation_match)

    def read_text(self, uri):
        return self.versions[uri][-1].decode("utf-8")

    def get_metadata(self, uri):
        return ObjectMetadata(uri, str(len(self.versions[uri]))) if uri in self.versions else None

    def list(self, prefix_uri):
        return sorted(uri for uri in self.versions if uri.startswith(prefix_uri))

    def read_bytes(self, uri, generation):
        versions = self.versions.get(uri, [])
        index = int(generation) - 1
        return versions[index] if 0 <= index < len(versions) else None

    def bucket(self, name):
        return FakeBucket(self, name)

    def ref(self, uri, data: bytes):
        metadata = self._write(uri, data, None)
        return {"uri": uri, "generation": metadata.generation, "sha256": hashlib.sha256(data).hexdigest()}

    def json(self, uri):
        return json.loads(self.read_text(uri))


class FakeBucket:
    def __init__(self, gcs, name):
        self.gcs, self.name = gcs, name

    def blob(self, name, generation=None):
        return FakeBlob(self.gcs, f"gs://{self.name}/{name}", generation)


class FakeBlob:
    def __init__(self, gcs, uri, generation):
        self.gcs, self.uri, self.generation = gcs, uri, generation

    def reload(self):
        if self.uri not in self.gcs.versions:
            raise FakeNotFound(self.uri)
        self.generation = len(self.gcs.versions[self.uri])

    def download_as_bytes(self, if_generation_match=None):
        generation = self.generation if self.generation is not None else len(self.gcs.versions.get(self.uri, []))
        data = self.gcs.read_bytes(self.uri, generation)
        if data is None:
            raise FakeNotFound(self.uri)
        return data

    def upload_from_string(self, data, if_generation_match=None):
        self.generation = int(self.gcs._write(self.uri, data, if_generation_match).generation)


def _tif_bytes(bands, *, descriptions=None, origin=(0.0, 4.0)):
    array = np.asarray(bands, dtype="float32")
    array = array[None] if array.ndim == 2 else array
    memfile = rasterio.io.MemoryFile()
    with memfile.open(driver="GTiff", width=array.shape[2], height=array.shape[1], count=array.shape[0],
                      dtype="float32", crs="EPSG:4326", transform=from_origin(origin[0], origin[1], 1, 1),
                      nodata=-9999.0) as dataset:
        dataset.write(array)
        for index, description in enumerate(descriptions or [], start=1):
            dataset.set_band_description(index, description)
    return memfile.read()


def _square(x0, y0, size=2):
    return {"type": "Polygon", "coordinates": [[(x0, y0), (x0 + size, y0), (x0 + size, y0 + size),
                                                (x0, y0 + size), (x0, y0)]]}


ROSTERS = {"fewsnet": {"0": _square(0, 2), "00": _square(2, 0)},
           "ipcch": {"1": _square(0, 0), "10": _square(2, 2), "7": _square(40, 40, 1)}}


def _stat_columns(family):
    contract = rs.SOURCE_CONTRACTS[family]
    return [f"{band}__{reducer}" for band in contract.bands for reducer in contract.reducers]


def _history_csv(system, family, through, start="2026-05"):
    months = rs.months_between(start, through)
    rows = [{"admin_code": key, "month": month, **{column: 1.0 for column in _stat_columns(family)}}
            for key in ROSTERS[system] for month in [start, *months]]
    return pd.DataFrame(rows, columns=["admin_code", "month", *_stat_columns(family)]).to_csv(index=False).encode()


HISTORY_THROUGH = {
    "fewsnet": {"evi": "2026-07", "fldas": "2026-07", "gosif_mean": "2026-07", "gosif_sd": "2026-07", "viirs": "2026-09"},
    "ipcch": {"evi": "2026-07", "fldas": "2026-07", "gosif_mean": "2026-07", "gosif_sd": "2026-08", "viirs": "2026-09"},
}


def _request(gcs, prepare_id="prep-202610-a"):
    systems = {}
    for system, polygons in ROSTERS.items():
        geometry = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"admin_code": key}, "geometry": shape}
            for key, shape in polygons.items()]}
        roster = pd.DataFrame({"admin_code": list(polygons)}).to_csv(index=False).encode()
        systems[system] = {
            "geometry": gcs.ref(f"gs://assets/{system}/geometry.geojson", json.dumps(geometry).encode()),
            "roster": gcs.ref(f"gs://assets/{system}/roster.csv", roster),
            "history": {family: gcs.ref(f"gs://assets/{system}/history/{family}.csv",
                                        _history_csv(system, family, HISTORY_THROUGH[system][family]))
                        for family in prepare.FAMILIES},
        }
    data = {
        "schema_version": prepare.PREPARE_SCHEMA_VERSION,
        "prepare_id": prepare_id,
        "origin_month": "2026-10",
        "cutoff_utc": "2026-10-05T12:00:00Z",
        "extraction_contract_version": rs.EXTRACTION_CONTRACT_VERSION,
        "systems": systems,
        "operator": "operator@ifpri.example",
    }
    uri = f"gs://prep-bucket/prepare_requests/{prepare_id}/prepare_request.json"
    return prepare.validate_prepare_request(data, request_uri=uri, request_generation="3",
                                            request_sha256=REQUEST_SHA)


PUBLISHED = {
    "evi": ["2026-07", "2026-09", "2026-10"],  # August missing at the provider
    "fldas": ["2026-08", "2026-09"],
    "gosif_mean": ["2026-08"],  # normal publication lag
    "gosif_sd": ["2026-08", "2026-09"],
    "viirs": ["2026-10"],  # only the unfinished current month
}


class FakeAcquirer:
    def __init__(self, tmp_path, *, fail_discovery=None, fail_acquire=None):
        self.tmp_path, self.fail_discovery, self.fail_acquire = tmp_path, fail_discovery, fail_acquire
        self.queries, self.acquired = [], []

    def published_months(self, family, *, start_month, end_month):
        self.queries.append((family, start_month, end_month))
        if family == self.fail_discovery:
            raise rs.SourceRetrievalError("403 provider authentication failed")
        return {month: f"{family}:{month}" for month in PUBLISHED[family] if start_month <= month <= end_month}

    def acquire(self, family, month, *, provider_id, prepare_id, workdir):
        self.acquired.append((family, month, provider_id))
        if family == self.fail_acquire:
            raise rs.SourceRetrievalError("download timed out")
        bands = rs.SOURCE_CONTRACTS[family].bands
        offset = float(month[-2:])
        data = _tif_bytes([GRID + offset + index for index in range(len(bands))],
                          descriptions=list(bands) if len(bands) > 1 else None)
        path = Path(workdir) / f"{family}_{month}.tif"
        path.write_bytes(data)
        return prepare.AcquiredRaster(str(path), {"uri": f"gs://raw/{family}/{month}.tif", "generation": "5",
                                                  "sha256": hashlib.sha256(data).hexdigest()})


def _read_csv(gcs, uri):
    return pd.read_csv(io.StringIO(gcs.read_text(uri)), dtype={"admin_code": str, "month": str})


def test_prepare_extracts_latest_completed_months_for_both_rosters(tmp_path):
    gcs, acquirer = FakeGcs(), FakeAcquirer(tmp_path)

    manifest = prepare.run_prepare(_request(gcs), store=gcs, reader=gcs, acquirer=acquirer,
                                   output_root=ROOT, workdir=tmp_path)

    base = f"{ROOT}/prepared/prep-202610-a/"
    # Exact discovered provider identities are acquired, once per month.
    assert ("evi", "2026-09", "evi:2026-09") in acquirer.acquired
    assert sorted(m for f, m, _ in acquirer.acquired if f == "gosif_sd") == ["2026-08", "2026-09"]
    assert not [a for a in acquirer.acquired if a[0] == "viirs"]  # unfinished October excluded
    evi = _read_csv(gcs, base + "features/fewsnet/evi.csv")
    assert evi["admin_code"].tolist() == ["0", "00"] and evi["month"].tolist() == ["2026-09", "2026-09"]
    assert evi.loc[0, "EVI__mean"] == pytest.approx(np.mean([0, 1, 4, 5]) + 9)
    # Per-system months: IPCCH GOSIF SD history already holds August.
    assert _read_csv(gcs, base + "features/ipcch/gosif_sd.csv")["month"].unique().tolist() == ["2026-09"]
    assert _read_csv(gcs, base + "features/fewsnet/gosif_sd.csv")["month"].unique().tolist() == ["2026-08", "2026-09"]
    fldas = _read_csv(gcs, base + "features/ipcch/fldas.csv")
    assert fldas.loc[fldas["admin_code"].eq("7"), "Rainf_f_tavg__mean"].isna().all()  # outside the raster

    coverage = _read_csv(gcs, base + "source_coverage.csv")
    status = coverage.set_index(["system", "family", "month"])["status"]
    assert status[("fewsnet", "evi", "2026-08")] == "not_published"
    assert status[("fewsnet", "evi", "2026-09")] == "observed"
    assert status[("ipcch", "viirs", "2026-09")] == "history_snapshot"
    assert coverage.loc[(coverage.system == "ipcch") & (coverage.family == "fldas") & (coverage.month == "2026-09"),
                        "areas_without_values"].item() == 1

    families = manifest["families"]
    assert families["gosif_mean"]["provider_latest_completed_month"] == "2026-08"
    assert families["viirs"]["provider_latest_completed_month"] is None
    assert families["viirs"]["latest_observation_month"] == {"fewsnet": "2026-09", "ipcch": "2026-09"}
    assert families["evi"]["latest_observation_month"]["fewsnet"] == "2026-09"
    assert families["evi"]["not_published_months"] == ["2026-08"]
    assert families["evi"]["sources"][0]["provider_id"] == "evi:2026-09"
    assert manifest["plan"]["uri"] == base + "prepare_plan.json"
    assert manifest["request"]["sha256"] == REQUEST_SHA
    assert gcs.json(base + "prepare_plan.json")["request"] == {
        "uri": "gs://prep-bucket/prepare_requests/prep-202610-a/prepare_request.json",
        "generation": "3", "sha256": REQUEST_SHA}

    latest = _read_csv(gcs, base + "area_latest_observation.csv")
    row = latest.set_index(["system", "family", "admin_code"]).loc[("ipcch", "fldas", "7"), "latest_observation_month"]
    assert row == "2026-07"  # outside the raster: history is still its latest observation
    assert gcs.json(base + "prepare_status.json")["status"] == "succeeded"


def test_same_prepare_id_cannot_run_twice(tmp_path):
    gcs = FakeGcs()
    request = _request(gcs)
    prepare.run_prepare(request, store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path),
                        output_root=ROOT, workdir=tmp_path)
    status_versions = len(gcs.versions[f"{ROOT}/prepared/prep-202610-a/prepare_status.json"])

    with pytest.raises(prepare.PreparationConflict, match="new prepare_id"):
        prepare.run_prepare(request, store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path),
                            output_root=ROOT, workdir=tmp_path)
    assert len(gcs.versions[f"{ROOT}/prepared/prep-202610-a/prepare_status.json"]) == status_versions


def test_provider_failure_fails_preparation_and_is_not_lag(tmp_path):
    gcs = FakeGcs()

    with pytest.raises(rs.SourceRetrievalError):
        prepare.run_prepare(_request(gcs), store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path, fail_discovery="fldas"),
                            output_root=ROOT, workdir=tmp_path)

    base = f"{ROOT}/prepared/prep-202610-a/"
    status = gcs.json(base + "prepare_status.json")
    assert (status["status"], status["failure_reason"]) == ("failed", "source_retrieval_failed")
    assert base + "prepare_plan.json" not in gcs.versions


def test_download_failure_during_extract_retains_failed_status(tmp_path):
    gcs = FakeGcs()

    with pytest.raises(rs.SourceRetrievalError):
        prepare.run_prepare(_request(gcs, "prep-202610-b"), store=gcs, reader=gcs,
                            acquirer=FakeAcquirer(tmp_path, fail_acquire="gosif_sd"), output_root=ROOT, workdir=tmp_path)

    base = f"{ROOT}/prepared/prep-202610-b/"
    assert gcs.json(base + "prepare_status.json")["failure_reason"] == "source_retrieval_failed"
    assert base + "prepared_manifest.json" not in gcs.versions
    assert base + "prepare_plan.json" in gcs.versions  # plan evidence retained


def test_pinned_reads_use_exact_generation_and_hash():
    gcs = FakeGcs()
    old = gcs.ref("gs://assets/roster.csv", b"admin_code\n0\n")
    gcs.ref("gs://assets/roster.csv", b"admin_code\n0\n1\n")  # newer live version
    same_bytes = gcs.ref("gs://assets/roster.csv", b"admin_code\n0\n")  # same bytes, new generation

    assert prepare.read_pinned(gcs, old) == b"admin_code\n0\n"  # old version retained and readable
    assert prepare.read_pinned(gcs, same_bytes) == b"admin_code\n0\n"
    assert same_bytes["generation"] == "3" and same_bytes["sha256"] == old["sha256"]
    with pytest.raises(ReferenceIdentityError, match="sha256 mismatch"):
        prepare.read_pinned(gcs, {**old, "generation": "2"})
    with pytest.raises(ReferenceIdentityError, match="not found"):
        prepare.read_pinned(gcs, {**old, "generation": "9"})
    reader = prepare.GcsPinnedReader(gcs)
    assert reader.read_bytes("gs://assets/roster.csv", "1") == b"admin_code\n0\n"
    assert reader.read_bytes("gs://assets/roster.csv", "9") is None


@pytest.mark.parametrize(
    ("csv", "message"),
    [
        (b"admin_code,month,EVI__mean\n0,2026-07,1\n", "columns must be"),
        (b"admin_code,month,EVI__mean,EVI__std\n9,2026-07,1,1\n", "outside the roster"),
        (b"admin_code,month,EVI__mean,EVI__std\n0,2026-11,1,1\n", "months after 2026-09"),
        # October has not ended at the 2026-10-05 cutoff, although it equals the origin.
        (b"admin_code,month,EVI__mean,EVI__std\n0,2026-10,1,1\n", "months after 2026-09"),
        (b"admin_code,month,EVI__mean,EVI__std\n0,2026-07,,\n", "no observations"),
        (b"admin_code,month,EVI__mean,EVI__std\n0,2026-07,1,1\n0,2026-07,2,2\n", "duplicate"),
        (b"admin_code,month,EVI__mean,EVI__std\n0,2026-07,inf,1\n", "non-finite"),
    ],
)
def test_history_snapshot_is_validated_before_it_sets_the_baseline(tmp_path, csv, message):
    gcs = FakeGcs()
    request = _request(gcs, "prep-202610-c")
    request["systems"]["fewsnet"]["history"]["evi"] = gcs.ref("gs://assets/bad.csv", csv)

    with pytest.raises(ValueError, match=message):
        prepare.plan_prepare(request, store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path), output_root=ROOT)
    assert gcs.json(f"{ROOT}/prepared/prep-202610-c/prepare_status.json")["failure_reason"] == "preparation_error"


def test_prepare_request_validation():
    gcs = FakeGcs()
    data = {key: value for key, value in _request(gcs).items() if key != "request"}
    uri = "gs://prep-bucket/prepare_requests/prep-202610-a/prepare_request.json"

    ok = {"request_uri": uri, "request_generation": "1", "request_sha256": REQUEST_SHA}

    with pytest.raises(DeliveryManifestError, match="request_uri"):
        prepare.validate_prepare_request(data, **{**ok, "request_uri": uri.replace("prep-202610-a", "other")})
    with pytest.raises(DeliveryManifestError, match="request_sha256"):
        prepare.validate_prepare_request(data, **{**ok, "request_sha256": "E" * 64})
    with pytest.raises(DeliveryManifestError, match="cutoff_utc"):
        prepare.validate_prepare_request({**data, "cutoff_utc": "2026-10-05Z"}, **ok)
    missing = json.loads(json.dumps(data))
    del missing["systems"]["ipcch"]["history"]["viirs"]
    with pytest.raises(DeliveryManifestError, match="history fields mismatch"):
        prepare.validate_prepare_request(missing, **ok)
    with pytest.raises(DeliveryManifestError, match="unexpected"):
        prepare.validate_prepare_request({**data, "history_through": {}}, **ok)


def test_extract_runs_as_batch_job_without_automatic_retries():
    plan_ref = {"uri": f"{ROOT}/prepared/p1/prepare_plan.json", "generation": "4", "sha256": "a" * 64}
    image = "europe-docker.pkg.dev/p/r/delivery@sha256:" + "c" * 64

    config = prepare.prepare_batch_job_config(plan_ref, prepare_id="p1", origin_month="2026-10", image_uri=image,
                                              service_account="prep@p.iam.gserviceaccount.com",
                                              earth_engine_project="ee-project")
    spec = build_batch_job_spec(config)

    runnable = spec["task_groups"][0]["task_spec"]["runnables"][0]["container"]
    assert runnable["commands"][:3] == ["-m", "cloud.orchestrator.prepare", "extract"]
    assert runnable["commands"][3:9] == ["--plan-uri", plan_ref["uri"], "--plan-generation", "4",
                                         "--plan-sha256", "a" * 64]
    assert spec["task_groups"][0]["task_spec"]["max_retry_count"] == 0
    legacy = BatchJobConfig(job_name_prefix="x", image_uri=image, service_account="s", run_id="r",
                            feature_month="2026-10", worker_args=[])
    assert build_batch_job_spec(legacy)["task_groups"][0]["task_spec"]["runnables"][0]["container"]["commands"][1] == \
        "cloud.batch.evi_worker"


# --- production acquirer boundary with fake Earth Engine / HTTP / GCS ---------------------


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code, self.content = status_code, content


class FakeHttp:
    def __init__(self, files, status=None):
        self.files, self.status, self.requests = files, status, []

    def head(self, url, **kwargs):
        self.requests.append(("HEAD", url))
        return FakeResponse(self.status or (200 if url in self.files else 404))

    def get(self, url, **kwargs):
        self.requests.append(("GET", url))
        return FakeResponse(self.status or 200, self.files.get(url, b""))


def _acquirer(gcs, *, ee=None, http=None):
    return prepare.CloudSourceAcquirer(ee=ee, client=gcs, http=http, store=gcs, output_root=ROOT,
                                       timeout_seconds=5, poll_seconds=0)


def test_cloud_acquirer_gosif_retains_exact_downloaded_bytes(tmp_path):
    gcs = FakeGcs()
    url = rs.gosif_url(rs.SOURCE_CONTRACTS["gosif_sd"].export["url"], "2026-08")
    payload = gzip.compress(_tif_bytes(GRID))
    acquirer = _acquirer(gcs, http=FakeHttp({url: payload}))

    published = acquirer.published_months("gosif_sd", start_month="2026-08", end_month="2026-09")
    raster = acquirer.acquire("gosif_sd", "2026-08", provider_id=published["2026-08"], prepare_id="p1", workdir=tmp_path)

    assert list(published) == ["2026-08"]  # September 404: not yet published
    assert raster.source["sha256"] == hashlib.sha256(payload).hexdigest()
    assert gcs.read_bytes(raster.source["uri"], raster.source["generation"]) == payload
    with rasterio.open(raster.path) as dataset:
        assert dataset.read(1).tolist() == GRID.tolist()
    with pytest.raises(rs.SourceRetrievalError, match="differs"):
        acquirer.acquire("gosif_sd", "2026-08", provider_id="http://elsewhere/x.tif.gz", prepare_id="p1", workdir=tmp_path)
    with pytest.raises(rs.SourceRetrievalError, match="HTTP 503"):
        _acquirer(gcs, http=FakeHttp({}, status=503)).published_months("gosif_sd", start_month="2026-08",
                                                                       end_month="2026-08")


class FakeEE:
    """Records the exact image ID, band selection and export parameters."""

    def __init__(self, gcs, *, listing, shards, state="COMPLETED"):
        self.gcs, self.listing, self.shards, self.state = gcs, listing, shards, state
        self.calls = []
        fake = self

        class _Collection:
            def __init__(self, collection):
                self.collection = collection

            def filterDate(self, start, end):
                fake.calls.append(("filterDate", self.collection, start, end))
                return self

            def aggregate_array(self, prop):
                return prop

        class _List:
            def __init__(self, parts):
                self.parts = parts

            def getInfo(self):
                return [[ms for ms, _ in fake.listing], [image_id for _, image_id in fake.listing]]

        class _Image:
            def __init__(self, image_id):
                fake.calls.append(("Image", image_id))

            def select(self, bands):
                fake.calls.append(("select", list(bands)))
                return self

            def resample(self, method):
                fake.calls.append(("resample", method))
                return self

            def reproject(self, **kwargs):
                fake.calls.append(("reproject", kwargs))
                return self

        class _Task:
            def start(self):
                for name, data in fake.shards:
                    fake.gcs._write(f"gs://{fake.export['bucket']}/{fake.export['fileNamePrefix']}{name}", data, 0)

            def status(self):
                return {"state": fake.state}

        class _Export:
            class image:
                @staticmethod
                def toCloudStorage(**kwargs):
                    fake.export = kwargs
                    return _Task()

        class _Geometry:
            @staticmethod
            def Rectangle(coords, crs, geodesic):
                return ("Rectangle", tuple(coords))

        self.ImageCollection, self.List, self.Image = _Collection, _List, _Image
        self.Geometry = _Geometry
        self.batch = type("batch", (), {"Export": _Export})


def _ms(year, month):
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)


def test_cloud_acquirer_gee_uses_discovered_image_and_named_fldas_bands(tmp_path):
    gcs = FakeGcs()
    collection = rs.SOURCE_CONTRACTS["fldas"].product
    image_id = f"{collection}/A202609"
    bands = [GRID + index for index in range(len(rs.FLDAS_BANDS))]
    shards = [("-0000000000-0000000000.tif", _tif_bytes([band[:, :2] for band in bands])),
              ("-0000000000-0000000002.tif", _tif_bytes([band[:, 2:] for band in bands], origin=(2.0, 4.0)))]
    ee = FakeEE(gcs, listing=[(_ms(2026, 9), image_id)], shards=shards)
    acquirer = _acquirer(gcs, ee=ee)

    published = acquirer.published_months("fldas", start_month="2026-08", end_month="2026-10")
    raster = acquirer.acquire("fldas", "2026-09", provider_id=published["2026-09"], prepare_id="p1", workdir=tmp_path)

    assert published == {"2026-09": image_id}
    assert ("Image", image_id) in ee.calls and ("select", list(rs.FLDAS_BANDS)) in ee.calls
    assert not [call for call in ee.calls if call[0] == "filterDate" and call[2] == "2026-09-01"]  # no re-resolution
    assert ee.export["crsTransform"] == [0.1, 0, -180, 0, -0.1, 90]
    assert raster.source["band_names"] == "explicit_export_selection_order" and len(raster.source["shards"]) == 2
    with rasterio.open(raster.path) as dataset:
        assert dataset.descriptions == rs.FLDAS_BANDS
        assert dataset.read(2).tolist() == (GRID + 1).tolist()
    with pytest.raises(rs.SourceRetrievalError, match="already has objects"):
        acquirer.acquire("fldas", "2026-09", provider_id=image_id, prepare_id="p1", workdir=tmp_path)
    with pytest.raises(rs.SourceRetrievalError, match="not an image of"):
        acquirer.acquire("fldas", "2026-09", provider_id="MODIS/061/MOD13A3/x", prepare_id="p2", workdir=tmp_path)


def test_cloud_acquirer_gee_export_failure_is_retrieval_failure(tmp_path):
    gcs = FakeGcs()
    collection = rs.SOURCE_CONTRACTS["viirs"].product
    ee = FakeEE(gcs, listing=[], shards=[], state="FAILED")

    with pytest.raises(rs.SourceRetrievalError, match="export failed"):
        _acquirer(gcs, ee=ee).acquire("viirs", "2026-09", provider_id=f"{collection}/20260901",
                                      prepare_id="p1", workdir=tmp_path)
    assert ("resample", "bilinear") in ee.calls


def test_history_after_last_ended_month_at_early_cutoff_is_rejected(tmp_path):
    gcs = FakeGcs()
    request = _request(gcs, "prep-202610-d")
    request["cutoff_utc"] = "2026-08-05T00:00:00Z"  # September had not happened yet
    request["systems"]["ipcch"]["history"]["evi"] = gcs.ref(
        "gs://assets/sep.csv", b"admin_code,month,EVI__mean,EVI__std\n1,2026-09,1,1\n")

    with pytest.raises(ValueError, match="months after 2026-07"):
        prepare.plan_prepare(request, store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path), output_root=ROOT)


SUBMIT = {"image_uri": "europe-docker.pkg.dev/p/r/delivery@sha256:" + "c" * 64,
          "service_account": "prep@p.iam.gserviceaccount.com", "earth_engine_project": "ee-project"}


def test_batch_submit_failure_records_status_and_keeps_plan(tmp_path):
    gcs = FakeGcs()
    request = _request(gcs, "prep-202610-e")

    def failing_submit(config):
        raise PermissionError("403 batch.jobs.create denied")

    with pytest.raises(PermissionError):
        prepare.plan_and_submit(request, store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path), output_root=ROOT,
                                submit=failing_submit, **SUBMIT)

    base = f"{ROOT}/prepared/prep-202610-e/"
    status = gcs.json(base + "prepare_status.json")
    assert (status["status"], status["failure_reason"]) == ("failed", "batch_submit_failed")
    assert base + "prepare_plan.json" in gcs.versions and base + "_PREPARE_ACQUIRED" in gcs.versions
    with pytest.raises(prepare.PreparationConflict):
        prepare.plan_and_submit(request, store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path), output_root=ROOT,
                                submit=failing_submit, **SUBMIT)


def test_plan_and_submit_passes_pinned_plan_to_batch(tmp_path):
    gcs, submitted = FakeGcs(), []
    request = _request(gcs, "prep-202610-f")

    planned = prepare.plan_and_submit(request, store=gcs, reader=gcs, acquirer=FakeAcquirer(tmp_path),
                                      output_root=ROOT, submit=submitted.append, **SUBMIT)

    (config,) = submitted
    assert config.worker_args[:5] == ["extract", "--plan-uri", planned["plan_ref"]["uri"], "--plan-generation",
                                      planned["plan_ref"]["generation"]]
    assert f"{ROOT}/prepared/prep-202610-f/prepare_status.json" not in gcs.versions  # extract writes status
