from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class GenerationConflict(RuntimeError):
    """Raised when an object generation precondition is not met."""


@dataclass(frozen=True)
class ObjectMetadata:
    uri: str
    generation: str


class ObjectStore(Protocol):
    def write_text(
        self, uri: str, content: str, *, if_generation_match: str | int | None = None
    ) -> ObjectMetadata: ...

    def read_text(self, uri: str) -> str: ...

    def get_metadata(self, uri: str) -> ObjectMetadata | None: ...

    def list(self, prefix_uri: str) -> list[str]: ...

    def copy(
        self,
        source_uri: str,
        target_uri: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectMetadata: ...


class LocalObjectStore:
    """Filesystem-backed fake object store with GCS-like generation checks."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._generations: dict[str, int] = {}
        self._write_order: list[str] = []

    def write_text(
        self, uri: str, content: str, *, if_generation_match: str | int | None = None
    ) -> ObjectMetadata:
        self._check_generation(uri, if_generation_match)
        path = self._path_for_uri(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        next_generation = self._generations.get(uri, 0) + 1
        self._generations[uri] = next_generation
        if uri not in self._write_order:
            self._write_order.append(uri)
        return ObjectMetadata(uri=uri, generation=str(next_generation))

    def read_text(self, uri: str) -> str:
        return self._path_for_uri(uri).read_text(encoding="utf-8")

    def get_metadata(self, uri: str) -> ObjectMetadata | None:
        generation = self._generations.get(uri)
        if generation is None:
            return None
        return ObjectMetadata(uri=uri, generation=str(generation))

    def list(self, prefix_uri: str) -> list[str]:
        prefix_path = self._path_for_uri(prefix_uri)
        if not prefix_path.exists():
            return []
        return [uri for uri in self._write_order if uri.startswith(prefix_uri)]

    def copy(
        self,
        source_uri: str,
        target_uri: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectMetadata:
        return self.write_text(
            target_uri,
            self.read_text(source_uri),
            if_generation_match=if_generation_match,
        )

    def _check_generation(self, uri: str, expected: str | int | None) -> None:
        if expected is None:
            return
        current = self._generations.get(uri, 0)
        if int(expected) != current:
            raise GenerationConflict(
                f"generation precondition failed for {uri}: expected {expected}, current {current}"
            )

    def _path_for_uri(self, uri: str) -> Path:
        if not uri.startswith("gs://"):
            raise ValueError(f"LocalObjectStore only accepts gs:// URIs: {uri}")
        return self.root / uri.removeprefix("gs://")


class GCSObjectStore:
    """Google Cloud Storage-backed object store using generation preconditions."""

    def __init__(self, client):
        self.client = client

    @classmethod
    def from_default(cls) -> "GCSObjectStore":
        from google.cloud import storage

        return cls(storage.Client())

    def write_text(
        self, uri: str, content: str, *, if_generation_match: str | int | None = None
    ) -> ObjectMetadata:
        bucket_name, blob_name = _parse_gcs_uri(uri)
        blob = self.client.bucket(bucket_name).blob(blob_name)
        try:
            blob.upload_from_string(
                content,
                content_type="text/plain; charset=utf-8",
                if_generation_match=_coerce_generation(if_generation_match),
            )
        except Exception as exc:
            if _is_generation_precondition_error(exc):
                raise GenerationConflict(str(exc)) from exc
            raise
        return ObjectMetadata(uri=uri, generation=str(blob.generation))

    def read_text(self, uri: str) -> str:
        bucket_name, blob_name = _parse_gcs_uri(uri)
        return self.client.bucket(bucket_name).blob(blob_name).download_as_text()

    def get_metadata(self, uri: str) -> ObjectMetadata | None:
        bucket_name, blob_name = _parse_gcs_uri(uri)
        blob = self.client.bucket(bucket_name).blob(blob_name)
        try:
            blob.reload()
        except Exception as exc:
            if _is_not_found_error(exc):
                return None
            raise
        return ObjectMetadata(uri=uri, generation=str(blob.generation))

    def list(self, prefix_uri: str) -> list[str]:
        bucket_name, prefix = _parse_gcs_uri(prefix_uri)
        return [
            f"gs://{bucket_name}/{blob.name}"
            for blob in self.client.list_blobs(bucket_name, prefix=prefix)
        ]

    def copy(
        self,
        source_uri: str,
        target_uri: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectMetadata:
        source_bucket_name, source_blob_name = _parse_gcs_uri(source_uri)
        target_bucket_name, target_blob_name = _parse_gcs_uri(target_uri)
        source_bucket = self.client.bucket(source_bucket_name)
        target_bucket = self.client.bucket(target_bucket_name)
        source_blob = source_bucket.blob(source_blob_name)
        try:
            copied = target_bucket.copy_blob(
                source_blob,
                target_bucket,
                target_blob_name,
                if_generation_match=_coerce_generation(if_generation_match),
            )
        except Exception as exc:
            if _is_generation_precondition_error(exc):
                raise GenerationConflict(str(exc)) from exc
            raise
        return ObjectMetadata(uri=target_uri, generation=str(copied.generation))


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"expected gs:// URI: {uri}")
    without_scheme = uri.removeprefix("gs://")
    bucket, sep, blob = without_scheme.partition("/")
    if not bucket or not sep:
        raise ValueError(f"expected gs://bucket/object URI: {uri}")
    return bucket, blob


def _coerce_generation(value: str | int | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _is_generation_precondition_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"PreconditionFailed", "FakePreconditionFailed"}


def _is_not_found_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"NotFound", "FakeNotFound"}
