"""Explicitly gated live GCP smoke for the FEWSNET candidate suite."""

from __future__ import annotations

import ast
import builtins
import hashlib
import json
import math
import os
from collections.abc import Mapping
from pathlib import Path
import re
import shutil
import subprocess
import sys
import symtable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest


SMOKE_ENV_VARS = (
    "FEWSNET_GCP_SMOKE_ENABLED",
    "FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI",
    "FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI",
)
HORIZON_KEYS = ("0m", "6m", "12m")
PRODUCTION_PROJECT_ID = "food-crisis-modeling"
PRODUCTION_OBJECT_ROOT = (
    "gs://food-crisis-modeling-artifacts/fewsnet_partitioned_rf"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNBOOK_PATH = _REPO_ROOT / "docs" / "09_fewsnet_partitioned_rf_runbook.md"
_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_GCS_BUCKET_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$"
)


def _canonical_gs_manifest_uri(
    name: str,
    value: object,
    *,
    required_suffix: str | None = None,
) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required")
    if value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"{name} must be trimmed and contain no whitespace")
    parsed = urlsplit(value)
    if parsed.scheme != "gs":
        raise ValueError(f"{name} must use the gs:// scheme")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not contain a query or fragment")
    if _GCS_BUCKET_PATTERN.fullmatch(parsed.netloc) is None:
        raise ValueError(f"{name} must contain a canonical GCS bucket")
    if not parsed.path.startswith("/") or parsed.path == "/":
        raise ValueError(f"{name} must contain a nonempty object name")
    object_name = parsed.path[1:]
    segments = object_name.split("/")
    if (
        "\\" in object_name
        or any(segment in {"", ".", ".."} for segment in segments)
        or urlunsplit(parsed) != value
    ):
        raise ValueError(f"{name} must be a canonical gs://bucket/object URI")
    if required_suffix is not None and not parsed.path.endswith(required_suffix):
        raise ValueError(f"{name} must end with {required_suffix}")
    return value


def _validated_smoke_manifest_uris() -> tuple[str, str]:
    deployment_uri = _canonical_gs_manifest_uri(
        "FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI",
        os.environ.get("FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI"),
    )
    snapshot_uri = _canonical_gs_manifest_uri(
        "FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI",
        os.environ.get("FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI"),
        required_suffix="/source_manifest.json",
    )
    return deployment_uri, snapshot_uri


def _checked_out_source_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("unable to resolve the checked-out Git commit") from exc
    commit = completed.stdout.strip()
    if _GIT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError(
            "checked-out Git commit must be exactly 40 lowercase hex characters"
        )
    return commit


def _verified_checkout_source_commit(
    deployment_source_commit: object,
    *,
    checked_out_commit: str | None = None,
) -> str:
    if (
        not isinstance(deployment_source_commit, str)
        or _GIT_COMMIT_PATTERN.fullmatch(deployment_source_commit) is None
    ):
        raise ValueError(
            "deployment source_git_commit must be exactly 40 lowercase hex characters"
        )
    commit = (
        _checked_out_source_commit()
        if checked_out_commit is None
        else checked_out_commit
    )
    if _GIT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError(
            "checked-out Git commit must be exactly 40 lowercase hex characters"
        )
    if commit != deployment_source_commit:
        raise ValueError(
            "checked-out Git commit does not equal deployment source_git_commit"
        )
    return commit


def _skip_reason() -> str:
    if os.environ.get("FEWSNET_GCP_SMOKE_ENABLED") != "1":
        return "set FEWSNET_GCP_SMOKE_ENABLED=1 to authorize the live GCP smoke"
    missing = [name for name in SMOKE_ENV_VARS if not os.environ.get(name)]
    if missing:
        return f"missing required FEWSNET GCP smoke variables: {missing}"
    try:
        _validated_smoke_manifest_uris()
    except ValueError as exc:
        return f"invalid FEWSNET GCP smoke environment: {exc}"
    return ""


_LIVE_SMOKE_SKIP_REASON = _skip_reason()


def _ref_field(ref: object, name: str) -> Any:
    if isinstance(ref, Mapping):
        return ref[name]
    return getattr(ref, name)


