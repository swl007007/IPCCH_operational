import pytest

from cloud.common.object_store import (
    GenerationConflict,
    GCSObjectStore,
    LocalObjectStore,
)


class FakePreconditionFailed(Exception):
    pass


class FakeBlob:
    def __init__(self, bucket_name, name, client):
        self.bucket_name = bucket_name
        self.name = name
        self.client = client
        self.generation = None

    def upload_from_string(self, content, content_type=None, if_generation_match=None):
        key = (self.bucket_name, self.name)
        current = self.client.generations.get(key, 0)
        if if_generation_match is not None and int(if_generation_match) != current:
            raise FakePreconditionFailed("generation mismatch")
        self.client.objects[key] = content
        self.client.generations[key] = current + 1
        self.generation = self.client.generations[key]

    def download_as_text(self):
        return self.client.objects[(self.bucket_name, self.name)]

    def rewrite(self, source_blob, if_generation_match=None):
        self.upload_from_string(
            source_blob.download_as_text(), if_generation_match=if_generation_match
        )
        return None, None, None


class FakeBucket:
    def __init__(self, name, client):
        self.name = name
        self.client = client

    def blob(self, name):
        return FakeBlob(self.name, name, self.client)

    def copy_blob(self, source_blob, target_bucket, new_name, if_generation_match=None):
        target = target_bucket.blob(new_name)
        target.rewrite(source_blob, if_generation_match=if_generation_match)
        return target


class FakeStorageClient:
    def __init__(self):
        self.objects = {}
        self.generations = {}

    def bucket(self, name):
        return FakeBucket(name, self)

    def list_blobs(self, bucket_name, prefix):
        for bucket, name in sorted(self.objects):
            if bucket == bucket_name and name.startswith(prefix):
                yield FakeBlob(bucket, name, self)


def test_local_object_store_write_read_list_and_copy(tmp_path):
    store = LocalObjectStore(tmp_path)

    first = store.write_text("gs://bucket/runs/run-1/a.txt", "alpha")
    assert first.generation == "1"
    assert store.read_text("gs://bucket/runs/run-1/a.txt") == "alpha"
    assert store.list("gs://bucket/runs/run-1/") == ["gs://bucket/runs/run-1/a.txt"]

    copied = store.copy(
        "gs://bucket/runs/run-1/a.txt", "gs://bucket/released/202604/a.txt"
    )
    assert copied.generation == "1"
    assert store.read_text("gs://bucket/released/202604/a.txt") == "alpha"


def test_generation_precondition_blocks_overwrite(tmp_path):
    store = LocalObjectStore(tmp_path)
    store.write_text("gs://bucket/released/202604/release_manifest.json", "{}")

    with pytest.raises(GenerationConflict):
        store.write_text(
            "gs://bucket/released/202604/release_manifest.json",
            '{"status":"current"}',
            if_generation_match=0,
        )


def test_generation_precondition_allows_expected_generation(tmp_path):
    store = LocalObjectStore(tmp_path)
    first = store.write_text("gs://bucket/object.txt", "one")
    second = store.write_text(
        "gs://bucket/object.txt", "two", if_generation_match=first.generation
    )

    assert second.generation == "2"
    assert store.read_text("gs://bucket/object.txt") == "two"


def test_gcs_object_store_uses_storage_client_generation_and_prefix_semantics():
    client = FakeStorageClient()
    store = GCSObjectStore(client)

    first = store.write_text("gs://bucket/runs/run-1/a.txt", "alpha")
    assert first.generation == "1"
    assert store.read_text("gs://bucket/runs/run-1/a.txt") == "alpha"
    assert store.list("gs://bucket/runs/run-1/") == ["gs://bucket/runs/run-1/a.txt"]

    copied = store.copy(
        "gs://bucket/runs/run-1/a.txt",
        "gs://bucket/released/202604/a.txt",
        if_generation_match=0,
    )
    assert copied.generation == "1"
    assert store.read_text("gs://bucket/released/202604/a.txt") == "alpha"
