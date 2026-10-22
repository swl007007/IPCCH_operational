"""Dual-system FEWSNET/IPCCH delivery request contract (``run_manifest.json``).

This is a new versioned contract, separate from the IPCCH-only input manifest in
``cloud/common/manifest.py``. Two levels are kept distinct:

* ``validate_delivery_request`` is structural only: field shapes, exact system /
  horizon coverage, immutable-reference form and cross-field identities. Passing
  it does not mean any referenced object, prepared snapshot, model or runtime is
  accepted; the result carries ``validation_level == "structural"``.
* ``verify_reference_identities`` checks each reference against an injected
  resolver (actual object generation and SHA-256). Prepared readiness, model
  acceptance-report content and runtime/job identity remain separate checks,
  enumerated by ``acceptance_requirements``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from cloud.common.object_refs import is_digest_pinned_image, normalize_gcs_ref
from cloud.orchestrator.causal_fill import FILL_POLICY_VERSION


SCHEMA_VERSION = "fewsnet-ipcch-delivery-request-v1"
SYSTEMS = ("fewsnet", "ipcch")
HORIZONS_MONTHS = (0, 6, 12)
SOURCE_ACTIONS = ("keep", "refresh")
RAW_CONVERTER_CONTRACT_VERSION = "september-h5-raw-converter-v1"
CONTRACT_KINDS = ("feature", "fill", "output", "diagnostic")
ASSET_KINDS = {
    "fewsnet": ("geometry", "roster", "population", "country_reference", "history_panel"),
    "ipcch": (
        "geometry",
        "roster",
        "population",
        "country_reference",
        "history_panel",
        "fixed_features",
    ),
}
DIAGNOSTIC_FAMILIES = {
    "fewsnet": ("polygon_confidence", "country_confidence"),
    "ipcch": ("polygon_training_errors", "country_confidence", "maximum_phase"),
}
UNAVAILABLE_REASONS = (
    "missing_evidence",
    "no_eligible_area_history",
    "no_complete_history",
    "single_month_interval_unavailable",
)
LEGACY_RELEASE_NAMESPACE = "released"
TOP_LEVEL_FIELDS = (
    "schema_version",
    "run_id",
    "origin_month",
    "systems",
    "horizons_months",
    "prepared_snapshot",
    "acled",
    "wfp",
    "models",
    "assets",
    "diagnostics",
    "contracts",
    "runtime",
    "release",
    "operator",
    "prepared_at",
)

_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,62}$")
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_RE = re.compile(r"^[1-9][0-9]*$")
_GCS_OBJECT_RE = re.compile(r"^gs://[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]/[^\s]*[^/\s]$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
_NAMESPACE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_REQUEST_PATH_RE = re.compile(
    r"^gs://[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]/requests/([^/]+)/run_manifest\.json$"
)


class DeliveryManifestError(ValueError):
    """Raised when a delivery request fails structural validation."""


class ReferenceIdentityError(ValueError):
    """Raised when a referenced object does not match its pinned identity."""


def validate_delivery_request(
    data: Mapping[str, Any],
    *,
    request_uri: str,
    request_generation: str,
    expected_release_namespace: str | None = None,
) -> dict[str, Any]:
    """Structurally validate one request read from ``request_uri`` at ``request_generation``.

    The request object's own identity comes from the event (URI + generation); the
    request never carries a checksum of itself.
    """
    if not isinstance(data, Mapping):
        raise DeliveryManifestError("request must be a JSON object")
    _exact_keys(data, TOP_LEVEL_FIELDS, "request")
    if data["schema_version"] != SCHEMA_VERSION:
        raise DeliveryManifestError(f"schema_version must be {SCHEMA_VERSION}")

    run_id = data["run_id"]
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise DeliveryManifestError("run_id must be 3-63 lowercase [a-z0-9._-] characters")
    path_match = _REQUEST_PATH_RE.fullmatch(request_uri or "")
    if path_match is None:
        raise DeliveryManifestError("request_uri must be gs://<bucket>/requests/<run_id>/run_manifest.json")
    if path_match.group(1) != run_id:
        raise DeliveryManifestError("run_id must equal the request path run ID")
    if not isinstance(request_generation, str) or _GENERATION_RE.fullmatch(request_generation) is None:
        raise DeliveryManifestError("request_generation must be a positive integer string")

    origin = _month(data["origin_month"], "origin_month")
    _exact_sequence(data["systems"], SYSTEMS, "systems")
    _exact_sequence(data["horizons_months"], HORIZONS_MONTHS, "horizons_months")

    prepared = _object(data["prepared_snapshot"], ("prepare_id", "origin_month", "manifest"), "prepared_snapshot")
    _text(prepared["prepare_id"], "prepared_snapshot.prepare_id")
    if _month(prepared["origin_month"], "prepared_snapshot.origin_month") != origin:
        raise DeliveryManifestError("prepared_snapshot.origin_month must equal origin_month")
    _ref(prepared["manifest"], "prepared_snapshot.manifest")

    for source in ("acled", "wfp"):
        _source_choice(data[source], source)

    models = _models(data["models"])
    _assets(data["assets"])
    _diagnostics(data["diagnostics"], models)
    _contracts(data["contracts"])
    _runtime(data["runtime"])
    _release(data["release"], expected_release_namespace)
    _text(data["operator"], "operator")
    _timestamp(data["prepared_at"], "prepared_at")

    validated = dict(data)
    validated["request"] = normalize_gcs_ref(request_uri, generation=request_generation)
    validated["validation_level"] = "structural"
    return validated


def iter_object_refs(request: Mapping[str, Any]) -> list[tuple[str, Mapping[str, str]]]:
    """Every pinned object reference in a structurally valid request, with its field path."""
    refs = [("prepared_snapshot.manifest", request["prepared_snapshot"]["manifest"])]
    for source in ("acled", "wfp"):
        choice = request[source]
        field = "retained_snapshot" if choice["action"] == "keep" else "raw_upload"
        refs.append((f"{source}.{field}", choice[field]))
    for model in request["models"]:
        label = f"models[{model['system']}/{model['horizon_months']}m]"
        refs.append((f"{label}.package_manifest", model["package_manifest"]))
        refs.append((f"{label}.acceptance_report", model["acceptance_report"]))
    for system in SYSTEMS:
        for kind in ASSET_KINDS[system]:
            refs.append((f"assets.{system}.{kind}", request["assets"][system][kind]))
    for entry in request["diagnostics"]:
        label = f"diagnostics[{entry['system']}/{entry['horizon_months']}m/{entry['family']}]"
        if entry["status"] in ("available", "frozen_output"):
            refs.append((f"{label}.evidence", entry["evidence"]))
        if entry["status"] == "frozen_output":
            refs.append((f"{label}.source_availability", entry["source_availability"]))
    refs.append(("runtime.environment_manifest", request["runtime"]["environment_manifest"]))
    return refs


def verify_reference_identities(
    request: Mapping[str, Any],
    resolve: Callable[[str, str], str | None],
) -> list[dict[str, str]]:
    """Check each reference's actual SHA-256 at its pinned generation.

    ``resolve(uri, generation)`` returns the SHA-256 of that exact object
    generation, or ``None`` when it does not exist. Any mismatch is an integrity
    failure, never a silently unavailable input.
    """
    if request.get("validation_level") != "structural":
        raise ReferenceIdentityError("request must pass structural validation first")
    verified = []
    for field, ref in iter_object_refs(request):
        actual = resolve(ref["uri"], ref["generation"])
        if actual is None:
            raise ReferenceIdentityError(f"{field} object/generation not found: {ref['uri']}#{ref['generation']}")
        if actual != ref["sha256"]:
            raise ReferenceIdentityError(f"{field} sha256 mismatch for {ref['uri']}#{ref['generation']}")
        verified.append({"field": field, **ref})
    return verified


def acceptance_requirements(request: Mapping[str, Any]) -> list[str]:
    """Checks beyond structure that must pass before costly work or publication."""
    return [
        "reference_identities: every pinned object exists at its generation with its sha256",
        f"prepared_snapshot: {request['prepared_snapshot']['prepare_id']} completed successfully "
        "for this origin, rosters and source contracts",
        "source_choices: retained snapshots are accepted prior snapshots; raw uploads pass the converter contract",
        "models: each acceptance report accepts its exact package for this system/horizon and runtime",
        "diagnostics: each available evidence bundle matches its declared model package and horizon",
        "runtime: configured job image digest equals runtime.image_uri",
        "release: current pointer generation equals release.expected_pointer_generation at publication",
    ]


def _source_choice(value: Any, source: str) -> None:
    if not isinstance(value, Mapping) or value.get("action") not in SOURCE_ACTIONS:
        raise DeliveryManifestError(f"{source}.action must be one of {SOURCE_ACTIONS}")
    field = "retained_snapshot" if value["action"] == "keep" else "raw_upload"
    _exact_keys(value, ("action", field, "converter_contract"), source)
    _ref(value[field], f"{source}.{field}")
    contract = _contract(value["converter_contract"], f"{source}.converter_contract")
    if contract["version"] != RAW_CONVERTER_CONTRACT_VERSION:
        raise DeliveryManifestError(
            f"{source}.converter_contract.version must be {RAW_CONVERTER_CONTRACT_VERSION}"
        )


def _models(value: Any) -> dict[tuple[str, int], str]:
    if not isinstance(value, list):
        raise DeliveryManifestError("models must be a list")
    fields = ("system", "horizon_months", "package_id", "package_manifest", "acceptance_report", "feature_schema_sha256")
    by_key: dict[tuple[str, int], str] = {}
    for index, model in enumerate(value):
        label = f"models[{index}]"
        _object(model, fields, label)
        key = (model["system"], model["horizon_months"])
        if model["system"] not in SYSTEMS or model["horizon_months"] not in HORIZONS_MONTHS:
            raise DeliveryManifestError(f"{label} has unsupported system/horizon {key}")
        if type(model["horizon_months"]) is not int:
            raise DeliveryManifestError(f"{label}.horizon_months must be an integer")
        if key in by_key:
            raise DeliveryManifestError(f"duplicate model entry for {key}")
        by_key[key] = _text(model["package_id"], f"{label}.package_id")
        _ref(model["package_manifest"], f"{label}.package_manifest")
        _ref(model["acceptance_report"], f"{label}.acceptance_report")
        _sha256(model["feature_schema_sha256"], f"{label}.feature_schema_sha256")
    expected = {(system, horizon) for system in SYSTEMS for horizon in HORIZONS_MONTHS}
    if set(by_key) != expected:
        raise DeliveryManifestError(f"models must cover exactly {sorted(expected)}")
    for system in SYSTEMS:
        package_ids = [by_key[(system, horizon)] for horizon in HORIZONS_MONTHS]
        if len(set(package_ids)) != len(package_ids):
            raise DeliveryManifestError(f"{system} horizons must reference distinct packages; no relabeled models")
    return by_key


def _assets(value: Any) -> None:
    _exact_keys(value, SYSTEMS, "assets")
    for system in SYSTEMS:
        _exact_keys(value[system], ASSET_KINDS[system], f"assets.{system}")
        for kind in ASSET_KINDS[system]:
            _ref(value[system][kind], f"assets.{system}.{kind}")


def _diagnostics(value: Any, models: Mapping[tuple[str, int], str]) -> None:
    if not isinstance(value, list):
        raise DeliveryManifestError("diagnostics must be a list")
    seen = set()
    for index, entry in enumerate(value):
        label = f"diagnostics[{index}]"
        if not isinstance(entry, Mapping):
            raise DeliveryManifestError(f"{label} must be an object")
        status = entry.get("status")
        if status == "available":
            fields = ("system", "horizon_months", "family", "status", "evidence",
                      "evidence_model_package_id", "evidence_horizon_months")
        elif status == "unavailable":
            # Canonical design section 4.2 form: explicit ``evidence: null`` plus a reason.
            fields = ("system", "horizon_months", "family", "status", "evidence", "reason")
        elif status == "frozen_output":
            # Accepted historical confidence outputs attached unchanged (FEWS 2026-10 retrain); the
            # evidence/source package stays distinct from the scored package.
            fields = ("system", "horizon_months", "family", "status", "evidence", "source_availability",
                      "source_delivery_id", "evidence_model_package_id", "evidence_horizon_months",
                      "evidence_basis", "evidence_period")
        else:
            raise DeliveryManifestError(f"{label}.status must be available, unavailable or frozen_output")
        _exact_keys(entry, fields, label)
        system, horizon, family = entry["system"], entry["horizon_months"], entry["family"]
        if system not in SYSTEMS or horizon not in HORIZONS_MONTHS or type(horizon) is not int:
            raise DeliveryManifestError(f"{label} has unsupported system/horizon")
        if family not in DIAGNOSTIC_FAMILIES[system]:
            raise DeliveryManifestError(f"{label}.family {family!r} is not a {system} diagnostic")
        key = (system, horizon, family)
        if key in seen:
            raise DeliveryManifestError(f"duplicate diagnostics entry {key}")
        seen.add(key)
        if status == "frozen_output":
            from cloud.orchestrator.delivery_outputs import APPROVED_PROXY_EVIDENCE

            if system != "fewsnet":
                raise DeliveryManifestError(f"{label}: frozen outputs are FEWS-only")
            _ref(entry["evidence"], f"{label}.evidence")
            _ref(entry["source_availability"], f"{label}.source_availability")
            _text(entry["source_delivery_id"], f"{label}.source_delivery_id")
            _text(entry["evidence_model_package_id"], f"{label}.evidence_model_package_id")
            if entry["evidence_horizon_months"] != horizon or type(entry["evidence_horizon_months"]) is not int:
                raise DeliveryManifestError(f"{label} evidence horizon must equal {horizon}")
            if (entry["evidence_basis"], entry["evidence_period"]) != APPROVED_PROXY_EVIDENCE[(system, horizon)]:
                raise DeliveryManifestError(f"{label} must carry the approved {horizon}m historical basis/period")
        elif status == "available":
            _ref(entry["evidence"], f"{label}.evidence")
            # Evidence must belong to this exact package and horizon: no h5 proxy default.
            if entry["evidence_horizon_months"] != horizon or type(entry["evidence_horizon_months"]) is not int:
                raise DeliveryManifestError(f"{label} evidence horizon must equal {horizon}")
            if entry["evidence_model_package_id"] != models[(system, horizon)]:
                raise DeliveryManifestError(f"{label} evidence must belong to model package {models[(system, horizon)]}")
        else:
            if entry["evidence"] is not None:
                raise DeliveryManifestError(f"{label}.evidence must be null when unavailable")
            if entry["reason"] not in UNAVAILABLE_REASONS:
                raise DeliveryManifestError(f"{label}.reason must be one of {UNAVAILABLE_REASONS}")
    expected = {
        (system, horizon, family)
        for system in SYSTEMS
        for horizon in HORIZONS_MONTHS
        for family in DIAGNOSTIC_FAMILIES[system]
    }
    if seen != expected:
        raise DeliveryManifestError(
            f"diagnostics must declare every system/horizon/family; missing {sorted(expected - seen)}"
        )


def _contracts(value: Any) -> None:
    _exact_keys(value, CONTRACT_KINDS, "contracts")
    for kind in CONTRACT_KINDS:
        _contract(value[kind], f"contracts.{kind}")
    if value["fill"]["version"] != FILL_POLICY_VERSION:
        raise DeliveryManifestError(f"contracts.fill.version must be {FILL_POLICY_VERSION}")


def _runtime(value: Any) -> None:
    _exact_keys(value, ("image_uri", "environment_manifest"), "runtime")
    if not isinstance(value["image_uri"], str) or not is_digest_pinned_image(value["image_uri"]):
        raise DeliveryManifestError("runtime.image_uri must be pinned by sha256 digest")
    _ref(value["environment_manifest"], "runtime.environment_manifest")


def _release(value: Any, expected_namespace: str | None) -> None:
    _exact_keys(value, ("namespace", "expected_pointer_generation"), "release")
    namespace = value["namespace"]
    if not isinstance(namespace, str) or _NAMESPACE_RE.fullmatch(namespace) is None:
        raise DeliveryManifestError("release.namespace must be a lowercase label")
    if namespace == LEGACY_RELEASE_NAMESPACE:
        raise DeliveryManifestError("release.namespace must not be the legacy IPCCH-only release root")
    if expected_namespace is not None and namespace != expected_namespace:
        raise DeliveryManifestError("release.namespace must equal the configured deployment namespace")
    generation = value["expected_pointer_generation"]
    # "0" means no current pointer is expected (first publication).
    if not isinstance(generation, str) or re.fullmatch(r"0|[1-9][0-9]*", generation) is None:
        raise DeliveryManifestError("release.expected_pointer_generation must be an integer string")


def _ref(value: Any, field: str) -> dict[str, str]:
    """Object references are exact: URI, generation and SHA-256; no prefix or alias."""
    _exact_keys(value, ("uri", "generation", "sha256"), field)
    if not isinstance(value["uri"], str) or _GCS_OBJECT_RE.fullmatch(value["uri"]) is None:
        raise DeliveryManifestError(f"{field}.uri must be a gs:// object URI, not a prefix")
    if not isinstance(value["generation"], str) or _GENERATION_RE.fullmatch(value["generation"]) is None:
        raise DeliveryManifestError(f"{field}.generation must be a positive integer string")
    _sha256(value["sha256"], f"{field}.sha256")
    return dict(value)


def _contract(value: Any, field: str) -> dict[str, str]:
    _exact_keys(value, ("version", "sha256"), field)
    _text(value["version"], f"{field}.version")
    _sha256(value["sha256"], f"{field}.sha256")
    return dict(value)


def _object(value: Any, fields: tuple[str, ...], label: str) -> Mapping[str, Any]:
    _exact_keys(value, fields, label)
    return value


def _exact_keys(value: Any, fields: tuple[str, ...], label: str) -> None:
    if not isinstance(value, Mapping):
        raise DeliveryManifestError(f"{label} must be an object")
    missing = [field for field in fields if field not in value]
    extra = sorted(set(value) - set(fields))
    if missing or extra:
        raise DeliveryManifestError(f"{label} fields mismatch: missing {missing}, unexpected {extra}")


def _exact_sequence(value: Any, expected: tuple, field: str) -> None:
    if not isinstance(value, list):
        raise DeliveryManifestError(f"{field} must be a list")
    # Exact element type (int for horizons, str for systems); bool and 6.0 are rejected.
    item_type = type(expected[0])
    if any(type(item) is not item_type for item in value):
        raise DeliveryManifestError(f"{field} items must be {item_type.__name__} values")
    if len(value) != len(set(value)):
        raise DeliveryManifestError(f"{field} must be a list without duplicates")
    if sorted(value) != sorted(expected):
        raise DeliveryManifestError(f"{field} must be exactly {list(expected)}")


def _month(value: Any, field: str) -> str:
    if not isinstance(value, str) or _MONTH_RE.fullmatch(value) is None:
        raise DeliveryManifestError(f"{field} must be YYYY-MM")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeliveryManifestError(f"{field} must be a non-empty string")
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise DeliveryManifestError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _timestamp(value: Any, field: str) -> None:
    """The preparation cutoff is an instant: full date and time in UTC (``Z``)."""
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        raise DeliveryManifestError(f"{field} must be an RFC3339 UTC timestamp YYYY-MM-DDTHH:MM:SS[.ffffff]Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DeliveryManifestError(f"{field} must be an RFC3339 UTC timestamp") from exc
