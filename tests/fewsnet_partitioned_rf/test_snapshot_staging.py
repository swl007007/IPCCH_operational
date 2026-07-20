import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

import fewsnet_partitioned_rf_pipeline.core.data as data_module
import fewsnet_partitioned_rf_pipeline.cli.stage_snapshot as stage_snapshot_cli
from fewsnet_partitioned_rf_pipeline.core.data import (
    normalize_admin_code,
    stage_snapshot,
)
from fewsnet_partitioned_rf_pipeline.schemas import validate_payload
from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    GenerationConflict,
    LocalArtifactStore,
)


class RecordingLocalArtifactStore(LocalArtifactStore):
    def __init__(self, root):
        super().__init__(root)
        self.write_order = []

    def put_bytes(self, uri, data, *, if_generation_match=None):
        ref = super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )
        self.write_order.append(uri)
        return ref

    def upload_file(self, path, uri, *, if_generation_match=None):
        ref = super().upload_file(
            path,
            uri,
            if_generation_match=if_generation_match,
        )
        self.write_order.append(uri)
        return ref


def _write_panel_fixture(tmp_path, rows=None):
    path = tmp_path / "assembled_fewsnet.csv"
    pd.DataFrame(
        rows
        or [
            {
                "FEWSNET_admin_code": " 12.0 ",
                "date": "2026-03-01",
                "fews_ipc_crisis": 1,
                "ignored_feature": 10,
            },
            {
                "FEWSNET_admin_code": "ABC",
                "date": "2026-03-15",
                "fews_ipc_crisis": 0,
                "ignored_feature": 20,
            },
            {
                "FEWSNET_admin_code": "12",
                "date": "2026-04-01",
                "fews_ipc_crisis": None,
                "ignored_feature": 30,
            },
            {
                "FEWSNET_admin_code": " ABC ",
                "date": "2026-04-20",
                "fews_ipc_crisis": None,
                "ignored_feature": 40,
            },
        ]
    ).to_csv(path, index=False)
    return path


def _write_boundary_fixture(
    tmp_path,
    *,
    admin_codes=("ABC", " 12.0 "),
    crs="EPSG:4326",
    geometries=None,
    include_admin_code=True,
):
    path = tmp_path / "boundaries.gpkg"
    data = {"name": [f"area-{index}" for index in range(len(admin_codes))]}
    if include_admin_code:
        data["admin_code"] = list(admin_codes)
    else:
        data["other_code"] = list(admin_codes)
    gdf = gpd.GeoDataFrame(
        data,
        geometry=list(geometries or [Point(index, index) for index in range(len(admin_codes))]),
        crs=crs,
    )
    gdf.to_file(path, driver="GPKG")
    return path


def _identity_payload(manifest):
    return {
        "schema_version": "fewsnet-source-snapshot-v1",
        "panel_sha256": manifest.panel.sha256,
        "boundaries_sha256": manifest.boundaries.sha256,
        "admin_universe_sha256": manifest.admin_universe.sha256,
        "row_count": manifest.row_count,
        "area_count": manifest.area_count,
        "spatial_feature_count": manifest.spatial_feature_count,
        "crs": manifest.crs,
        "latest_feature_month": manifest.latest_feature_month,
        "latest_label_month": manifest.latest_label_month,
        "admin_code_mapping": manifest.admin_code_mapping,
    }


def test_normalize_admin_code_preserves_identifiers_and_canonicalizes_integer_like_values():
    assert normalize_admin_code(" 12.0 ") == "12"
    assert normalize_admin_code(12.0) == "12"
    assert normalize_admin_code("  ABC-01  ") == "ABC-01"


