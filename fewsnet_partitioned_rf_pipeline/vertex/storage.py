"""Binary-safe artifact storage with exact generation preconditions."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from google.api_core.exceptions import PreconditionFailed

from fewsnet_partitioned_rf_pipeline.core import ObjectRef


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class GenerationConflict(RuntimeError):
    """Raised when an object generation precondition is not met."""


class ArtifactStore(Protocol):
    """Storage boundary for immutable and generation-guarded artifacts."""

    def put_bytes(
        self,
        uri: str,
        data: bytes,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef: ...

    def read_bytes(self, uri: str, generation: str | int | None = None) -> bytes: ...

    def put_text(
        self,
        uri: str,
        content: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef: ...

    def read_text(self, uri: str, generation: str | int | None = None) -> str: ...

    def upload_file(
        self,
        path: Path,
        uri: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef: ...

    def download_file(
        self,
        uri: str,
        path: Path,
        generation: str | int | None = None,
    ) -> None: ...

    def get_ref(self, uri: str) -> ObjectRef: ...

    def list(self, prefix: str) -> list[ObjectRef]: ...


class LocalArtifactStore:
    """Filesystem-backed artifact store with GCS-like generation checks."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._generations: dict[str, int] = {}

    def put_bytes(
        self,
        uri: str,
        data: bytes,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef:
        path = self._path_for_uri(uri)
        current = self._current_generation(uri, path)
        _check_generation(current, if_generation_match, uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        generation = current + 1
        self._generations[uri] = generation
        return _object_ref(uri, generation, data)

    def read_bytes(self, uri: str, generation: str | int | None = None) -> bytes:
        path = self._path_for_uri(uri)
        if not path.is_file():
            raise FileNotFoundError(uri)
        current = self._current_generation(uri, path)
        _check_generation(current, generation, uri)
        return path.read_bytes()

    def put_text(
        self,
        uri: str,
        content: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef:
        return self.put_bytes(
            uri,
            content.encode("utf-8"),
            if_generation_match=if_generation_match,
        )

    def read_text(self, uri: str, generation: str | int | None = None) -> str:
        return self.read_bytes(uri, generation=generation).decode("utf-8")

    def upload_file(
        self,
        path: Path,
        uri: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef:
        source = Path(path)
        target = self._path_for_uri(uri)
        current = self._current_generation(uri, target)
        _check_generation(current, if_generation_match, uri)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        generation = current + 1
        self._generations[uri] = generation
        return _file_ref(uri, generation, target)

    def download_file(
        self,
        uri: str,
        path: Path,
        generation: str | int | None = None,
    ) -> None:
        target = Path(path)
        source = self._path_for_uri(uri)
        if not source.is_file():
            raise FileNotFoundError(uri)
        current = self._current_generation(uri, source)
        _check_generation(current, generation, uri)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def get_ref(self, uri: str) -> ObjectRef:
        path = self._path_for_uri(uri)
        if not path.is_file():
            raise FileNotFoundError(uri)
        generation = self._current_generation(uri, path)
        return _file_ref(uri, generation, path)

    def list(self, prefix: str) -> list[ObjectRef]:
        bucket, object_prefix = _parse_gs_uri(prefix, allow_empty_object=True)
        bucket_root = self.root / bucket
        if not bucket_root.is_dir():
            return []

        refs = []
        for path in bucket_root.rglob("*"):
            if not path.is_file():
                continue
            object_name = path.relative_to(bucket_root).as_posix()
            if object_name.startswith(object_prefix):
                refs.append(self.get_ref(f"gs://{bucket}/{object_name}"))
        return sorted(refs, key=lambda ref: ref.uri)

    def _current_generation(self, uri: str, path: Path) -> int:
        generation = self._generations.get(uri)
        if generation is None and path.is_file():
            generation = 1
            self._generations[uri] = generation
        return generation or 0

    def _path_for_uri(self, uri: str) -> Path:
        bucket, object_name = _parse_gs_uri(uri)
        return self.root.joinpath(bucket, *PurePosixPath(object_name).parts)


class GCSArtifactStore:
    """Google Cloud Storage adapter using exact generation preconditions."""

    def __init__(self, client: Any):
        self.client = client

    @classmethod
    def from_default(cls) -> "GCSArtifactStore":
        from google.cloud import storage

        return cls(storage.Client())

    def put_bytes(
        self,
        uri: str,
        data: bytes,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef:
        blob = self._blob(uri)
        blob.metadata = {"sha256": hashlib.sha256(data).hexdigest()}
        expected = _coerce_generation(if_generation_match)
        try:
            blob.upload_from_string(data, if_generation_match=expected)
        except PreconditionFailed as exc:
            raise GenerationConflict(
                f"generation precondition failed for {uri}: expected {if_generation_match}"
            ) from exc
        return _blob_ref(uri, blob)

    def read_bytes(self, uri: str, generation: str | int | None = None) -> bytes:
        blob = self._blob(uri)
        try:
            return blob.download_as_bytes(
                if_generation_match=int(generation) if generation else None
            )
        except PreconditionFailed as exc:
            raise GenerationConflict(
                f"generation precondition failed while reading {uri}: expected {generation}"
            ) from exc

    def put_text(
        self,
        uri: str,
        content: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef:
        return self.put_bytes(
            uri,
            content.encode("utf-8"),
            if_generation_match=if_generation_match,
        )

    def read_text(self, uri: str, generation: str | int | None = None) -> str:
        return self.read_bytes(uri, generation=generation).decode("utf-8")

    def upload_file(
        self,
        path: Path,
        uri: str,
        *,
        if_generation_match: str | int | None = None,
    ) -> ObjectRef:
        source = Path(path)
        blob = self._blob(uri)
        blob.metadata = {"sha256": sha256_file(source)}
        expected = _coerce_generation(if_generation_match)
        try:
            blob.upload_from_filename(str(source), if_generation_match=expected)
        except PreconditionFailed as exc:
            raise GenerationConflict(
                f"generation precondition failed for {uri}: expected {if_generation_match}"
            ) from exc
        return _blob_ref(uri, blob)

    def download_file(
        self,
        uri: str,
        path: Path,
        generation: str | int | None = None,
    ) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        blob = self._blob(uri)
        try:
            blob.download_to_filename(
                str(target),
                if_generation_match=int(generation) if generation else None,
            )
        except PreconditionFailed as exc:
            raise GenerationConflict(
                f"generation precondition failed while reading {uri}: expected {generation}"
            ) from exc

    def get_ref(self, uri: str) -> ObjectRef:
        blob = self._blob(uri)
        blob.reload()
        return _blob_ref(uri, blob)

    def list(self, prefix: str) -> list[ObjectRef]:
        bucket, object_prefix = _parse_gs_uri(prefix, allow_empty_object=True)
        refs = [
            _blob_ref(f"gs://{bucket}/{blob.name}", blob)
            for blob in self.client.list_blobs(bucket, prefix=object_prefix)
        ]
        return sorted(refs, key=lambda ref: ref.uri)

    def _blob(self, uri: str):
        bucket, object_name = _parse_gs_uri(uri)
        return self.client.bucket(bucket).blob(object_name)


def put_immutable_or_verify(store: ArtifactStore, uri: str, data: bytes) -> ObjectRef:
    intended_sha256 = hashlib.sha256(data).hexdigest()
    try:
        return store.put_bytes(uri, data, if_generation_match=0)
    except GenerationConflict:
        existing = store.get_ref(uri)
        if existing.sha256 != intended_sha256 or existing.size_bytes != len(data):
            raise GenerationConflict(
                f"immutable object already exists with different bytes: {uri}"
            )
        return existing


def upload_file_immutable_or_verify(
    store: ArtifactStore, path: Path, uri: str
) -> ObjectRef:
    intended_sha256 = sha256_file(path)
    intended_size = path.stat().st_size
    try:
        return store.upload_file(path, uri, if_generation_match=0)
    except GenerationConflict:
        existing = store.get_ref(uri)
        if existing.sha256 != intended_sha256 or existing.size_bytes != intended_size:
            raise GenerationConflict(
                f"immutable object already exists with different bytes: {uri}"
            )
        return existing


def put_mutable_or_verify(
    store: ArtifactStore,
    uri: str,
    data: bytes,
    expected_generation: str | int,
) -> ObjectRef:
    intended_sha256 = hashlib.sha256(data).hexdigest()
    try:
        return store.put_bytes(
            uri,
            data,
            if_generation_match=expected_generation,
        )
    except GenerationConflict:
        existing = store.get_ref(uri)
        if existing.sha256 != intended_sha256 or existing.size_bytes != len(data):
            raise
        return existing


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_generation(current: int, expected: str | int | None, uri: str) -> None:
    if expected is not None and int(expected) != current:
        raise GenerationConflict(
            f"generation precondition failed for {uri}: expected {expected}, current {current}"
        )


def _object_ref(uri: str, generation: int, data: bytes) -> ObjectRef:
    return ObjectRef(
        uri=uri,
        generation=str(generation),
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )


def _file_ref(uri: str, generation: int, path: Path) -> ObjectRef:
    return ObjectRef(
        uri=uri,
        generation=str(generation),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _blob_ref(uri: str, blob: Any) -> ObjectRef:
    metadata = blob.metadata
    sha256 = metadata.get("sha256") if isinstance(metadata, dict) else None
    if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
        raise ValueError(f"missing or invalid sha256 metadata for {uri}")
    if blob.generation is None:
        raise ValueError(f"missing generation metadata for {uri}")
    if blob.size is None:
        raise ValueError(f"missing size metadata for {uri}")
    return ObjectRef(
        uri=uri,
        generation=str(blob.generation),
        sha256=sha256,
        size_bytes=int(blob.size),
    )


def _parse_gs_uri(
    uri: str, *, allow_empty_object: bool = False
) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"expected gs:// URI: {uri}")
    remainder = uri.removeprefix("gs://")
    bucket, separator, object_name = remainder.partition("/")
    if not bucket or bucket in {".", ".."}:
        raise ValueError(f"expected gs://bucket/object URI: {uri}")
    if not separator:
        if allow_empty_object:
            return bucket, ""
        raise ValueError(f"expected gs://bucket/object URI: {uri}")
    if not object_name:
        if allow_empty_object:
            return bucket, ""
        raise ValueError(f"expected gs://bucket/object URI: {uri}")
    parts = object_name.split("/")
    validated_parts = parts[:-1] if allow_empty_object and parts[-1] == "" else parts
    if any(part in {"", ".", ".."} for part in validated_parts):
        raise ValueError(f"invalid GCS object name in URI: {uri}")
    return bucket, object_name


def _coerce_generation(value: str | int | None) -> int | None:
    return int(value) if value is not None else None