def _read_json_ref(store: object, ref: object) -> dict[str, Any]:
    uri = str(_ref_field(ref, "uri"))
    generation = str(_ref_field(ref, "generation"))
    data = store.read_bytes(uri, generation=generation)
    assert len(data) == int(_ref_field(ref, "size_bytes"))
    assert hashlib.sha256(data).hexdigest() == _ref_field(ref, "sha256")
    payload = json.loads(data)
    assert isinstance(payload, dict)
    return payload


def _state_name(value: object) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(value).rsplit(".", 1)[-1]


@pytest.mark.skipif(
    bool(_LIVE_SMOKE_SKIP_REASON),
    reason=_LIVE_SMOKE_SKIP_REASON,
)
def test_live_gcp_candidate_smoke_is_disposable_and_never_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_manifest_uri, snapshot_manifest_uri = (
        _validated_smoke_manifest_uris()
    )
    from google.api_core.client_options import ClientOptions
    from google.api_core.exceptions import NotFound
    from google.cloud import aiplatform_v1

    from fewsnet_partitioned_rf_pipeline.cli.run_latest import (
        _default_backends,
        run_latest,
    )
    from fewsnet_partitioned_rf_pipeline.schemas import (
        validate_deployment,
        validate_payload,
    )
    from fewsnet_partitioned_rf_pipeline.vertex.storage import GCSArtifactStore

    store = GCSArtifactStore.from_default()
    deployment_ref = store.get_ref(deployment_manifest_uri)
    deployment = _read_json_ref(store, deployment_ref)
    validate_deployment(deployment)
    source_git_commit = _verified_checkout_source_commit(
        deployment["source_git_commit"]
    )
    monkeypatch.setenv("FEWSNET_SOURCE_GIT_COMMIT", source_git_commit)

    project_id = str(deployment["project_id"])
    region = str(deployment["region"])
    root_uri = str(deployment["object_store_root_uri"]).rstrip("/")
    assert project_id != PRODUCTION_PROJECT_ID, (
        "the live smoke must use a dedicated non-production GCP project"
    )
    assert not root_uri.startswith(PRODUCTION_OBJECT_ROOT), (
        "the live smoke must not use the production FEWSNET artifact root"
    )
    for name in (
        "orchestrator_service_account",
        "training_service_account",
        "batch_prediction_service_account",
    ):
        assert str(deployment[name]).endswith(
            f"@{project_id}.iam.gserviceaccount.com"
        ), f"{name} must belong to the dedicated smoke project"

    client_options = ClientOptions(
        api_endpoint=f"{region}-aiplatform.googleapis.com"
    )
    job_service = aiplatform_v1.JobServiceClient(
        client_options=client_options
    )
    model_service = aiplatform_v1.ModelServiceClient(
        client_options=client_options
    )
    endpoint_service = aiplatform_v1.EndpointServiceClient(
        client_options=client_options
    )
    parent = f"projects/{project_id}/locations/{region}"

    endpoint_names_before = {
        endpoint.name
        for endpoint in endpoint_service.list_endpoints(
            request={"parent": parent}
        )
    }
    backends = _default_backends(region)
    registry_backend = backends[1]
    alias_backend = backends[3]
    registry_backend.init(project=project_id, location=region)
    parent_models = {
        horizon_key: (
            f"{parent}/models/{deployment['parent_model_ids'][horizon_key]}"
        )
        for horizon_key in HORIZON_KEYS
    }
    production_aliases_before = {
        horizon_key: alias_backend.current_version(
            parent_models[horizon_key],
            "production",
        )
        for horizon_key in HORIZON_KEYS
    }
    current_pointer_uri = f"{root_uri}/released/current.json"

    def optional_object_state(uri: str) -> tuple[str, str, bytes] | None:
        try:
            ref = store.get_ref(uri)
        except (FileNotFoundError, NotFound):
            return None
        data = store.read_bytes(uri, generation=ref.generation)
        return (ref.generation, ref.sha256, data)

    current_pointer_before = optional_object_state(current_pointer_uri)
    result = run_latest(
        deployment,
        store,
        *backends,
        snapshot_manifest_uri=snapshot_manifest_uri,
        promote=False,
    )

    assert result["status"] == "CANDIDATE_VALIDATED"
    assert result["phase"] == "OUTPUT_VALIDATED"
    assert result["run_id"] == result["suite_version"]
    validate_payload("suite-manifest", result["suite_manifest"])

    run_manifest = _read_json_ref(store, result["run_manifest"])
    validate_payload("run-manifest", run_manifest)
    assert run_manifest["status"] == "candidate_validated"
    assert run_manifest["phase"] == "OUTPUT_VALIDATED"
    assert set(run_manifest["model_versions"]) == set(HORIZON_KEYS)
    assert set(run_manifest["batch_jobs"]) == set(HORIZON_KEYS)

    snapshot_ref = run_manifest["snapshot_ref"]
    assert snapshot_ref["uri"] == snapshot_manifest_uri
    snapshot = _read_json_ref(store, snapshot_ref)
    validate_payload("source-snapshot", snapshot)
    expected_rows = int(snapshot["area_count"])
    validation = result["validation"]
    assert validation["area_count"] == expected_rows
    assert validation["snapshot_id"] == snapshot["snapshot_id"]
    assert validation["snapshot_content_sha256"] == snapshot[
        "snapshot_content_sha256"
    ]
    assert set(validation["horizons"]) == set(HORIZON_KEYS)
    for horizon_key in HORIZON_KEYS:
        summary = validation["horizons"][horizon_key]
        assert summary["row_count"] == expected_rows
        assert sum(summary["source_counts"].values()) == expected_rows

    run_root = f"{root_uri}/runs/{result['run_id']}"
    custom_job_ref = store.get_ref(f"{run_root}/training/custom_job.json")
    custom_job_evidence = _read_json_ref(store, custom_job_ref)
    custom_job_request = custom_job_evidence["request"]["custom_job"]
    custom_job_resource = custom_job_evidence["resource"]
    operation_id = custom_job_request["labels"]["fewsnet_operation"]
    custom_jobs = list(
        job_service.list_custom_jobs(
            request={
                "parent": parent,
                "filter": (
                    f'display_name="{custom_job_request["display_name"]}" '
                    f"AND labels.fewsnet_operation={operation_id}"
                ),
            }
        )
    )
    assert len(custom_jobs) == 1
    assert custom_jobs[0].name == custom_job_resource["name"]
    assert _state_name(custom_jobs[0].state) == "JOB_STATE_SUCCEEDED"

    version_resources: set[str] = set()
    for horizon_key in HORIZON_KEYS:
        version = run_manifest["model_versions"][horizon_key]
        model = model_service.get_model(
            request={"name": version["version_resource_name"]}
        )
        observed_resource = (
            model.name
            if "@" in model.name
            else f"{model.name}@{model.version_id}"
        )
        assert observed_resource == version["version_resource_name"]
        assert str(model.version_id) == version["version_id"]
        assert model.name == version["parent_model_resource_name"]
        assert model.artifact_uri == version["artifact_uri"]
        assert model.container_spec.image_uri == deployment[
            "container_image_uri"
        ]
        assert dict(model.labels).get("lifecycle") == "candidate"
        assert version["suite_version_alias"] in set(model.version_aliases)
        assert "production" not in set(model.version_aliases)
        version_resources.add(version["version_resource_name"])
    assert len(version_resources) == 3

    expected_batch_jobs = {
        value["job_resource_name"]
        for value in run_manifest["batch_jobs"].values()
    }
    batch_run_label = hashlib.sha256(
        result["run_id"].encode("utf-8")
    ).hexdigest()[:16]
    observed_batch_jobs = list(
        job_service.list_batch_prediction_jobs(
            request={
                "parent": parent,
                "filter": f"labels.fewsnet_run={batch_run_label}",
            }
        )
    )
    assert len(observed_batch_jobs) == 3
    assert {job.name for job in observed_batch_jobs} == expected_batch_jobs
    assert all(
        _state_name(job.state) == "JOB_STATE_SUCCEEDED"
        for job in observed_batch_jobs
    )

    endpoint_names_after = {
        endpoint.name
        for endpoint in endpoint_service.list_endpoints(
            request={"parent": parent}
        )
    }
    assert endpoint_names_after == endpoint_names_before
    assert {
        horizon_key: alias_backend.current_version(
            parent_models[horizon_key],
            "production",
        )
        for horizon_key in HORIZON_KEYS
    } == production_aliases_before
    assert optional_object_state(current_pointer_uri) == current_pointer_before