def test_stage_snapshot_writes_manifest_last_and_preserves_area_identity(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")

    manifest = stage_snapshot(
        panel_path=panel,
        boundaries_path=boundaries,
        destination_root="gs://bucket/fewsnet_partitioned_rf",
        store=store,
        created_at_utc="2026-07-20T00:00:00Z",
    )

    assert manifest.row_count == 4
    assert manifest.area_count == 2
    assert manifest.spatial_feature_count == 2
    assert manifest.latest_feature_month == "2026-04"
    assert manifest.latest_label_month == "2026-03"
    assert manifest.crs == "EPSG:4326"
    assert len(manifest.snapshot_content_sha256) == 64
    assert manifest.admin_code_mapping == {
        "panel": "FEWSNET_admin_code",
        "boundaries": "admin_code",
        "canonical": "admin_code",
    }
    assert manifest.source_identity == {
        "panel_bootstrap_path": str(panel),
        "boundaries_bootstrap_path": str(boundaries),
        "panel_source_type": "assembled_fewsnet_csv",
        "boundaries_source_type": "fewsnet_admin_boundaries_v3",
    }
    assert store.write_order[-1].endswith("source_manifest.json")
    assert len(store.write_order) == 4

    canonical_identity = json.dumps(
        _identity_payload(manifest),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    expected_content_sha256 = hashlib.sha256(canonical_identity).hexdigest()
    assert manifest.snapshot_content_sha256 == expected_content_sha256
    assert manifest.snapshot_id == f"fewsnet-202604-{expected_content_sha256[:8]}"

    assert store.read_bytes(manifest.panel.uri) == panel.read_bytes()
    assert store.read_text(manifest.admin_universe.uri) == "admin_code\n12\nABC\n"

    normalized_boundaries = tmp_path / "normalized.parquet"
    store.download_file(
        manifest.boundaries.uri,
        normalized_boundaries,
        generation=manifest.boundaries.generation,
    )
    normalized_gdf = gpd.read_parquet(normalized_boundaries)
    assert normalized_gdf["admin_code"].tolist() == ["12", "ABC"]
    assert normalized_gdf.crs.to_epsg() == 4326

    manifest_uri = store.write_order[-1]
    manifest_payload = json.loads(store.read_text(manifest_uri))
    validate_payload("source-snapshot", manifest_payload)
    assert manifest_payload == {
        "schema_version": "fewsnet-source-snapshot-v1",
        **asdict(manifest),
    }


def test_stage_snapshot_reuses_byte_identical_immutable_objects(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    kwargs = {
        "panel_path": panel,
        "boundaries_path": boundaries,
        "destination_root": "gs://bucket/fewsnet_partitioned_rf",
        "store": store,
        "created_at_utc": "2026-07-20T00:00:00Z",
    }

    first = stage_snapshot(**kwargs)
    second = stage_snapshot(**kwargs)

    assert second == first
    assert len(store.write_order) == 4


def test_stage_snapshot_reuses_existing_manifest_when_only_created_at_changes(
    tmp_path,
):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "boundaries_path": boundaries,
        "destination_root": "gs://bucket/fewsnet_partitioned_rf",
        "store": store,
    }

    first = stage_snapshot(
        **common,
        created_at_utc="2026-07-20T00:00:00Z",
    )
    second = stage_snapshot(
        **common,
        created_at_utc="2026-07-20T01:00:00Z",
    )

    assert second == first
    assert len(store.write_order) == 4


def test_stage_snapshot_rejects_manifest_with_stale_exact_artifact_generation(
    tmp_path,
):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "boundaries_path": boundaries,
        "destination_root": "gs://bucket/fewsnet_partitioned_rf",
        "store": store,
    }
    first = stage_snapshot(
        **common,
        created_at_utc="2026-07-20T00:00:00Z",
    )
    panel_bytes = store.read_bytes(
        first.panel.uri,
        generation=first.panel.generation,
    )
    replacement = store.put_bytes(
        first.panel.uri,
        panel_bytes,
        if_generation_match=first.panel.generation,
    )
    assert replacement.generation != first.panel.generation

    with pytest.raises(GenerationConflict, match="exact artifact reference"):
        stage_snapshot(
            **common,
            created_at_utc="2026-07-20T01:00:00Z",
        )


def test_stage_snapshot_rejects_unreadable_generation_in_existing_manifest(
    tmp_path,
):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "boundaries_path": boundaries,
        "destination_root": "gs://bucket/fewsnet_partitioned_rf",
        "store": store,
    }
    manifest = stage_snapshot(
        **common,
        created_at_utc="2026-07-20T00:00:00Z",
    )
    manifest_uri = (
        "gs://bucket/fewsnet_partitioned_rf/inputs/snapshots/"
        f"{manifest.snapshot_id}/source_manifest.json"
    )
    manifest_ref = store.get_ref(manifest_uri)
    payload = json.loads(
        store.read_text(manifest_uri, generation=manifest_ref.generation)
    )
    payload["panel"]["generation"] = "999"
    store.put_bytes(
        manifest_uri,
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        if_generation_match=manifest_ref.generation,
    )

    with pytest.raises(GenerationConflict, match="exact artifact reference"):
        stage_snapshot(
            **common,
            created_at_utc="2026-07-20T01:00:00Z",
        )


