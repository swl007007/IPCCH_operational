import copy
import hashlib

import pytest

from cloud.orchestrator import delivery_manifest as dm


REQUEST_URI = "gs://ipcch-requests/requests/oct2026-r1/run_manifest.json"
GENERATION = "1759900000000001"


def _ref(name):
    return {
        "uri": f"gs://ipcch-delivery/{name}",
        "generation": "17",
        "sha256": hashlib.sha256(name.encode()).hexdigest(),
    }


def _contract(version):
    return {"version": version, "sha256": hashlib.sha256(version.encode()).hexdigest()}


def _package_id(system, horizon):
    return f"{system}-202604-{horizon}m"


def _request():
    models = [
        {
            "system": system,
            "horizon_months": horizon,
            "package_id": _package_id(system, horizon),
            "package_manifest": _ref(f"models/{system}/{horizon}m/package_manifest.json"),
            "acceptance_report": _ref(f"models/{system}/{horizon}m/acceptance.json"),
            "feature_schema_sha256": "b" * 64,
        }
        for system in dm.SYSTEMS
        for horizon in dm.HORIZONS_MONTHS
    ]
    diagnostics = [
        {"system": system, "horizon_months": horizon, "family": family,
         "status": "unavailable", "evidence": None, "reason": "missing_evidence"}
        for system in dm.SYSTEMS
        for horizon in dm.HORIZONS_MONTHS
        for family in dm.DIAGNOSTIC_FAMILIES[system]
    ]
    diagnostics[0] = {
        "system": "fewsnet", "horizon_months": 0, "family": "polygon_confidence",
        "status": "available", "evidence": _ref("evidence/fewsnet/0m/errors.csv"),
        "evidence_model_package_id": _package_id("fewsnet", 0), "evidence_horizon_months": 0,
    }
    return {
        "schema_version": dm.SCHEMA_VERSION,
        "run_id": "oct2026-r1",
        "origin_month": "2026-10",
        "systems": ["fewsnet", "ipcch"],
        "horizons_months": [0, 6, 12],
        "prepared_snapshot": {"prepare_id": "prep-202610-a", "origin_month": "2026-10",
                              "manifest": _ref("prepared/prep-202610-a/prepared_manifest.json")},
        "acled": {"action": "refresh", "raw_upload": _ref("uploads/acled.csv"),
                  "converter_contract": _contract(dm.RAW_CONVERTER_CONTRACT_VERSION)},
        "wfp": {"action": "keep", "retained_snapshot": _ref("snapshots/wfp-202609.csv"),
                "converter_contract": _contract(dm.RAW_CONVERTER_CONTRACT_VERSION)},
        "models": models,
        "assets": {system: {kind: _ref(f"assets/{system}/{kind}") for kind in dm.ASSET_KINDS[system]}
                   for system in dm.SYSTEMS},
        "diagnostics": diagnostics,
        "contracts": {"feature": _contract("feature-v1"), "fill": _contract(dm.FILL_POLICY_VERSION),
                      "output": _contract("september-v3-output-v1"), "diagnostic": _contract("diag-v1")},
        "runtime": {"image_uri": "europe-docker.pkg.dev/p/r/delivery@sha256:" + "c" * 64,
                    "environment_manifest": _ref("runtime/environment.json")},
        "release": {"namespace": "dual-system", "expected_pointer_generation": "0"},
        "operator": "operator@ifpri.example",
        "prepared_at": "2026-10-03T12:00:00Z",
    }


def _validate(data, **kwargs):
    kwargs.setdefault("request_uri", REQUEST_URI)
    kwargs.setdefault("request_generation", GENERATION)
    return dm.validate_delivery_request(data, **kwargs)


def test_valid_request_is_structural_only_and_binds_request_identity():
    validated = _validate(_request(), expected_release_namespace="dual-system")

    assert validated["validation_level"] == "structural"
    assert validated["request"] == {"uri": REQUEST_URI, "generation": GENERATION}
    assert len(dm.iter_object_refs(validated)) == 1 + 2 + 12 + 11 + 1 + 1
    assert any("prep-202610-a" in item for item in dm.acceptance_requirements(validated))


