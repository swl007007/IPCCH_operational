from pathlib import Path

import pytest

from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    GenerationConflict,
    LocalArtifactStore,
    put_immutable_or_verify,
    put_mutable_or_verify,
    upload_file_immutable_or_verify,
)


def test_local_store_round_trips_binary_and_records_sha256(tmp_path):
    store = LocalArtifactStore(tmp_path)
    ref = store.put_bytes("gs://bucket/models/model.joblib", b"\x00model", if_generation_match=0)
    assert ref.generation == "1"
    assert ref.size_bytes == 6
    assert store.read_bytes(ref.uri) == b"\x00model"
    assert store.get_ref(ref.uri) == ref


def test_local_store_rejects_immutable_overwrite(tmp_path):
    store = LocalArtifactStore(tmp_path)
    store.put_text("gs://bucket/object.json", "{}", if_generation_match=0)
    with pytest.raises(GenerationConflict):
        store.put_text("gs://bucket/object.json", "{\"x\":1}", if_generation_match=0)


def test_local_store_upload_download_preserves_file_bytes(tmp_path):
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    source.write_bytes(b"artifact")
    store = LocalArtifactStore(tmp_path / "objects")
    ref = store.upload_file(source, "gs://bucket/artifact.bin", if_generation_match=0)
    store.download_file(ref.uri, target, generation=ref.generation)
    assert target.read_bytes() == b"artifact"


def test_immutable_retry_accepts_identical_bytes_but_rejects_drift(tmp_path):
    store = LocalArtifactStore(tmp_path)
    first = put_immutable_or_verify(store, "gs://bucket/object", b"same")
    assert put_immutable_or_verify(store, "gs://bucket/object", b"same") == first
    with pytest.raises(GenerationConflict, match="different bytes"):
        put_immutable_or_verify(store, "gs://bucket/object", b"changed")


def test_immutable_file_retry_compares_sha256_and_size(tmp_path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"large-artifact")
    store = LocalArtifactStore(tmp_path / "objects")
    first = upload_file_immutable_or_verify(store, path, "gs://bucket/large.bin")
    assert upload_file_immutable_or_verify(store, path, first.uri) == first


def test_mutable_retry_accepts_already_committed_intended_bytes(tmp_path):
    store = LocalArtifactStore(tmp_path)
    first = put_mutable_or_verify(store, "gs://bucket/current.json", b"old", 0)
    updated = put_mutable_or_verify(
        store, first.uri, b"new", expected_generation=first.generation
    )
    assert put_mutable_or_verify(
        store, first.uri, b"new", expected_generation=first.generation
    ) == updated


def test_local_store_lists_refs_under_trailing_slash_prefix(tmp_path):
    store = LocalArtifactStore(tmp_path)
    expected = store.put_bytes("gs://bucket/models/model.joblib", b"model")
    store.put_bytes("gs://bucket/reports/report.json", b"{}")

    assert store.list("gs://bucket/models/") == [expected]