def test_stage_snapshot_inspects_hashes_and_uploads_one_captured_panel_version(
    tmp_path,
    monkeypatch,
):
    panel = _write_panel_fixture(tmp_path)
    original_panel_bytes = panel.read_bytes()
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    original_inspect_panel = data_module.inspect_panel
    mutated = False

    def inspect_then_mutate_bootstrap(path):
        nonlocal mutated
        result = original_inspect_panel(path)
        if not mutated:
            with panel.open("ab") as handle:
                handle.write(b"XYZ,2026-05-01,1,50\n")
            mutated = True
        return result

    monkeypatch.setattr(data_module, "inspect_panel", inspect_then_mutate_bootstrap)

    manifest = stage_snapshot(
        panel_path=panel,
        boundaries_path=boundaries,
        destination_root="gs://bucket/fewsnet_partitioned_rf",
        store=store,
        created_at_utc="2026-07-20T00:00:00Z",
    )

    assert panel.read_bytes() != original_panel_bytes
    assert store.read_bytes(manifest.panel.uri) == original_panel_bytes
    assert manifest.panel.sha256 == hashlib.sha256(original_panel_bytes).hexdigest()
    assert manifest.row_count == 4
    assert manifest.area_count == 2
    assert manifest.latest_feature_month == "2026-04"


def test_inspect_panel_preserves_na_admin_identifier(tmp_path):
    panel = _write_panel_fixture(
        tmp_path,
        rows=[
            {
                "FEWSNET_admin_code": "NA",
                "date": "2026-03-01",
                "fews_ipc_crisis": 1,
            },
            {
                "FEWSNET_admin_code": "A,B",
                "date": "2026-03-01",
                "fews_ipc_crisis": 0,
            },
        ],
    )

    info = data_module.inspect_panel(panel)

    assert info["admin_codes"] == ("A,B", "NA")


def test_stage_snapshot_quotes_admin_universe_csv_identifiers(tmp_path):
    panel = _write_panel_fixture(
        tmp_path,
        rows=[
            {
                "FEWSNET_admin_code": "A,B",
                "date": "2026-03-01",
                "fews_ipc_crisis": 1,
            },
            {
                "FEWSNET_admin_code": "XYZ",
                "date": "2026-03-01",
                "fews_ipc_crisis": 0,
            },
        ],
    )
    boundaries = _write_boundary_fixture(
        tmp_path,
        admin_codes=("XYZ", "A,B"),
    )
    store = RecordingLocalArtifactStore(tmp_path / "store")

    manifest = stage_snapshot(
        panel_path=panel,
        boundaries_path=boundaries,
        destination_root="gs://bucket/fewsnet_partitioned_rf",
        store=store,
        created_at_utc="2026-07-20T00:00:00Z",
    )

    admin_universe_csv = store.read_text(manifest.admin_universe.uri)
    assert admin_universe_csv == 'admin_code\n"A,B"\nXYZ\n'
    assert list(csv.reader(admin_universe_csv.splitlines())) == [
        ["admin_code"],
        ["A,B"],
        ["XYZ"],
    ]


