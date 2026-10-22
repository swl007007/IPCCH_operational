"""2026-10 retrain source-contract changes: FEWS nightlight sum, GOSIF v3 boundary, legacy v1."""

import pandas as pd
import pytest

from cloud.batch import remote_sources as rs
from cloud.orchestrator import prepare
from cloud.orchestrator.delivery_job import AcceptanceError, require_supported_extraction_contract
from cloud.orchestrator.delivery_manifest import DeliveryManifestError
from tests.cloud import test_prepare as tp


def test_fews_nightlight_maps_to_viirs_sum_and_sd_to_std():
    assert rs.MODEL_COLUMN_MAPPING["fewsnet"]["nightlight"] == "avg_rad__sum"
    assert rs.MODEL_COLUMN_MAPPING["fewsnet"]["nightlight_sd"] == "avg_rad__std"
    assert rs.MODEL_COLUMN_MAPPING["ipcch"]["nightlight_mean"] == "avg_rad__sum"


def test_gosif_mean_is_v3_from_2025_only_and_sd_stays_v2():
    mean, sd = rs.SOURCE_CONTRACTS["gosif_mean"], rs.SOURCE_CONTRACTS["gosif_sd"]
    assert "GOSIF-GPP_v3" in mean.export["url"] and mean.first_month == "2025-01"
    assert "v3/Monthly/Mean from 2025-01" in mean.product and "inherited v2 history" in mean.product
    assert "GOSIF-GPP_v2" in sd.export["url"]


def test_refresh_before_the_v3_boundary_is_rejected():
    gcs = tp.FakeGcs()
    request = tp._request(gcs)
    raw = {key: value for key, value in request.items() if key != "request"}
    uri = request["request"]["uri"]
    with pytest.raises(DeliveryManifestError, match="precedes the contract start"):
        prepare.validate_prepare_request({**raw, "refresh_from": {"gosif_mean": "2024-12"}}, request_uri=uri,
                                         request_generation="3", request_sha256=tp.REQUEST_SHA)
    accepted = prepare.validate_prepare_request({**raw, "refresh_from": {"gosif_mean": "2025-01"}},
                                                request_uri=uri, request_generation="3",
                                                request_sha256=tp.REQUEST_SHA)
    assert accepted["refresh_from"] == {"gosif_mean": "2025-01"}


def test_plan_never_extracts_gosif_mean_before_the_v3_boundary(tmp_path, monkeypatch):
    monkeypatch.setitem(tp.PUBLISHED, "gosif_mean", ["2024-08", "2024-12", "2025-01", "2025-06"])
    gcs = tp.FakeGcs()
    request = tp._request(gcs)
    for system in ("fewsnet", "ipcch"):  # v2 history that ends before the boundary
        rows = pd.DataFrame({"admin_code": list(tp.ROSTERS[system]), "month": "2024-06", "GPP_Mean__mean": 1.0})
        request["systems"][system]["history"]["gosif_mean"] = gcs.ref(
            f"gs://assets/{system}/history/gosif_mean_v2.csv", rows.to_csv(index=False).encode())
    plan = prepare.plan_prepare(request, store=gcs, reader=gcs, acquirer=tp.FakeAcquirer(tmp_path),
                                output_root="gs://prep-bucket")
    family = plan["families"]["gosif_mean"]
    assert family["provider_latest_completed_month"] == "2025-06"
    assert set(family["months"]) == {"2025-01", "2025-06"}
    for months in family["system_months"].values():
        assert months[0] == "2025-01" and min(months) >= "2025-01"


@pytest.mark.parametrize("version", ["current-repo-remote-scripts-v1", rs.EXTRACTION_CONTRACT_VERSION])
def test_delivery_reads_legacy_v1_and_current_prepared_snapshots(version):
    assert require_supported_extraction_contract({"extraction_contract_version": version}) == version


def test_delivery_rejects_unknown_extraction_contract():
    with pytest.raises(AcceptanceError):
        require_supported_extraction_contract({"extraction_contract_version": "current-repo-remote-scripts-v0"})


def test_v3_http_discovery_stops_at_the_contract_start(tmp_path):
    gcs = tp.FakeGcs()
    mean = rs.SOURCE_CONTRACTS["gosif_mean"]
    old = rs.gosif_url(mean.export["url"], "2024-12")  # v3 archive also has pre-2025 files
    http = tp.FakeHttp({old: b"x"})
    found = tp._acquirer(gcs, http=http).latest_published("gosif_mean", floor_month=mean.first_month,
                                                           end_month="2026-09")
    assert found is None
    assert len(http.requests) == 21  # 2026-09 back to 2025-01 only
