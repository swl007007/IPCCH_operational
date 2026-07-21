from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable

import pytest
from google.api_core.exceptions import NotFound

from fewsnet_partitioned_rf_pipeline.config import PARENT_MODEL_IDS
from fewsnet_partitioned_rf_pipeline.core import RegisteredModelVersion
from fewsnet_partitioned_rf_pipeline.vertex.registry import (
    mark_registered_versions_abandoned,
    register_candidate_version,
    resolve_parent_model,
    suite_version_alias,
)
from fewsnet_partitioned_rf_pipeline.vertex.storage import LocalArtifactStore


PROJECT_ID = "food-crisis-modeling"
REGION = "us-central1"
RUN_ROOT_URI = "gs://bucket/fewsnet_partitioned_rf/runs/run-001"
SUITE_VERSION = "FEWSNET PRF/202604__Git-A_Data-B_Run-C"
SUITE_ALIAS = "fewsnet-prf-202604-git-a-data-b-run-c"
IMAGE_DIGEST = f"sha256:{'a' * 64}"
IMAGE_URI = (
    "us-central1-docker.pkg.dev/food-crisis-modeling/fewsnet/"
    f"fewsnet-partitioned-rf@{IMAGE_DIGEST}"
)
SOURCE_GIT_COMMIT = "0123456789abcdef0123456789abcdef01234567"
VERSION_DESCRIPTION = "immutable FEWSNET candidate suite"


@dataclass
class FakeEnvironmentVariable:
    name: str
    value: str


@dataclass
class FakeContainerSpec:
    image_uri: str
    env: list[FakeEnvironmentVariable]


@dataclass
class FakeGcaResource:
    container_spec: FakeContainerSpec


@dataclass
class FakeVersionInfo:
    version_id: str
    model_resource_name: str
    version_aliases: list[str]


class FakeModel:
    def __init__(
        self,
        *,
        parent_resource_name: str,
        version_id: str,
        artifact_uri: str,
        image_uri: str,
        image_digest: str,
        source_git_commit: str,
        labels: dict[str, str],
        event_log: list[tuple[str, object]],
    ) -> None:
        self.resource_name = parent_resource_name
        self.version_id = version_id
        self.versioned_resource_name = (
            f"{parent_resource_name}@{version_id}"
        )
        self.uri = artifact_uri
        self.labels = dict(labels)
        self.gca_resource = FakeGcaResource(
            container_spec=FakeContainerSpec(
                image_uri=image_uri,
                env=[
                    FakeEnvironmentVariable(
                        "FEWSNET_CONTAINER_IMAGE_DIGEST",
                        image_digest,
                    ),
                    FakeEnvironmentVariable(
                        "FEWSNET_SOURCE_GIT_COMMIT",
                        source_git_commit,
                    ),
                ],
            )
        )
        self.update_calls: list[dict[str, str]] = []
        self._event_log = event_log

    def update(self, *, labels: dict[str, str]):
        self._event_log.append(("update", self.versioned_resource_name))
        self.update_calls.append(dict(labels))
        self.labels = dict(labels)
        return self