def test_inspect_panel_rejects_duplicate_area_period_keys_across_chunks(
    tmp_path,
    monkeypatch,
):
    panel = _write_panel_fixture(
        tmp_path,
        rows=[
            {
                "FEWSNET_admin_code": "12.0",
                "date": "2026-03-01",
                "fews_ipc_crisis": 1,
            },
            {
                "FEWSNET_admin_code": "ABC",
                "date": "2026-03-01",
                "fews_ipc_crisis": 0,
            },
            {
                "FEWSNET_admin_code": "12",
                "date": "2026-03-20",
                "fews_ipc_crisis": 1,
            },
        ],
    )
    monkeypatch.setattr(data_module, "PANEL_CHUNK_SIZE", 2)

    with pytest.raises(ValueError, match="duplicate"):
        data_module.inspect_panel(panel)


def test_stage_snapshot_rejects_panel_spatial_area_set_mismatch(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path, admin_codes=("12", "XYZ"))
    store = RecordingLocalArtifactStore(tmp_path / "store")

    with pytest.raises(ValueError, match="area set mismatch"):
        stage_snapshot(
            panel_path=panel,
            boundaries_path=boundaries,
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=store,
            created_at_utc="2026-07-20T00:00:00Z",
        )

    assert store.write_order == []


def test_stage_snapshot_rejects_boundaries_missing_admin_code(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path, include_admin_code=False)

    with pytest.raises(ValueError, match="admin_code"):
        stage_snapshot(
            panel_path=panel,
            boundaries_path=boundaries,
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )


def test_stage_snapshot_rejects_non_wgs84_boundaries(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(tmp_path, crs="EPSG:3857")

    with pytest.raises(ValueError, match="EPSG:4326"):
        stage_snapshot(
            panel_path=panel,
            boundaries_path=boundaries,
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )


@pytest.mark.parametrize(
    ("admin_codes", "geometries"),
    [
        (("12", "12.0"), None),
        (("12", "ABC"), (Point(0, 0), None)),
    ],
)
def test_stage_snapshot_requires_one_non_null_geometry_per_normalized_admin_code(
    tmp_path,
    admin_codes,
    geometries,
):
    panel = _write_panel_fixture(tmp_path)
    boundaries = _write_boundary_fixture(
        tmp_path,
        admin_codes=admin_codes,
        geometries=geometries,
    )

    with pytest.raises(ValueError, match="one non-null geometry"):
        stage_snapshot(
            panel_path=panel,
            boundaries_path=boundaries,
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )


def test_stage_snapshot_cli_prints_manifest_uri_as_json(monkeypatch, capsys):
    store = object()
    monkeypatch.setattr(
        stage_snapshot_cli.GCSArtifactStore,
        "from_default",
        lambda: store,
    )
    monkeypatch.setattr(
        stage_snapshot_cli,
        "stage_snapshot",
        lambda **kwargs: SimpleNamespace(snapshot_id="fewsnet-202604-deadbeef"),
    )

    result = stage_snapshot_cli.main(
        [
            "--panel",
            "panel.csv",
            "--boundaries",
            "boundaries.shp",
            "--destination-root",
            "gs://bucket/root/",
            "--created-at-utc",
            "2026-07-20T00:00:00Z",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "manifest_uri": (
            "gs://bucket/root/inputs/snapshots/"
            "fewsnet-202604-deadbeef/source_manifest.json"
        )
    }


@pytest.mark.parametrize("error", [ValueError("invalid"), GenerationConflict("conflict")])
def test_stage_snapshot_cli_returns_nonzero_for_validation_or_generation_conflict(
    monkeypatch,
    error,
):
    monkeypatch.setattr(
        stage_snapshot_cli.GCSArtifactStore,
        "from_default",
        lambda: object(),
    )

    def fail(**kwargs):
        raise error

    monkeypatch.setattr(stage_snapshot_cli, "stage_snapshot", fail)

    assert stage_snapshot_cli.main(
        [
            "--panel",
            "panel.csv",
            "--boundaries",
            "boundaries.shp",
            "--destination-root",
            "gs://bucket/root",
            "--created-at-utc",
            "2026-07-20T00:00:00Z",
        ]
    ) == 1
