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
from fewsnet_partitioned_rf_pipeline.core.normalization import normalize_panel
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


def write_matching_normalized_fixture(tmp_path):
    source_frame = pd.read_csv(_write_panel_fixture(tmp_path))
    source_frame["Tair_f_tavg_mean"] = [20.0, 25.0, 21.0, 26.0]
    source_frame["Tair_zscore"] = 0.0
    source_frame["Rainf_f_tavg_mean"] = [40.0, 45.0, 41.0, 46.0]
    source_frame["Rainf_zscore"] = 0.0
    raw = tmp_path / "assembled_fewsnet.raw.csv"
    source_frame.to_csv(raw, index=False)
    normalized = tmp_path / "assembled_fewsnet.normalized.csv"
    audit = tmp_path / "panel_normalization_audit.json"
    normalize_panel(raw, normalized, audit)
    return normalized, audit


def _write_matching_audit(panel, tmp_path):
    frame = pd.read_csv(panel)
    periods = pd.to_datetime(frame["date"]).dt.to_period("M")
    labeled = frame["fews_ipc_crisis"].fillna("").astype(str).str.strip().ne("")
    panel_sha256 = hashlib.sha256(panel.read_bytes()).hexdigest()
    payload = {
        "schema_version": "fewsnet-panel-normalization-v1",
        "normalization_version": "deduplicate-before-global-rolling-zscore-v1",
        "source_panel": {
            "path": str(panel) + ".raw",
            "sha256": panel_sha256,
            "size_bytes": panel.stat().st_size,
            "row_count": len(frame),
            "column_count": len(frame.columns),
        },
        "output_panel": {
            "path": str(panel),
            "sha256": panel_sha256,
            "size_bytes": panel.stat().st_size,
            "row_count": len(frame),
            "column_count": len(frame.columns),
        },
        "key_columns": ["FEWSNET_admin_code", "feature_month"],
        "sort_columns": ["FEWSNET_admin_code", "date", "source_row_number"],
        "comparison_excluded_columns": ["Tair_zscore", "Rainf_zscore"],
        "climate_derivation": {
            "Tair_f_tavg_mean": "Tair_zscore",
            "Rainf_f_tavg_mean": "Rainf_zscore",
            "rolling_order": "global_after_stable_admin_date_sort",
            "window": 12,
            "minimum_periods": 1,
            "grouping_column": "FEWSNET_admin_code",
            "std_ddof": 1,
        },
        "latest_feature_month": str(periods.max()),
        "latest_label_month": str(periods.loc[labeled].max()),
        "duplicate_group_count": 0,
        "duplicate_row_count": 0,
        "removed_row_count": 0,
        "conflict_group_count": 0,
        "duplicate_groups": [],
    }
    audit = tmp_path / f"{panel.stem}.normalization.audit.json"
    audit.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit


