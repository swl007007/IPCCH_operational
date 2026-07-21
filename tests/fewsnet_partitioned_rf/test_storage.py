import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from google.api_core.exceptions import PreconditionFailed

from fewsnet_partitioned_rf_pipeline.vertex.storage import (
    GCSArtifactStore,
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


def test_local_store_serializes_concurrent_create_only_writes(tmp_path, monkeypatch):
    store = LocalArtifactStore(tmp_path)
    uri = "gs://bucket/race.bin"
    object_path = tmp_path / "bucket" / "race.bin"
    original_write_bytes = Path.write_bytes
    first_write_entered = threading.Event()
    second_write_entered = threading.Event()
    release_writes = threading.Event()
    second_started = threading.Event()
    call_lock = threading.Lock()
    write_calls = 0

    def blocking_write_bytes(path, data):
        nonlocal write_calls
        if path == object_path:
            with call_lock:
                write_calls += 1
                call_number = write_calls
            if call_number == 1:
                first_write_entered.set()
            elif call_number == 2:
                second_write_entered.set()
            assert release_writes.wait(timeout=5)
        return original_write_bytes(path, data)

    def attempt(data):
        try:
            return "ok", store.put_bytes(uri, data, if_generation_match=0)
        except GenerationConflict:
            return "conflict", None

    def attempt_second():
        second_started.set()
        return attempt(b"second")

    monkeypatch.setattr(Path, "write_bytes", blocking_write_bytes)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(attempt, b"first")
        second = None
        try:
            assert first_write_entered.wait(timeout=2)
            second = executor.submit(attempt_second)
            assert second_started.wait(timeout=2)
            second_write_entered.wait(timeout=1)
        finally:
            release_writes.set()

        first_status, first_ref = first.result(timeout=5)
        assert second is not None
        second_status, second_ref = second.result(timeout=5)

    assert first_status == "ok"
    assert first_ref is not None
    assert second_status == "conflict"
    assert second_ref is None
    assert store.read_bytes(uri, generation=first_ref.generation) == b"first"


def test_local_store_exact_generation_read_blocks_replacement(tmp_path, monkeypatch):
    store = LocalArtifactStore(tmp_path)
    uri = "gs://bucket/current.bin"
    original = store.put_bytes(uri, b"old", if_generation_match=0)
    object_path = tmp_path / "bucket" / "current.bin"
    original_read_bytes = Path.read_bytes
    original_write_bytes = Path.write_bytes
    read_entered = threading.Event()
    release_read = threading.Event()
    writer_started = threading.Event()
    writer_write_entered = threading.Event()
    writer_finished = threading.Event()
    blocked_once = False
    gate_lock = threading.Lock()

    def blocking_read_bytes(path):
        nonlocal blocked_once
        should_block = False
        if path == object_path:
            with gate_lock:
                if not blocked_once:
                    blocked_once = True
                    should_block = True
        if should_block:
            read_entered.set()
            assert release_read.wait(timeout=5)
        return original_read_bytes(path)

    def observed_write_bytes(path, data):
        if path == object_path:
            writer_write_entered.set()
        return original_write_bytes(path, data)

    def replace_bytes():
        writer_started.set()
        try:
            return store.put_bytes(
                uri,
                b"new",
                if_generation_match=original.generation,
            )
        finally:
            writer_finished.set()

    monkeypatch.setattr(Path, "read_bytes", blocking_read_bytes)
    monkeypatch.setattr(Path, "write_bytes", observed_write_bytes)
    with ThreadPoolExecutor(max_workers=2) as executor:
        reader = executor.submit(store.read_bytes, uri, original.generation)
        writer = None
        try:
            assert read_entered.wait(timeout=2)
            writer = executor.submit(replace_bytes)
            assert writer_started.wait(timeout=2)
            writer_write_entered.wait(timeout=1)
            writer_finished.wait(timeout=1)
        finally:
            release_read.set()

        read_result = reader.result(timeout=5)
        assert writer is not None
        updated = writer.result(timeout=5)

    assert read_result == b"old"
    assert store.read_bytes(uri, generation=updated.generation) == b"new"


@pytest.mark.parametrize(
    "uri",
    [
        "gs://bucket/..\\..\\escape.bin",
        "gs://bucket//escape.bin",
        "gs://bucket/./escape.bin",
        "gs://bucket/../escape.bin",
        "gs://bucket\\escape/object.bin",
        "gs://C:/escape.bin",
    ],
)
def test_local_store_rejects_unsafe_uri_identities(tmp_path, uri):
    store = LocalArtifactStore(tmp_path)

    with pytest.raises(ValueError):
        store.put_bytes(uri, b"escape", if_generation_match=0)


def test_local_store_rejects_existing_symlink_escape(tmp_path):
    root = tmp_path / "store"
    bucket_root = root / "bucket"
    outside = tmp_path / "outside"
    bucket_root.mkdir(parents=True)
    outside.mkdir()
    link = bucket_root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    store = LocalArtifactStore(root)
    with pytest.raises(ValueError, match="outside local artifact bucket root"):
        store.put_bytes(
            "gs://bucket/link/escape.bin",
            b"escape",
            if_generation_match=0,
        )

    assert not (outside / "escape.bin").exists()


def test_local_store_preserves_bucket_root_and_trailing_prefix_listing(tmp_path):
    store = LocalArtifactStore(tmp_path)
    expected = store.put_bytes("gs://bucket/models/model.joblib", b"model")

    assert store.list("gs://bucket") == [expected]
    assert store.list("gs://bucket/") == [expected]
    assert store.list("gs://bucket/models/") == [expected]


class _StatefulFakeBlob:
    def __init__(self, bucket_name, name, client):
        self.bucket_name = bucket_name
        self.name = name
        self.client = client
        self.metadata = None
        self.generation = None
        self.size = None

    @property
    def key(self):
        return self.bucket_name, self.name

    def upload_from_string(self, data, if_generation_match=None):
        self.client.upload_string_preconditions.append(if_generation_match)
        self._upload(bytes(data), if_generation_match)

    def upload_from_filename(self, filename, if_generation_match=None):
        self.client.upload_filename_arguments.append(
            (filename, if_generation_match)
        )
        self._upload(Path(filename).read_bytes(), if_generation_match)

    def download_as_bytes(self, if_generation_match=None):
        self.client.download_bytes_preconditions.append(if_generation_match)
        return self._download(if_generation_match)

    def download_to_filename(self, filename, if_generation_match=None):
        self.client.download_filename_arguments.append(
            (filename, if_generation_match)
        )
        Path(filename).write_bytes(self._download(if_generation_match))

    def reload(self):
        self._load()

    def _upload(self, data, expected):
        current = self.client.objects.get(self.key, {}).get("generation", 0)
        if expected is not None and expected != current:
            raise PreconditionFailed("generation mismatch")
        self.client.objects[self.key] = {
            "data": data,
            "metadata": dict(self.metadata or {}),
            "generation": current + 1,
        }
        self._load()

    def _download(self, expected):
        state = self._load()
        if expected is not None and expected != state["generation"]:
            raise PreconditionFailed("generation mismatch")
        return state["data"]

    def _load(self):
        state = self.client.objects[self.key]
        self.metadata = dict(state["metadata"])
        self.generation = state["generation"]
        self.size = len(state["data"])
        return state


class _StatefulFakeBucket:
    def __init__(self, name, client):
        self.name = name
        self.client = client

    def blob(self, name):
        return _StatefulFakeBlob(self.name, name, self.client)


class _StatefulFakeStorageClient:
    def __init__(self):
        self.objects = {}
        self.upload_string_preconditions = []
        self.upload_filename_arguments = []
        self.download_bytes_preconditions = []
        self.download_filename_arguments = []
        self.list_arguments = []

    def bucket(self, name):
        return _StatefulFakeBucket(name, self)

    def list_blobs(self, bucket_name, prefix):
        self.list_arguments.append((bucket_name, prefix))
        for bucket, name in sorted(self.objects):
            if bucket == bucket_name and name.startswith(prefix):
                blob = _StatefulFakeBlob(bucket, name, self)
                blob.reload()
                yield blob

    def seed(self, uri, data, metadata):
        remainder = uri.removeprefix("gs://")
        bucket, name = remainder.split("/", 1)
        self.objects[(bucket, name)] = {
            "data": data,
            "metadata": dict(metadata),
            "generation": 1,
        }


def test_gcs_store_persists_sha_and_uses_exact_byte_generation_arguments():
    client = _StatefulFakeStorageClient()
    store = GCSArtifactStore(client)
    data = b"\x00model"

    ref = store.put_bytes(
        "gs://bucket/models/model.joblib",
        data,
        if_generation_match=0,
    )

    assert ref.sha256 == hashlib.sha256(data).hexdigest()
    assert client.objects[("bucket", "models/model.joblib")]["metadata"] == {
        "sha256": ref.sha256
    }
    assert client.upload_string_preconditions == [0]
    assert store.read_bytes(ref.uri, generation=ref.generation) == data
    assert client.download_bytes_preconditions == [1]
    assert store.list("gs://bucket/models/") == [ref]
    assert client.list_arguments == [("bucket", "models/")]


def test_gcs_store_preserves_file_bytes_and_exact_generation_arguments(tmp_path):
    client = _StatefulFakeStorageClient()
    store = GCSArtifactStore(client)
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    source.write_bytes(b"artifact")

    ref = store.upload_file(
        source,
        "gs://bucket/files/artifact.bin",
        if_generation_match=0,
    )
    store.download_file(ref.uri, target, generation=ref.generation)

    assert target.read_bytes() == b"artifact"
    assert ref.sha256 == hashlib.sha256(b"artifact").hexdigest()
    assert client.upload_filename_arguments == [(str(source), 0)]
    assert client.download_filename_arguments == [(str(target), 1)]


def test_gcs_store_converts_precondition_failures():
    store = GCSArtifactStore(_StatefulFakeStorageClient())
    ref = store.put_bytes("gs://bucket/object", b"first", if_generation_match=0)

    with pytest.raises(GenerationConflict):
        store.put_bytes("gs://bucket/object", b"second", if_generation_match=0)
    with pytest.raises(GenerationConflict):
        store.read_bytes(ref.uri, generation="999")


@pytest.mark.parametrize("uri", ["file:///tmp/object", "https://bucket/object"])
def test_gcs_store_rejects_non_gs_uris(uri):
    store = GCSArtifactStore(_StatefulFakeStorageClient())

    with pytest.raises(ValueError):
        store.get_ref(uri)
    with pytest.raises(ValueError):
        store.list(uri)


def test_gcs_store_never_reuses_object_missing_checksum_metadata():
    client = _StatefulFakeStorageClient()
    client.seed("gs://bucket/legacy/object", b"same", metadata={})
    store = GCSArtifactStore(client)

    with pytest.raises(ValueError, match="sha256 metadata"):
        store.get_ref("gs://bucket/legacy/object")
    with pytest.raises(ValueError, match="sha256 metadata"):
        put_immutable_or_verify(store, "gs://bucket/legacy/object", b"same")


def test_gcs_immutable_byte_retry_rehashes_exact_existing_generation():
    intended = b"same"
    stored = b"evil"
    assert len(stored) == len(intended)
    uri = "gs://bucket/forged/bytes.bin"
    client = _StatefulFakeStorageClient()
    client.seed(
        uri,
        stored,
        metadata={"sha256": hashlib.sha256(intended).hexdigest()},
    )
    store = GCSArtifactStore(client)

    with pytest.raises(GenerationConflict, match="different bytes"):
        put_immutable_or_verify(store, uri, intended)

    assert client.download_bytes_preconditions == [1]


def test_gcs_immutable_file_retry_rehashes_exact_existing_generation(tmp_path):
    intended = b"same"
    stored = b"evil"
    assert len(stored) == len(intended)
    source = tmp_path / "intended.bin"
    source.write_bytes(intended)
    uri = "gs://bucket/forged/file.bin"
    client = _StatefulFakeStorageClient()
    client.seed(
        uri,
        stored,
        metadata={"sha256": hashlib.sha256(intended).hexdigest()},
    )
    store = GCSArtifactStore(client)

    with pytest.raises(GenerationConflict, match="different bytes"):
        upload_file_immutable_or_verify(store, source, uri)

    assert len(client.download_filename_arguments) == 1
    assert client.download_filename_arguments[0][1] == 1


def test_gcs_store_preserves_valid_colon_object_names():
    store = GCSArtifactStore(_StatefulFakeStorageClient())
    uri = "gs://bucket/reports/2026-07-20T00:00:00Z.json"

    ref = store.put_bytes(uri, b"{}", if_generation_match=0)

    assert ref.uri == uri
    assert store.read_bytes(uri, generation=ref.generation) == b"{}"
