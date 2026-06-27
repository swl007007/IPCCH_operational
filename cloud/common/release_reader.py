from __future__ import annotations

import json

from cloud.common.object_store import ObjectStore


class ReleaseManifestError(ValueError):
    """Raised when consumers attempt to bypass the release manifest contract."""


def read_release_manifest(store: ObjectStore, manifest_uri: str) -> dict:
    if not manifest_uri.endswith(
        "/release_manifest.json"
    ) and not manifest_uri.endswith("release_manifest.json"):
        raise ReleaseManifestError(
            "consumers must read release_manifest.json explicitly"
        )
    manifest = json.loads(store.read_text(manifest_uri))
    if manifest.get("status") != "current":
        raise ReleaseManifestError("release manifest is not current")
    return manifest