def _identity_payload(manifest):
    return {
        "schema_version": "fewsnet-source-snapshot-v2",
        "panel_sha256": manifest.panel.sha256,
        "normalization_audit_sha256": manifest.normalization_audit.sha256,
        "normalization_version": "deduplicate-before-global-rolling-zscore-v1",
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


def test_stage_snapshot_uploads_verified_normalization_audit_before_manifest(tmp_path):
    normalized_panel, audit = write_matching_normalized_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")

    manifest = stage_snapshot(
        panel_path=normalized_panel,
        normalization_audit_path=audit,
        boundaries_path=_write_boundary_fixture(tmp_path),
        destination_root="gs://bucket/fewsnet_partitioned_rf",
        store=store,
        created_at_utc="2026-07-20T00:00:00Z",
    )

    assert manifest.normalization_audit.sha256 == hashlib.sha256(
        audit.read_bytes()
    ).hexdigest()
    assert manifest.panel.uri.endswith("assembled_fewsnet.normalized.csv")
    assert manifest.normalization_audit.uri.endswith(
        "panel_normalization_audit.json"
    )
    assert store.write_order[-1].endswith("source_manifest.json")


def test_stage_snapshot_rejects_audit_for_different_panel(tmp_path):
    normalized_panel, audit = write_matching_normalized_fixture(tmp_path)
    normalized_panel.write_bytes(normalized_panel.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="normalization.*checksum|size"):
        stage_snapshot(
            panel_path=normalized_panel,
            normalization_audit_path=audit,
            boundaries_path=_write_boundary_fixture(tmp_path),
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )


def test_stage_snapshot_keeps_duplicate_panel_hard_gate_after_audit_validation(
    tmp_path,
):
    normalized_panel, audit = write_matching_normalized_fixture(tmp_path)
    frame = pd.read_csv(normalized_panel)
    pd.concat([frame, frame.iloc[[0]]], ignore_index=True).to_csv(
        normalized_panel,
        index=False,
    )
    payload = json.loads(audit.read_text(encoding="utf-8"))
    payload["source_panel"]["row_count"] = len(frame) + 1
    payload["output_panel"].update(
        {
            "sha256": hashlib.sha256(normalized_panel.read_bytes()).hexdigest(),
            "size_bytes": normalized_panel.stat().st_size,
            "row_count": len(frame) + 1,
        }
    )
    audit.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate FEWSNET_admin_code"):
        stage_snapshot(
            panel_path=normalized_panel,
            normalization_audit_path=audit,
            boundaries_path=_write_boundary_fixture(tmp_path),
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )


def test_stage_snapshot_writes_manifest_last_and_preserves_area_identity(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")

    manifest = stage_snapshot(
        panel_path=panel,
        normalization_audit_path=audit,
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
        "panel_source_type": "assembled_fewsnet_normalized_v1_csv",
        "boundaries_source_type": "fewsnet_admin_boundaries_v3",
    }
    assert store.write_order[-1].endswith("source_manifest.json")
    assert len(store.write_order) == 5

    canonical_identity = json.dumps(
        _identity_payload(manifest),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    expected_content_sha256 = hashlib.sha256(canonical_identity).hexdigest()
    assert manifest.snapshot_content_sha256 == expected_content_sha256
    assert manifest.snapshot_id == f"fewsnet-202604-{expected_content_sha256[:8]}"

    assert store.read_bytes(manifest.panel.uri) == panel.read_bytes()
    assert store.read_bytes(manifest.normalization_audit.uri) == audit.read_bytes()
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
        "schema_version": "fewsnet-source-snapshot-v2",
        **asdict(manifest),
    }


def test_stage_snapshot_reuses_byte_identical_immutable_objects(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    kwargs = {
        "panel_path": panel,
        "normalization_audit_path": audit,
        "boundaries_path": boundaries,
        "destination_root": "gs://bucket/fewsnet_partitioned_rf",
        "store": store,
        "created_at_utc": "2026-07-20T00:00:00Z",
    }

    first = stage_snapshot(**kwargs)
    second = stage_snapshot(**kwargs)

    assert second == first
    assert len(store.write_order) == 5


def test_stage_snapshot_reuses_existing_manifest_when_only_created_at_changes(
    tmp_path,
):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "normalization_audit_path": audit,
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
    assert len(store.write_order) == 5


def test_stage_snapshot_rejects_manifest_with_stale_exact_artifact_generation(
    tmp_path,
):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "normalization_audit_path": audit,
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


def test_stage_snapshot_rejects_stale_normalization_audit_generation(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "normalization_audit_path": audit,
        "boundaries_path": boundaries,
        "destination_root": "gs://bucket/fewsnet_partitioned_rf",
        "store": store,
    }
    first = stage_snapshot(
        **common,
        created_at_utc="2026-07-20T00:00:00Z",
    )
    audit_bytes = store.read_bytes(
        first.normalization_audit.uri,
        generation=first.normalization_audit.generation,
    )
    replacement = store.put_bytes(
        first.normalization_audit.uri,
        audit_bytes,
        if_generation_match=first.normalization_audit.generation,
    )
    assert replacement.generation != first.normalization_audit.generation

    with pytest.raises(GenerationConflict, match="exact artifact reference"):
        stage_snapshot(
            **common,
            created_at_utc="2026-07-20T01:00:00Z",
        )


def test_stage_snapshot_audit_drift_changes_snapshot_identity(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "boundaries_path": boundaries,
        "destination_root": "gs://bucket/fewsnet_partitioned_rf",
        "store": store,
        "created_at_utc": "2026-07-20T00:00:00Z",
    }
    first = stage_snapshot(normalization_audit_path=audit, **common)
    changed_payload = json.loads(audit.read_text(encoding="utf-8"))
    changed_payload["source_panel"]["path"] += ".relocated"
    changed_audit = tmp_path / "changed-normalization-audit.json"
    changed_audit.write_text(
        json.dumps(changed_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    second = stage_snapshot(normalization_audit_path=changed_audit, **common)

    assert second.normalization_audit.sha256 != first.normalization_audit.sha256
    assert second.snapshot_content_sha256 != first.snapshot_content_sha256
    assert second.snapshot_id != first.snapshot_id


def test_stage_snapshot_rejects_unreadable_generation_in_existing_manifest(
    tmp_path,
):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")
    common = {
        "panel_path": panel,
        "normalization_audit_path": audit,
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
    audit = _write_matching_audit(panel, tmp_path)
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
        normalization_audit_path=audit,
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
    audit = _write_matching_audit(panel, tmp_path)
    store = RecordingLocalArtifactStore(tmp_path / "store")

    manifest = stage_snapshot(
        panel_path=panel,
        normalization_audit_path=audit,
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
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path, admin_codes=("12", "XYZ"))
    store = RecordingLocalArtifactStore(tmp_path / "store")

    with pytest.raises(ValueError, match="area set mismatch"):
        stage_snapshot(
            panel_path=panel,
            normalization_audit_path=audit,
            boundaries_path=boundaries,
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=store,
            created_at_utc="2026-07-20T00:00:00Z",
        )

    assert store.write_order == []


def test_stage_snapshot_rejects_boundaries_missing_admin_code(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path, include_admin_code=False)

    with pytest.raises(ValueError, match="admin_code"):
        stage_snapshot(
            panel_path=panel,
            normalization_audit_path=audit,
            boundaries_path=boundaries,
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )


def test_stage_snapshot_rejects_non_wgs84_boundaries(tmp_path):
    panel = _write_panel_fixture(tmp_path)
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(tmp_path, crs="EPSG:3857")

    with pytest.raises(ValueError, match="EPSG:4326"):
        stage_snapshot(
            panel_path=panel,
            normalization_audit_path=audit,
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
    audit = _write_matching_audit(panel, tmp_path)
    boundaries = _write_boundary_fixture(
        tmp_path,
        admin_codes=admin_codes,
        geometries=geometries,
    )

    with pytest.raises(ValueError, match="one non-null geometry"):
        stage_snapshot(
            panel_path=panel,
            normalization_audit_path=audit,
            boundaries_path=boundaries,
            destination_root="gs://bucket/fewsnet_partitioned_rf",
            store=RecordingLocalArtifactStore(tmp_path / "store"),
            created_at_utc="2026-07-20T00:00:00Z",
        )


def test_stage_snapshot_cli_prints_manifest_uri_as_json(monkeypatch, capsys):
    store = object()
    captured = {}
    monkeypatch.setattr(
        stage_snapshot_cli.GCSArtifactStore,
        "from_default",
        lambda: store,
    )
    def fake_stage_snapshot(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(snapshot_id="fewsnet-202604-deadbeef")

    monkeypatch.setattr(stage_snapshot_cli, "stage_snapshot", fake_stage_snapshot)

    result = stage_snapshot_cli.main(
        [
            "--panel",
            "panel.csv",
            "--normalization-audit",
            "panel.audit.json",
            "--boundaries",
            "boundaries.shp",
            "--destination-root",
            "gs://bucket/root/",
            "--created-at-utc",
            "2026-07-20T00:00:00Z",
        ]
    )

    assert result == 0
    assert captured["normalization_audit_path"] == Path("panel.audit.json")
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
            "--normalization-audit",
            "panel.audit.json",
            "--boundaries",
            "boundaries.shp",
            "--destination-root",
            "gs://bucket/root",
            "--created-at-utc",
            "2026-07-20T00:00:00Z",
        ]
    ) == 1