@pytest.mark.parametrize("acled_action", ["keep", "refresh"])
@pytest.mark.parametrize("wfp_action", ["keep", "refresh"])
def test_all_four_source_choices_validate(acled_action, wfp_action):
    data = _request()
    for source, action in (("acled", acled_action), ("wfp", wfp_action)):
        field = "retained_snapshot" if action == "keep" else "raw_upload"
        data[source] = {"action": action, field: _ref(f"{source}/{field}"),
                        "converter_contract": _contract(dm.RAW_CONVERTER_CONTRACT_VERSION)}

    validated = _validate(data)

    fields = dict(dm.iter_object_refs(validated))
    assert ("acled.retained_snapshot" if acled_action == "keep" else "acled.raw_upload") in fields
    assert ("wfp.retained_snapshot" if wfp_action == "keep" else "wfp.raw_upload") in fields


def _mutations():
    def setter(path, value):
        def apply(data):
            target = data
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return apply

    def drop(path):
        def apply(data):
            target = data
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
        return apply

    return [
        (setter(("schema_version",), "v0"), {}, "schema_version"),
        (setter(("run_id",), "other-run"), {}, "request path run ID"),
        (setter(("run_id",), "Oct 2026"), {}, "run_id must be"),
        (lambda d: None, {"request_uri": "gs://ipcch-requests/uploads/run_manifest.json"}, "request_uri"),
        (lambda d: None, {"request_generation": "0"}, "request_generation"),
        (setter(("command",), "rm -rf /"), {}, "unexpected \\['command'\\]"),
        (drop(("operator",)), {}, "missing \\['operator'\\]"),
        (setter(("origin_month",), "2026-13"), {}, "origin_month"),
        (setter(("systems",), ["fewsnet"]), {}, "systems must be exactly"),
        (setter(("systems",), ["fewsnet", "fewsnet", "ipcch"]), {}, "without duplicates"),
        (setter(("horizons_months",), [0, 5, 6, 12]), {}, "horizons_months must be exactly"),
        (setter(("horizons_months",), [0, 6, 6]), {}, "without duplicates"),
        (setter(("prepared_snapshot", "origin_month"), "2026-09"), {}, "prepared_snapshot.origin_month"),
        (setter(("prepared_snapshot", "manifest", "uri"), "gs://ipcch-delivery/prepared/"), {}, "not a prefix"),
        (setter(("prepared_snapshot", "manifest", "uri"), "/mnt/c/local/prepared.json"), {}, "gs:// object URI"),
        (drop(("prepared_snapshot", "manifest", "generation")), {}, "missing \\['generation'\\]"),
        (setter(("prepared_snapshot", "manifest", "sha256"), "A" * 64), {}, "lowercase SHA-256"),
        (setter(("acled", "action"), "latest"), {}, "acled.action"),
        (setter(("wfp",), {"action": "keep", "raw_upload": _ref("x"),
                           "converter_contract": _contract(dm.RAW_CONVERTER_CONTRACT_VERSION)}), {}, "wfp fields mismatch"),
        (setter(("wfp", "converter_contract"), _contract("legacy-wfp-reader")), {}, "converter_contract.version"),
        (setter(("contracts", "fill"), _contract("global-ffill-zero")), {}, "contracts.fill.version"),
        (setter(("runtime", "image_uri"), "europe-docker.pkg.dev/p/r/delivery:latest"), {}, "pinned by sha256"),
        (setter(("release", "namespace"), "released"), {}, "legacy IPCCH-only"),
        (setter(("release", "expected_pointer_generation"), 3), {}, "expected_pointer_generation"),
        (lambda d: None, {"expected_release_namespace": "other"}, "configured deployment namespace"),
        (setter(("prepared_at",), "2026-10-03 12:00"), {}, "prepared_at"),
        (setter(("prepared_at",), "2026-10-03Z"), {}, "prepared_at"),
        (setter(("prepared_at",), "2026-10-03T12:00:00+02:00"), {}, "prepared_at"),
        (setter(("prepared_at",), "2026-13-03T12:00:00Z"), {}, "prepared_at"),
        (setter(("horizons_months",), [0.0, 6.0, 12.0]), {}, "horizons_months items must be int"),
        (setter(("horizons_months",), [0, "6", 12]), {}, "horizons_months items must be int"),
        (setter(("horizons_months",), [False, 6, 12]), {}, "horizons_months items must be int"),
        (setter(("systems",), ["fewsnet", 1]), {}, "systems items must be str"),
        (setter(("models", 0, "horizon_months"), 0.0), {}, "horizon_months must be an integer"),
        (setter(("diagnostics", 1, "evidence"), _ref("evidence/x.csv")), {}, "evidence must be null"),
        (drop(("diagnostics", 1, "evidence")), {}, "missing \\['evidence'\\]"),
        (setter(("diagnostics", 0, "evidence"), None), {}, "uri must be|must be an object"),
        (drop(("assets", "ipcch", "fixed_features")), {}, "assets.ipcch fields mismatch"),
    ]


