from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping


_IMAGE_DIGEST_RE = re.compile(r".+@sha256:[A-Fa-f0-9]{64}$")
_SHA256_HEX_RE = re.compile(r"^[A-Fa-f0-9]{64}$")


class ImmutableReferenceError(ValueError):
    """Raised when a required artifact lacks immutable evidence."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_digest_pinned_image(image_uri: str) -> bool:
    return bool(_IMAGE_DIGEST_RE.fullmatch(image_uri or ""))


def has_immutable_reference(artifact: Mapping[str, Any]) -> bool:
    checksum = artifact.get("checksum")
    if checksum and _SHA256_HEX_RE.fullmatch(str(checksum)):
        return artifact.get("checksum_algorithm") in (None, "sha256")

    for field in ("generation", "version_id", "image_digest", "model_version"):
        if artifact.get(field):
            return True
    return False


def require_immutable_reference(artifact: Mapping[str, Any]) -> None:
    if artifact.get("required") and not has_immutable_reference(artifact):
        artifact_id = artifact.get("artifact_id", "<unknown>")
        raise ImmutableReferenceError(
            f"required artifact {artifact_id} lacks immutable reference"
        )


def normalize_gcs_ref(
    uri: str,
    *,
    generation: str | None = None,
    checksum: str | None = None,
    checksum_algorithm: str | None = None,
) -> dict[str, str]:
    ref = {"uri": uri}
    if generation is not None:
        ref["generation"] = str(generation)
    if checksum is not None:
        ref["checksum"] = checksum
    if checksum_algorithm is not None:
        ref["checksum_algorithm"] = checksum_algorithm
    return ref