class FakeRegistry:
    def __init__(self, sdk: FakeSDK, parent_resource_name: str) -> None:
        self._sdk = sdk
        self._parent_resource_name = parent_resource_name

    def list_versions(self):
        self._sdk.event_log.append(
            ("list_versions", self._parent_resource_name)
        )
        if self._parent_resource_name in self._sdk.list_errors:
            raise self._sdk.list_errors[self._parent_resource_name]
        try:
            versions = self._sdk.parent_versions[self._parent_resource_name]
        except KeyError as exc:
            raise NotFound("parent model does not exist") from exc
        return list(versions.values())

    def get_version_info(self, version_alias: str):
        self._sdk.event_log.append(("get_version_info", version_alias))
        try:
            return self._sdk.parent_versions[self._parent_resource_name][
                version_alias
            ]
        except KeyError as exc:
            raise NotFound("version alias does not exist") from exc

    def update_version(
        self,
        version: str,
        version_description: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        assert version_description is None
        assert labels is not None
        version_resource_name = f"{self._parent_resource_name}@{version}"
        self._sdk.event_log.append(
            ("update_version", version_resource_name)
        )
        model = self._sdk.models[(self._parent_resource_name, version)]
        model.update_calls.append(dict(labels))
        model.labels = dict(labels)


class FakeModelBoundary:
    def __init__(self, sdk: FakeSDK) -> None:
        self._sdk = sdk

    def __call__(self, *, model_name: str, version: str):
        self._sdk.load_calls.append(
            {"model_name": model_name, "version": version}
        )
        self._sdk.event_log.append(("load", f"{model_name}@{version}"))
        return self._sdk.models[(model_name, version)]

    def upload(self, **kwargs):
        self._sdk.upload_calls.append(dict(kwargs))
        self._sdk.event_log.append(("upload", kwargs["display_name"]))
        if isinstance(self._sdk.upload_result, BaseException):
            raise self._sdk.upload_result
        assert self._sdk.upload_result is not None
        return self._sdk.upload_result


class FakeSDK:
    def __init__(self) -> None:
        self.event_log: list[tuple[str, object]] = []
        self.init_calls: list[dict[str, str]] = []
        self.registry_calls: list[str] = []
        self.upload_calls: list[dict[str, object]] = []
        self.load_calls: list[dict[str, str]] = []
        self.parent_versions: dict[str, dict[str, FakeVersionInfo]] = {}
        self.models: dict[tuple[str, str], FakeModel] = {}
        self.list_errors: dict[str, BaseException] = {}
        self.upload_result: FakeModel | BaseException | None = None
        self.Model = FakeModelBoundary(self)

    def init(self, *, project: str, location: str) -> None:
        self.init_calls.append({"project": project, "location": location})
        self.event_log.append(("init", (project, location)))

    def ModelRegistry(self, model: str):
        self.registry_calls.append(model)
        return FakeRegistry(self, model)

    def add_existing_version(
        self,
        *,
        model: FakeModel,
        version_alias: str,
    ) -> None:
        info = FakeVersionInfo(
            version_id=model.version_id,
            model_resource_name=model.resource_name,
            version_aliases=[version_alias, "default"],
        )
        self.parent_versions.setdefault(model.resource_name, {})[
            version_alias
        ] = info
        self.models[(model.resource_name, model.version_id)] = model


class RecordingLocalArtifactStore(LocalArtifactStore):
    def __init__(
        self,
        root: Path,
        event_log: list[tuple[str, object]],
    ) -> None:
        super().__init__(root)
        self._event_log = event_log

    def put_bytes(self, uri, data, *, if_generation_match=None):
        self._event_log.append(("persist", uri))
        return super().put_bytes(
            uri,
            data,
            if_generation_match=if_generation_match,
        )


def _parent_resource(horizon_key: str) -> str:
    return (
        f"projects/{PROJECT_ID}/locations/{REGION}/models/"
        f"{PARENT_MODEL_IDS[horizon_key]}"
    )


def _artifact_uri(horizon_key: str) -> str:
    return (
        "gs://bucket/fewsnet_partitioned_rf/suites/"
        f"{SUITE_VERSION}/models/{horizon_key}"
    )


def _candidate_labels(
    horizon_key: str,
    suite_label: str = SUITE_ALIAS,
    lifecycle: str = "candidate",
) -> dict[str, str]:
    return {
        "feature_month": "2026-04",
        "snapshot": "data-b",
        "horizon": horizon_key,
        "suite": suite_label,
        "lifecycle": lifecycle,
    }


def _model(
    sdk: FakeSDK,
    horizon_key: str,
    *,
    version_id: str = "7",
    artifact_uri: str | None = None,
    image_uri: str = IMAGE_URI,
    image_digest: str = IMAGE_DIGEST,
    labels: dict[str, str] | None = None,
) -> FakeModel:
    return FakeModel(
        parent_resource_name=_parent_resource(horizon_key),
        version_id=version_id,
        artifact_uri=artifact_uri or _artifact_uri(horizon_key),
        image_uri=image_uri,
        image_digest=image_digest,
        source_git_commit=SOURCE_GIT_COMMIT,
        labels=labels or _candidate_labels(horizon_key),
        event_log=sdk.event_log,
    )


def _register(
    *,
    tmp_path: Path,
    sdk: FakeSDK,
    horizon_key: str,
    callback: Callable[[RegisteredModelVersion], None],
    suite_version: str = SUITE_VERSION,
    labels: dict[str, str] | None = None,
) -> tuple[RegisteredModelVersion, RecordingLocalArtifactStore]:
    store = RecordingLocalArtifactStore(tmp_path / "store", sdk.event_log)
    result = register_candidate_version(
        project_id=PROJECT_ID,
        region=REGION,
        run_root_uri=RUN_ROOT_URI,
        suite_version=suite_version,
        horizon_key=horizon_key,
        artifact_uri=_artifact_uri(horizon_key),
        image_uri=IMAGE_URI,
        image_digest=IMAGE_DIGEST,
        source_git_commit=SOURCE_GIT_COMMIT,
        version_description=VERSION_DESCRIPTION,
        labels=labels
        or {
            "feature_month": "2026-04",
            "snapshot": "data-b",
        },
        store=store,
        update_run_manifest=callback,
        sdk=sdk,
    )
    return result, store


@pytest.mark.parametrize(
    ("suite_version", "expected"),
    [
        (SUITE_VERSION, SUITE_ALIAS),
        ("2026 / April__Suite", "v-2026-april-suite"),
        ("Already-valid", "already-valid"),
        ("a---b___c", "a-b-c"),
    ],
)
def test_suite_version_alias_applies_vertex_identifier_rules(
    suite_version,
    expected,
):
    assert suite_version_alias(suite_version) == expected


@pytest.mark.parametrize(
    "suite_version",
    [
        "---___///",
        "a" * 129,
        "1" + "a" * 126,
    ],
)
def test_suite_version_alias_rejects_empty_or_overlong_results(suite_version):
    with pytest.raises(ValueError, match="suite version alias"):
        suite_version_alias(suite_version)


def test_resolve_parent_model_treats_only_not_found_as_absence():
    horizon_key = "0m"
    parent_resource_name = _parent_resource(horizon_key)
    missing_sdk = FakeSDK()

    assert (
        resolve_parent_model(
            project_id=PROJECT_ID,
            region=REGION,
            horizon_key=horizon_key,
            sdk=missing_sdk,
        )
        is None
    )
    assert missing_sdk.init_calls == [
        {"project": PROJECT_ID, "location": REGION}
    ]

    failing_sdk = FakeSDK()
    failing_sdk.list_errors[parent_resource_name] = RuntimeError(
        "permission denied"
    )
    with pytest.raises(RuntimeError, match="permission denied"):
        resolve_parent_model(
            project_id=PROJECT_ID,
            region=REGION,
            horizon_key=horizon_key,
            sdk=failing_sdk,
        )


@pytest.mark.parametrize("horizon_key", ["0m", "6m", "12m"])
@pytest.mark.parametrize("parent_exists", [False, True])
def test_register_candidate_version_uses_exact_vertex_upload_contract(
    tmp_path,
    horizon_key,
    parent_exists,
):
    sdk = FakeSDK()
    parent_resource_name = _parent_resource(horizon_key)
    if parent_exists:
        sdk.parent_versions[parent_resource_name] = {}
    uploaded = _model(sdk, horizon_key)
    sdk.upload_result = uploaded
    callback_results: list[RegisteredModelVersion] = []

    def update_run_manifest(result):
        sdk.event_log.append(("manifest", result.horizon_key))
        callback_results.append(result)

    result, store = _register(
        tmp_path=tmp_path,
        sdk=sdk,
        horizon_key=horizon_key,
        callback=update_run_manifest,
    )

    expected_labels = _candidate_labels(horizon_key)
    assert sdk.init_calls == [{"project": PROJECT_ID, "location": REGION}]
    assert sdk.upload_calls == [
        {
            "display_name": PARENT_MODEL_IDS[horizon_key],
            "artifact_uri": _artifact_uri(horizon_key),
            "serving_container_image_uri": IMAGE_URI,
            "serving_container_predict_route": "/predict",
            "serving_container_health_route": "/health",
            "serving_container_ports": [8080],
            "serving_container_environment_variables": {
                "FEWSNET_CONTAINER_IMAGE_DIGEST": IMAGE_DIGEST,
                "FEWSNET_SOURCE_GIT_COMMIT": SOURCE_GIT_COMMIT,
            },
            "labels": expected_labels,
            "parent_model": (
                parent_resource_name if parent_exists else None
            ),
            "model_id": (
                None if parent_exists else PARENT_MODEL_IDS[horizon_key]
            ),
            "is_default_version": not parent_exists,
            "version_aliases": [SUITE_ALIAS],
            "version_description": VERSION_DESCRIPTION,
            "sync": True,
        }
    ]
    assert "version_id" not in sdk.upload_calls[0]
    assert "production" not in sdk.upload_calls[0]["version_aliases"]
    assert result == RegisteredModelVersion(
        horizon_key=horizon_key,
        parent_model_resource_name=uploaded.resource_name,
        version_resource_name=uploaded.versioned_resource_name,
        version_id=uploaded.version_id,
        suite_version_alias=SUITE_ALIAS,
        artifact_uri=_artifact_uri(horizon_key),
    )
    evidence_uri = f"{RUN_ROOT_URI}/registry/{horizon_key}.json"
    assert json.loads(store.read_text(evidence_uri)) == asdict(result)
    assert callback_results == [result]
    assert sdk.event_log[-2:] == [
        ("persist", evidence_uri),
        ("manifest", horizon_key),
    ]


def test_long_suite_alias_uses_deterministic_label_projection(tmp_path):
    suite_version = "FEWSNET-" + "Long-Suite-Identity-" * 5
    suite_alias = suite_version_alias(suite_version)
    expected_suite_label = (
        f"{suite_alias[:50].rstrip('-')}-"
        f"{hashlib.sha256(suite_alias.encode()).hexdigest()[:12]}"
    )
    sdk = FakeSDK()
    sdk.upload_result = _model(sdk, "0m")

    _register(
        tmp_path=tmp_path,
        sdk=sdk,
        horizon_key="0m",
        callback=lambda result: None,
        suite_version=suite_version,
    )

    assert len(suite_alias) <= 128
    assert len(expected_suite_label) <= 63
    assert sdk.upload_calls[0]["version_aliases"] == [suite_alias]
    assert sdk.upload_calls[0]["labels"]["suite"] == expected_suite_label


@pytest.mark.parametrize(
    ("reserved_key", "invalid_value"),
    [
        ("horizon", "12m"),
        ("suite", "someone-else"),
        ("lifecycle", "production"),
    ],
)
def test_caller_labels_cannot_override_reserved_candidate_identity(
    tmp_path,
    reserved_key,
    invalid_value,
):
    sdk = FakeSDK()
    sdk.upload_result = _model(sdk, "0m")
    labels = {
        "feature_month": "2026-04",
        reserved_key: invalid_value,
    }

    with pytest.raises(ValueError, match=reserved_key):
        _register(
            tmp_path=tmp_path,
            sdk=sdk,
            horizon_key="0m",
            callback=lambda result: None,
            labels=labels,
        )

    assert sdk.upload_calls == []


def test_exact_retry_reuses_version_and_restores_candidate_lifecycle(
    tmp_path,
):
    horizon_key = "6m"
    sdk = FakeSDK()
    existing = _model(
        sdk,
        horizon_key,
        labels=_candidate_labels(
            horizon_key,
            lifecycle="abandoned",
        ),
    )
    sdk.add_existing_version(model=existing, version_alias=SUITE_ALIAS)
    callback_results: list[RegisteredModelVersion] = []

    result, store = _register(
        tmp_path=tmp_path,
        sdk=sdk,
        horizon_key=horizon_key,
        callback=callback_results.append,
    )

    assert sdk.upload_calls == []
    assert sdk.load_calls == [
        {
            "model_name": existing.resource_name,
            "version": existing.version_id,
        }
    ]
    assert existing.update_calls == [_candidate_labels(horizon_key)]
    assert existing.labels["feature_month"] == "2026-04"
    assert result.version_resource_name == existing.versioned_resource_name
    evidence_uri = f"{RUN_ROOT_URI}/registry/{horizon_key}.json"
    assert json.loads(store.read_text(evidence_uri)) == asdict(result)
    assert callback_results == [result]


def test_retry_restores_lifecycle_through_exact_version_registry_api(
    tmp_path,
):
    horizon_key = "6m"
    sdk = FakeSDK()
    parent = _model(
        sdk,
        horizon_key,
        version_id="1",
        labels=_candidate_labels(horizon_key, lifecycle="production"),
    )
    candidate = _model(
        sdk,
        horizon_key,
        version_id="7",
        labels=_candidate_labels(horizon_key, lifecycle="abandoned"),
    )
    sdk.models[(parent.resource_name, parent.version_id)] = parent
    sdk.add_existing_version(model=candidate, version_alias=SUITE_ALIAS)

    def update_parent(*, labels):
        sdk.event_log.append(("parent_update", parent.resource_name))
        parent.update_calls.append(dict(labels))
        parent.labels = dict(labels)
        return candidate

    candidate.update = update_parent

    result, _ = _register(
        tmp_path=tmp_path,
        sdk=sdk,
        horizon_key=horizon_key,
        callback=lambda registered: None,
    )

    assert (
        "update_version",
        candidate.versioned_resource_name,
    ) in sdk.event_log
    assert candidate.update_calls == [_candidate_labels(horizon_key)]
    assert candidate.labels["lifecycle"] == "candidate"
    assert parent.update_calls == []
    assert parent.labels["lifecycle"] == "production"
    assert result.version_resource_name == candidate.versioned_resource_name


def test_retry_rejects_source_git_commit_mismatch_before_side_effects(
    tmp_path,
):
    horizon_key = "6m"
    sdk = FakeSDK()
    existing = _model(sdk, horizon_key)
    environment = existing.gca_resource.container_spec.env
    source_commit = next(
        item
        for item in environment
        if item.name == "FEWSNET_SOURCE_GIT_COMMIT"
    )
    source_commit.value = "f" * 40
    sdk.add_existing_version(model=existing, version_alias=SUITE_ALIAS)
    callback_results = []

    with pytest.raises(ValueError, match="source Git commit"):
        _register(
            tmp_path=tmp_path,
            sdk=sdk,
            horizon_key=horizon_key,
            callback=callback_results.append,
        )

    assert sdk.upload_calls == []
    assert existing.update_calls == []
    assert callback_results == []
    store = LocalArtifactStore(tmp_path / "store")
    with pytest.raises(FileNotFoundError):
        store.read_text(f"{RUN_ROOT_URI}/registry/{horizon_key}.json")


def test_retry_rejects_production_aliased_version_before_side_effects(
    tmp_path,
):
    horizon_key = "6m"
    sdk = FakeSDK()
    existing = _model(
        sdk,
        horizon_key,
        labels=_candidate_labels(horizon_key, lifecycle="abandoned"),
    )
    sdk.add_existing_version(model=existing, version_alias=SUITE_ALIAS)
    version_info = sdk.parent_versions[existing.resource_name][SUITE_ALIAS]
    version_info.version_aliases = [SUITE_ALIAS, "default", "production"]
    callback_results = []

    with pytest.raises(ValueError, match="production alias"):
        _register(
            tmp_path=tmp_path,
            sdk=sdk,
            horizon_key=horizon_key,
            callback=callback_results.append,
        )

    assert sdk.load_calls == []
    assert sdk.upload_calls == []
    assert existing.update_calls == []
    assert callback_results == []
    store = LocalArtifactStore(tmp_path / "store")
    with pytest.raises(FileNotFoundError):
        store.read_text(f"{RUN_ROOT_URI}/registry/{horizon_key}.json")


def test_retry_allows_default_alias_without_lifecycle_update(tmp_path):
    horizon_key = "6m"
    sdk = FakeSDK()
    existing = _model(sdk, horizon_key)
    sdk.add_existing_version(model=existing, version_alias=SUITE_ALIAS)

    result, _ = _register(
        tmp_path=tmp_path,
        sdk=sdk,
        horizon_key=horizon_key,
        callback=lambda registered: None,
    )

    version_info = sdk.parent_versions[existing.resource_name][SUITE_ALIAS]
    assert "default" in version_info.version_aliases
    assert "production" not in version_info.version_aliases
    assert sdk.upload_calls == []
    assert existing.update_calls == []
    assert result.version_resource_name == existing.versioned_resource_name


@pytest.mark.parametrize("lifecycle", [None, "production", "retired"])
def test_retry_rejects_missing_or_unsupported_lifecycle_before_side_effects(
    tmp_path,
    lifecycle,
):
    horizon_key = "12m"
    sdk = FakeSDK()
    labels = _candidate_labels(horizon_key)
    if lifecycle is None:
        labels.pop("lifecycle")
    else:
        labels["lifecycle"] = lifecycle
    existing = _model(sdk, horizon_key, labels=labels)
    sdk.add_existing_version(model=existing, version_alias=SUITE_ALIAS)
    callback_results = []

    with pytest.raises(ValueError, match="lifecycle"):
        _register(
            tmp_path=tmp_path,
            sdk=sdk,
            horizon_key=horizon_key,
            callback=callback_results.append,
        )

    assert sdk.upload_calls == []
    assert existing.update_calls == []
    assert callback_results == []
    store = LocalArtifactStore(tmp_path / "store")
    with pytest.raises(FileNotFoundError):
        store.read_text(f"{RUN_ROOT_URI}/registry/{horizon_key}.json")


@pytest.mark.parametrize(
    ("mismatch", "expected_message"),
    [
        ("parent", "unexpected parent model resource"),
        ("version", "non-numeric model version ID"),
        ("versioned_resource", "inconsistent version resource name"),
    ],
)
def test_retry_validates_structural_identity_before_lifecycle_update(
    tmp_path,
    mismatch,
    expected_message,
):
    horizon_key = "0m"
    sdk = FakeSDK()
    existing = _model(
        sdk,
        horizon_key,
        labels=_candidate_labels(horizon_key, lifecycle="abandoned"),
    )
    sdk.add_existing_version(model=existing, version_alias=SUITE_ALIAS)
    if mismatch == "parent":
        existing.resource_name = f"{existing.resource_name}-other"
    elif mismatch == "version":
        existing.version_id = "not-numeric"
    else:
        existing.versioned_resource_name = f"{existing.resource_name}@999"
    callback_results = []

    with pytest.raises(ValueError, match=expected_message):
        _register(
            tmp_path=tmp_path,
            sdk=sdk,
            horizon_key=horizon_key,
            callback=callback_results.append,
        )

    assert sdk.upload_calls == []
    assert existing.update_calls == []
    assert callback_results == []
    store = LocalArtifactStore(tmp_path / "store")
    with pytest.raises(FileNotFoundError):
        store.read_text(f"{RUN_ROOT_URI}/registry/{horizon_key}.json")


@pytest.mark.parametrize(
    ("mismatch", "expected_message"),
    [
        ("artifact_uri", "artifact URI"),
        ("image_uri", "image URI"),
        ("image_digest", "image digest"),
        ("horizon", "horizon label"),
        ("suite", "suite label"),
    ],
)
def test_retry_identity_mismatch_fails_without_duplicate_upload(
    tmp_path,
    mismatch,
    expected_message,
):
    horizon_key = "12m"
    sdk = FakeSDK()
    existing = _model(sdk, horizon_key)
    if mismatch == "artifact_uri":
        existing.uri = "gs://bucket/different-artifact"
    elif mismatch == "image_uri":
        existing.gca_resource.container_spec.image_uri = (
            "registry.example/different@" + IMAGE_DIGEST
        )
    elif mismatch == "image_digest":
        existing.gca_resource.container_spec.env[0].value = (
            f"sha256:{'b' * 64}"
        )
    elif mismatch == "horizon":
        existing.labels["horizon"] = "0m"
    elif mismatch == "suite":
        existing.labels["suite"] = "different-suite"
    sdk.add_existing_version(model=existing, version_alias=SUITE_ALIAS)
    callback_results = []

    with pytest.raises(ValueError, match=expected_message):
        _register(
            tmp_path=tmp_path,
            sdk=sdk,
            horizon_key=horizon_key,
            callback=callback_results.append,
        )

    assert sdk.upload_calls == []
    assert existing.update_calls == []
    assert callback_results == []
    store = LocalArtifactStore(tmp_path / "store")
    with pytest.raises(FileNotFoundError):
        store.read_text(f"{RUN_ROOT_URI}/registry/{horizon_key}.json")


def test_manifest_callback_failure_propagates_after_evidence_persistence(
    tmp_path,
):
    horizon_key = "0m"
    sdk = FakeSDK()
    sdk.upload_result = _model(sdk, horizon_key)
    store = RecordingLocalArtifactStore(tmp_path / "store", sdk.event_log)

    def fail_manifest_update(result):
        sdk.event_log.append(("manifest", result.horizon_key))
        raise RuntimeError("manifest update failed")

    with pytest.raises(RuntimeError, match="manifest update failed"):
        register_candidate_version(
            project_id=PROJECT_ID,
            region=REGION,
            run_root_uri=RUN_ROOT_URI,
            suite_version=SUITE_VERSION,
            horizon_key=horizon_key,
            artifact_uri=_artifact_uri(horizon_key),
            image_uri=IMAGE_URI,
            image_digest=IMAGE_DIGEST,
            source_git_commit=SOURCE_GIT_COMMIT,
            version_description=VERSION_DESCRIPTION,
            labels={"feature_month": "2026-04"},
            store=store,
            update_run_manifest=fail_manifest_update,
            sdk=sdk,
        )

    evidence_uri = f"{RUN_ROOT_URI}/registry/{horizon_key}.json"
    assert json.loads(store.read_text(evidence_uri))["horizon_key"] == horizon_key
    assert sdk.event_log[-2:] == [
        ("persist", evidence_uri),
        ("manifest", horizon_key),
    ]


def test_mark_registered_versions_abandoned_merges_existing_labels():
    sdk = FakeSDK()
    refs: list[RegisteredModelVersion] = []
    models: list[FakeModel] = []
    for index, horizon_key in enumerate(("0m", "6m"), start=1):
        model = _model(sdk, horizon_key, version_id=str(index))
        model.labels["provenance"] = f"source-{index}"
        sdk.models[(model.resource_name, model.version_id)] = model
        models.append(model)
        refs.append(
            RegisteredModelVersion(
                horizon_key=horizon_key,
                parent_model_resource_name=model.resource_name,
                version_resource_name=model.versioned_resource_name,
                version_id=model.version_id,
                suite_version_alias=SUITE_ALIAS,
                artifact_uri=model.uri,
            )
        )

    assert (
        mark_registered_versions_abandoned(
            refs,
            project_id=PROJECT_ID,
            region=REGION,
            sdk=sdk,
        )
        is None
    )

    assert sdk.init_calls == [{"project": PROJECT_ID, "location": REGION}]
    assert sdk.upload_calls == []
    for index, model in enumerate(models, start=1):
        assert model.labels["lifecycle"] == "abandoned"
        assert model.labels["provenance"] == f"source-{index}"
        assert model.labels["horizon"] in {"0m", "6m"}
        assert model.labels["suite"] == SUITE_ALIAS
        assert model.update_calls == [model.labels]


def test_mark_abandoned_updates_exact_versions_not_parent_models():
    sdk = FakeSDK()
    refs: list[RegisteredModelVersion] = []
    parents: list[FakeModel] = []
    candidates: list[FakeModel] = []
    for index, horizon_key in enumerate(("0m", "6m"), start=1):
        parent = _model(
            sdk,
            horizon_key,
            version_id="1",
            labels=_candidate_labels(horizon_key, lifecycle="production"),
        )
        candidate = _model(
            sdk,
            horizon_key,
            version_id=str(index + 6),
        )
        sdk.models[(parent.resource_name, parent.version_id)] = parent
        sdk.models[(candidate.resource_name, candidate.version_id)] = candidate

        def update_parent(
            *,
            labels,
            parent_model=parent,
            loaded_model=candidate,
        ):
            sdk.event_log.append(
                ("parent_update", parent_model.resource_name)
            )
            parent_model.update_calls.append(dict(labels))
            parent_model.labels = dict(labels)
            return loaded_model

        candidate.update = update_parent
        parents.append(parent)
        candidates.append(candidate)
        refs.append(
            RegisteredModelVersion(
                horizon_key=horizon_key,
                parent_model_resource_name=candidate.resource_name,
                version_resource_name=candidate.versioned_resource_name,
                version_id=candidate.version_id,
                suite_version_alias=SUITE_ALIAS,
                artifact_uri=candidate.uri,
            )
        )

    mark_registered_versions_abandoned(
        refs,
        project_id=PROJECT_ID,
        region=REGION,
        sdk=sdk,
    )

    for parent, candidate in zip(parents, candidates, strict=True):
        assert (
            "update_version",
            candidate.versioned_resource_name,
        ) in sdk.event_log
        assert candidate.labels["lifecycle"] == "abandoned"
        assert parent.update_calls == []
        assert parent.labels["lifecycle"] == "production"