_VALID_DEPLOYMENT_MANIFEST_URI = (
    "gs://dedicated-smoke-bucket/fewsnet/deployments/test.json"
)
_VALID_SNAPSHOT_MANIFEST_URI = (
    "gs://dedicated-smoke-bucket/fewsnet/inputs/snapshots/test/"
    "source_manifest.json"
)


def _set_smoke_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    deployment_uri: str,
    snapshot_uri: str,
) -> None:
    monkeypatch.setenv("FEWSNET_GCP_SMOKE_ENABLED", "1")
    monkeypatch.setenv(
        "FEWSNET_GCP_DEPLOYMENT_MANIFEST_URI",
        deployment_uri,
    )
    monkeypatch.setenv(
        "FEWSNET_GCP_TEST_SNAPSHOT_MANIFEST_URI",
        snapshot_uri,
    )


@pytest.mark.parametrize(
    ("deployment_uri", "snapshot_uri"),
    (
        (" ", _VALID_SNAPSHOT_MANIFEST_URI),
        ("not-a-uri", _VALID_SNAPSHOT_MANIFEST_URI),
        ("gs://bucket", _VALID_SNAPSHOT_MANIFEST_URI),
        (
            f"{_VALID_DEPLOYMENT_MANIFEST_URI}?generation=1",
            _VALID_SNAPSHOT_MANIFEST_URI,
        ),
        (
            _VALID_DEPLOYMENT_MANIFEST_URI,
            "gs://dedicated-smoke-bucket/fewsnet/snapshot.json",
        ),
        (
            _VALID_DEPLOYMENT_MANIFEST_URI,
            f"{_VALID_SNAPSHOT_MANIFEST_URI}#fragment",
        ),
        (
            _VALID_DEPLOYMENT_MANIFEST_URI,
            f" {_VALID_SNAPSHOT_MANIFEST_URI}",
        ),
    ),
)
def test_smoke_gate_rejects_malformed_manifest_uris(
    monkeypatch: pytest.MonkeyPatch,
    deployment_uri: str,
    snapshot_uri: str,
) -> None:
    _set_smoke_environment(
        monkeypatch,
        deployment_uri=deployment_uri,
        snapshot_uri=snapshot_uri,
    )

    assert _skip_reason().startswith("invalid FEWSNET GCP smoke environment:")