@pytest.mark.parametrize(("mutate", "kwargs", "message"), _mutations())
def test_invalid_requests_are_rejected(mutate, kwargs, message):
    data = _request()
    mutate(data)

    with pytest.raises(dm.DeliveryManifestError, match=message):
        _validate(data, **kwargs)


def test_models_must_cover_six_distinct_packages_without_relabeling():
    missing = _request()
    missing["models"].pop()
    duplicate = _request()
    duplicate["models"][1] = copy.deepcopy(duplicate["models"][0])
    relabeled = _request()
    relabeled["models"][1]["package_id"] = relabeled["models"][0]["package_id"]
    h5 = _request()
    h5["models"][0]["horizon_months"] = 5

    for data, message in ((missing, "cover exactly"), (duplicate, "duplicate model"),
                          (relabeled, "no relabeled models"), (h5, "unsupported system/horizon")):
        with pytest.raises(dm.DeliveryManifestError, match=message):
            _validate(data)


def test_diagnostics_must_be_declared_and_bound_to_matching_evidence():
    missing = _request()
    missing["diagnostics"].pop()
    h5_proxy = _request()
    h5_proxy["diagnostics"][0]["evidence_horizon_months"] = 5
    other_package = _request()
    other_package["diagnostics"][0]["evidence_model_package_id"] = "fewsnet-202609-h5"
    bad_reason = _request()
    bad_reason["diagnostics"][1]["reason"] = "zero_error"
    wrong_family = _request()
    wrong_family["diagnostics"][1]["family"] = "maximum_phase"

    cases = ((missing, "every system/horizon/family"), (h5_proxy, "evidence horizon must equal 0"),
             (other_package, "evidence must belong to model package"), (bad_reason, "reason must be"),
             (wrong_family, "not a fewsnet diagnostic"))
    for data, message in cases:
        with pytest.raises(dm.DeliveryManifestError, match=message):
            _validate(data)


def test_reference_identities_are_checked_against_actual_objects():
    validated = _validate(_request())
    actual = {ref["uri"]: ref["sha256"] for _, ref in dm.iter_object_refs(validated)}

    verified = dm.verify_reference_identities(validated, lambda uri, generation: actual.get(uri))
    assert len(verified) == len(actual)

    wrong = dict(actual)
    wrong[validated["acled"]["raw_upload"]["uri"]] = "d" * 64
    with pytest.raises(dm.ReferenceIdentityError, match="acled.raw_upload sha256 mismatch"):
        dm.verify_reference_identities(validated, lambda uri, generation: wrong.get(uri))
    with pytest.raises(dm.ReferenceIdentityError, match="not found"):
        dm.verify_reference_identities(validated, lambda uri, generation: None)
    with pytest.raises(dm.ReferenceIdentityError, match="structural validation first"):
        dm.verify_reference_identities(_request(), lambda uri, generation: None)