def test_smoke_gate_accepts_canonical_manifest_uris(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_smoke_environment(
        monkeypatch,
        deployment_uri=_VALID_DEPLOYMENT_MANIFEST_URI,
        snapshot_uri=_VALID_SNAPSHOT_MANIFEST_URI,
    )

    assert _skip_reason() == ""


def test_source_commit_mismatch_fails_before_environment_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEWSNET_SOURCE_GIT_COMMIT", raising=False)
    helper = globals().get("_verified_checkout_source_commit")
    assert callable(helper), "live smoke lacks a checkout source-commit gate"

    with pytest.raises(ValueError, match="checked-out Git commit"):
        helper("0" * 40, checked_out_commit="1" * 40)
    assert "FEWSNET_SOURCE_GIT_COMMIT" not in os.environ


def test_source_commit_match_uses_exact_checked_out_identity() -> None:
    checkout_helper = globals().get("_checked_out_source_commit")
    verify_helper = globals().get("_verified_checkout_source_commit")
    assert callable(checkout_helper)
    assert callable(verify_helper)

    checked_out_commit = checkout_helper()
    assert len(checked_out_commit) == 40
    assert checked_out_commit == checked_out_commit.lower()
    assert all(character in "0123456789abcdef" for character in checked_out_commit)
    assert verify_helper(checked_out_commit) == checked_out_commit


def _runbook_text() -> str:
    return _RUNBOOK_PATH.read_text(encoding="utf-8")


def _marked_python_source(begin_marker: str, end_marker: str) -> str:
    text = _runbook_text()
    try:
        marked = text.split(begin_marker, 1)[1].split(end_marker, 1)[0]
    except IndexError as exc:
        raise AssertionError(f"runbook marker is missing: {begin_marker}") from exc
    lines = marked.splitlines()
    start = next(
        (index + 1 for index, line in enumerate(lines) if "<<'PY'" in line),
        None,
    )
    if start is None:
        raise AssertionError(f"marked block has no Python heredoc: {begin_marker}")
    end = next(
        (index for index in range(start, len(lines)) if lines[index] == "PY"),
        None,
    )
    if end is None:
        raise AssertionError(f"marked Python heredoc is unterminated: {begin_marker}")
    return "\n".join(lines[start:end]) + "\n"


def _production_verifier_source() -> str:
    return _marked_python_source(
        "# BEGIN FEWSNET_PRODUCTION_ACCEPTANCE_VERIFIER",
        "# END FEWSNET_PRODUCTION_ACCEPTANCE_VERIFIER",
    )


def _python_311_executable() -> str:
    if sys.version_info[:2] == (3, 11):
        return sys.executable
    candidates = [
        os.environ.get("FEWSNET_PYTHON311"),
        shutil.which("python3.11"),
        *(
            str(path)
            for path in sorted(
                Path.home().glob(
                    ".local/share/uv/python/cpython-3.11.*/bin/python3.11"
                )
            )
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise AssertionError("a Python 3.11 interpreter is required for runbook linting")


def _unresolved_global_names(source: str) -> set[str]:
    module = symtable.symtable(source, "<fewsnet-acceptance-verifier>", "exec")
    module_definitions = {
        symbol.get_name()
        for symbol in module.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }
    permitted = set(dir(builtins)) | {
        "__builtins__",
        "__name__",
        "__package__",
        "__spec__",
    }
    unresolved: set[str] = set()

    def visit(table: symtable.SymbolTable) -> None:
        for symbol in table.get_symbols():
            name = symbol.get_name()
            if (
                symbol.is_referenced()
                and symbol.is_global()
                and name not in module_definitions
                and name not in permitted
            ):
                unresolved.add(name)
        for child in table.get_children():
            visit(child)

    visit(module)
    return unresolved


def _verifier_helpers() -> dict[str, Any]:
    source = _production_verifier_source()
    prefix = source.split("\nraw_panel = required_env(", 1)[0]
    namespace: dict[str, Any] = {}
    exec(compile(prefix, "<fewsnet-acceptance-helpers>", "exec"), namespace)
    return namespace


def _shell_export(text: str, name: str) -> str:
    match = re.search(rf'^export {re.escape(name)}="(.*)"$', text, re.MULTILINE)
    if match is None:
        raise AssertionError(f"runbook export is missing: {name}")
    return match.group(1).replace(r'\"', '"')


def _condition_allows(condition: str, resource_name: str) -> bool:
    def atom_allows(atom: str) -> bool:
        atom = atom.strip()
        equality = re.fullmatch(r'resource\.name == "([^"]+)"', atom)
        if equality is not None:
            return resource_name == equality.group(1)
        starts = re.fullmatch(
            r'resource\.name\.startsWith\("([^"]+)"\)',
            atom,
        )
        if starts is not None:
            return resource_name.startswith(starts.group(1))
        ends = re.fullmatch(
            r'resource\.name\.endsWith\("([^"]+)"\)',
            atom,
        )
        if ends is not None:
            return resource_name.endswith(ends.group(1))
        raise AssertionError(f"unsupported documented IAM condition atom: {atom}")

    for disjunction in condition.split(" || "):
        conjunction = disjunction.strip()
        if conjunction.startswith("(") and conjunction.endswith(")"):
            conjunction = conjunction[1:-1]
        if all(atom_allows(atom) for atom in conjunction.split(" && ")):
            return True
    return False


def _role_permissions(text: str, role_id_variable: str) -> set[str]:
    command = re.search(
        re.escape(f'gcloud iam roles create "${role_id_variable}"')
        + r'.*?--permissions="([^"]+)"',
        text,
        re.DOTALL,
    )
    if command is None:
        raise AssertionError(f"custom role command is missing: {role_id_variable}")
    return set(command.group(1).split(","))


def test_runbook_limits_orchestrator_replacement_to_exact_mutable_objects() -> None:
    text = _runbook_text()
    base = "projects/_/buckets/example/objects/fewsnet"
    create_condition = _shell_export(text, "ORCHESTRATOR_CREATE_CONDITION").replace(
        "${OBJECT_RESOURCE_BASE}", base
    )
    replace_condition = _shell_export(
        text,
        "ORCHESTRATOR_REPLACE_CONDITION",
    ).replace("${OBJECT_RESOURCE_BASE}", base)

    assert _role_permissions(text, "OBJECT_CREATOR_ROLE_ID") == {
        "storage.objects.create"
    }
    assert _role_permissions(text, "OBJECT_REPLACER_ROLE_ID") == {
        "storage.objects.get",
        "storage.objects.delete",
    }
    assert '--role="$OBJECT_CREATOR_ROLE"' in text
    assert "expression=${ORCHESTRATOR_CREATE_CONDITION}" in text
    assert '--role="$OBJECT_REPLACER_ROLE"' in text
    assert "expression=${ORCHESTRATOR_REPLACE_CONDITION}" in text

    immutable_objects = (
        f"{base}/inputs/snapshots/s1/assembled_fewsnet.normalized.csv",
        f"{base}/deployments/deployment-deadbeef.json",
        f"{base}/runs/r1/predictions/0m.csv",
        f"{base}/suites/s1/models/0m/model.joblib",
        f"{base}/suites/s1/suite_manifest.json",
    )
    for resource_name in immutable_objects:
        assert _condition_allows(create_condition, resource_name)
        assert not _condition_allows(replace_condition, resource_name)

    mutable_objects = (
        f"{base}/locks/production-promotion.json",
        f"{base}/released/current.json",
        f"{base}/released/2026-04/production_suite_manifest.json",
        f"{base}/runs/r1/run_manifest.json",
    )
    for resource_name in mutable_objects:
        assert _condition_allows(create_condition, resource_name)
        assert _condition_allows(replace_condition, resource_name)

    assert not _condition_allows(
        replace_condition,
        f"{base}/runs/r1/error.json",
    )
    assert not _condition_allows(
        replace_condition,
        f"{base}/released/2026-04/map.png",
    )


def test_acceptance_verifier_rejects_optimized_python_before_cloud_bootstrap() -> None:
    source = _production_verifier_source()
    guard_prefix = source.split("\nfrom datetime", 1)[0]
    environment = dict(os.environ)
    environment["PYTHONOPTIMIZE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", guard_prefix],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    combined = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "all_16_acceptance_items=PASS" not in combined
    assert "optimized Python" in combined


def test_acceptance_verifier_uses_no_optimization_sensitive_asserts() -> None:
    tree = ast.parse(_production_verifier_source())
    assert [node for node in ast.walk(tree) if isinstance(node, ast.Assert)] == []


@pytest.mark.parametrize(
    ("begin_marker", "end_marker"),
    (
        (
            "# BEGIN FEWSNET_FIXED_SAMPLE_PARITY_GENERATOR",
            "# END FEWSNET_FIXED_SAMPLE_PARITY_GENERATOR",
        ),
        (
            "# BEGIN FEWSNET_PRODUCTION_ACCEPTANCE_VERIFIER",
            "# END FEWSNET_PRODUCTION_ACCEPTANCE_VERIFIER",
        ),
    ),
)
def test_marked_runbook_programs_parse_with_python_311(
    begin_marker: str,
    end_marker: str,
) -> None:
    source = _marked_python_source(begin_marker, end_marker)
    ast.parse(source, "<fewsnet-runbook>", "exec", feature_version=(3, 11))
    completed = subprocess.run(
        [
            _python_311_executable(),
            "-c",
            "import ast,sys; ast.parse(sys.stdin.read(), '<fewsnet-runbook>', 'exec')",
        ],
        input=source,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_acceptance_verifier_has_no_unresolved_global_names() -> None:
    assert _unresolved_global_names(_production_verifier_source()) == set()


def test_acceptance_verifier_normalizes_fake_object_refs() -> None:
    class FakeObjectRef:
        uri = "gs://bucket/root/object.json"
        generation = 7
        sha256 = "a" * 64
        size_bytes = "12"

    normalizer = _verifier_helpers()["object_ref_dict"]
    assert normalizer(FakeObjectRef()) == {
        "uri": "gs://bucket/root/object.json",
        "generation": "7",
        "sha256": "a" * 64,
        "size_bytes": 12,
    }


def test_runbook_has_executable_generation_bound_fixed_sample_parity_workflow() -> None:
    source = _marked_python_source(
        "# BEGIN FEWSNET_FIXED_SAMPLE_PARITY_GENERATOR",
        "# END FEWSNET_FIXED_SAMPLE_PARITY_GENERATOR",
    )
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    required_tokens = {
        "GCSArtifactStore",
        "LocalArtifactStore",
        "PACKAGE_FILES",
        "load_model_package",
        "create_app",
        "TestClient",
    }
    assert required_tokens <= names | attributes
    for field in (
        "batch_input",
        "package_objects",
        "vertex_output_objects",
        "local_output",
        "container_output",
        "vertex_output",
        "sample_sha256",
        "size_bytes",
        "sha256",
        "generation",
    ):
        assert field in source


@pytest.mark.parametrize("invalid_delta", (-1.0, math.nan, math.inf, -math.inf))
def test_acceptance_parity_helpers_reject_invalid_deltas_and_forged_hashes(
    invalid_delta: float,
) -> None:
    helpers = _verifier_helpers()
    validate_delta = helpers["validate_probability_delta"]
    require_fingerprint = helpers["require_fingerprint"]
    object_fingerprint = helpers["object_fingerprint"]

    assert validate_delta(0.0, 1e-12, "zero delta") == 0.0
    with pytest.raises(ValueError):
        validate_delta(invalid_delta, 1e-12, "invalid delta")

    actual = b'{"predictions":[]}\n'
    evidence = object_fingerprint(actual)
    require_fingerprint(actual, evidence, "actual output")
    forged = {**evidence, "sha256": "0" * 64}
    with pytest.raises(ValueError):
        require_fingerprint(actual, forged, "forged zero report")


def test_acceptance_verifier_binds_staged_panel_and_raw_source_identity() -> None:
    helpers = _verifier_helpers()
    read_ref = helpers["read_ref"]
    panel_csv_dimensions = helpers["panel_csv_dimensions"]
    require_source_panel_identity = helpers["require_source_panel_identity"]

    panel_bytes = b"admin_code,value\nA,1\nB,2\n"
    panel_ref = {
        "uri": "gs://bucket/root/inputs/snapshots/s1/panel.csv",
        "generation": "7",
        "sha256": hashlib.sha256(panel_bytes).hexdigest(),
        "size_bytes": len(panel_bytes),
    }

    class FakeStore:
        def __init__(self, data: bytes):
            self.data = data

        def read_bytes(self, uri: str, generation: str) -> bytes:
            assert uri == panel_ref["uri"]
            assert generation == panel_ref["generation"]
            return self.data

    assert read_ref(FakeStore(panel_bytes), panel_ref, "staged panel") == panel_bytes
    assert panel_csv_dimensions(panel_bytes, "staged panel") == (2, 2)
    with pytest.raises(ValueError, match="size|checksum"):
        read_ref(FakeStore(panel_bytes + b"C,3\n"), panel_ref, "staged panel")

    source_panel = {
        "sha256": hashlib.sha256(b"raw").hexdigest(),
        "size_bytes": 3,
    }
    require_source_panel_identity(
        source_panel,
        source_panel["sha256"],
        source_panel["size_bytes"],
    )
    with pytest.raises(ValueError):
        require_source_panel_identity(source_panel, "0" * 64, 3)


def test_acceptance_inventory_allows_only_documented_object_paths() -> None:
    allowed_object_uri = _verifier_helpers()["allowed_object_uri"]
    root = "gs://bucket/fewsnet"
    approved = (
        f"{root}/inputs/snapshots/s1/source_manifest.json",
        f"{root}/deployments/deployment-{'a' * 12}-{'b' * 64}.json",
        f"{root}/runs/r1/run_manifest.json",
        f"{root}/runs/r1/inputs/selected_source_manifest.json",
        f"{root}/runs/r1/training/custom_job.json",
        f"{root}/runs/r1/registry/0m.json",
        f"{root}/runs/r1/batch_prediction/12m/input.jsonl",
        (
            f"{root}/runs/r1/batch_prediction/12m/raw/"
            "prediction.results-1/predictions_0001.jsonl"
        ),
        f"{root}/runs/r1/predictions/6m.csv",
        f"{root}/runs/r1/error.json",
        f"{root}/suites/s1/models/0m/model.joblib",
        f"{root}/suites/s1/predictions/12m.csv",
        f"{root}/suites/s1/suite_manifest.json",
        f"{root}/locks/production-promotion.json",
        f"{root}/released/2026-04/production_suite_manifest.json",
        f"{root}/released/current.json",
    )
    assert all(allowed_object_uri(root, uri) for uri in approved)

    forbidden = (
        f"{root}/runs/r1/map.png",
        f"{root}/runs/r1/forecast-map.pdf",
        f"{root}/runs/r1/forecast.xls",
        f"{root}/runs/r1/forecast.xlsx",
        f"{root}/runs/r1/forecast.xlsb",
        f"{root}/runs/r1/future-performance.json",
        f"{root}/runs/r1/arbitrary-new-output.json",
    )
    assert all(not allowed_object_uri(root, uri) for uri in forbidden)
