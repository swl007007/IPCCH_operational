"""Task 10-29 v2 request contract: structure, mode, operation conflicts, derived months and month rules (R5, R17,
R19, R23, R36-R39, R60, R66, FCC1, FCC6, FCC8)."""

import copy
from datetime import datetime, timezone

import pytest

from cloud.orchestrator import delivery_request_v2 as v2
from cloud.orchestrator.delivery_manifest import ReferenceIdentityError

NOW = datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc)
URI = "gs://ops-bucket/requests/run-2026-10a/run_manifest.json"


def ref(n):
    return {"uri": f"gs://ops-bucket/objects/o{n}.bin", "generation": str(1000 + n), "sha256": f"{n:064x}"}


KEEP = {"action": "keep"}


def ipcch_gen():
    return {"model_combination": {"combination_id": "ipcch-final-h2h8h14-c1", "envelope": ref(1)}, "country_reference": ref(21),
            "acled": KEEP, "research_inputs": {f: KEEP for f in v2.RESEARCH_FAMILIES}, "history_snapshot": KEEP,
            "wfp": KEEP}


def request(**over):
    base = {"schema_version": v2.SCHEMA_VERSION, "run_id": "run-2026-10a", "mode": "real", "execution_month": "2026-10",
            "operations": {"ipcch_generation": True, "ipcch_inference": True, "fewsnet_generation": False,
                           "fewsnet_inference": False},
            "ipcch": ipcch_gen(), "fewsnet": None, "publication": "current",
            "runtime": {"image_uri": "us-central1-docker.pkg.dev/p/r/img@sha256:" + "a" * 64, "environment_manifest": ref(2)},
            "release": {"namespace": "prod", "expected_pointer_generation": "17"},
            "operator": "ops@example.org", "prepared_at": "2026-10-30T05:00:00Z"}
    base.update(over)
    if base.get("ipcch") and not base["operations"]["ipcch_inference"]:
        base["ipcch"] = {k: v for k, v in base["ipcch"].items() if k != "country_reference"}   # inference input only
    return base


def check(data, current="2026-09", now=NOW):
    return v2.validate_request_v2(data, request_uri=URI, request_generation="5", now_utc=now, production_namespace="prod",
                                  smoke_namespace="smoke", current_ipcch_execution_month=current)


def refused(data, text, **kw):
    with pytest.raises(v2.DeliveryRequestV2Error, match=text):
        check(data, **kw)


def ops(**sel):
    return {k: bool(sel.get(k, False)) for k in v2.OPERATIONS}


def test_valid_combined_ipcch_request_and_derived_months():
    out = check(request())
    assert out["derived"]["feature_origin"] == "2026-08"
    assert [(h["model_horizon_months"], h["public_lead_months"], h["target_month"]) for h in out["derived"]["horizons"]] \
        == [(2, 0, "2026-10"), (8, 6, "2027-04"), (14, 12, "2027-10")]
    assert out["validation_level"] == "structural" and out["request"]["generation"] == "5"


def test_mode_is_required_and_closed():
    data = request()
    del data["mode"]
    refused(data, "fields mismatch")
    refused(request(mode="test"), "mode must be one of")
    refused(request(mode=None), "mode must be one of")


def test_no_operation_and_block_presence():
    refused(request(operations=ops()), "select no step")
    refused(request(operations=ops(ipcch_generation=True, ipcch_inference=True, fewsnet_generation=True)),
            "fewsnet must be an object exactly when")
    refused(request(ipcch=None), "ipcch must be an object exactly when")
    refused(request(operations={**ops(ipcch_generation=True), "ipcch_inference": 1}), "booleans")


def test_smoke_selects_ipcch_only_and_its_own_namespace():
    smoke = request(mode="smoke", release={"namespace": "smoke", "expected_pointer_generation": "0"})
    assert check(smoke)["mode"] == "smoke"
    refused(request(mode="smoke"), "release.namespace must equal")                     # production namespace
    fews = request(mode="smoke", release={"namespace": "smoke", "expected_pointer_generation": "0"},
                   operations=ops(ipcch_generation=True, fewsnet_generation=True),
                   fewsnet={"acled": {"action": "keep", "retained_snapshot": ref(9), "converter_contract":
                                      {"version": "september-h5-raw-converter-v1", "sha256": "b" * 64}},
                            "wfp": {"action": "keep", "retained_snapshot": ref(10), "converter_contract":
                                    {"version": "september-h5-raw-converter-v1", "sha256": "b" * 64}},
                            "prepare_request": ref(11)})
    refused(fews, "IPCCH operations only")


def test_inference_only_needs_exactly_one_batch_and_no_refresh():
    inf = request(operations=ops(ipcch_inference=True),
                  ipcch={"model_combination": ipcch_gen()["model_combination"], "country_reference": ref(21),
                         "feature_batch": {"batch_id": "batch-2026-10a", "manifest": ref(3)}})
    assert check(inf)["ipcch"]["feature_batch"]["batch_id"] == "batch-2026-10a"
    missing = copy.deepcopy(inf)
    del missing["ipcch"]["feature_batch"]
    refused(missing, "must name an existing feature batch")
    keep_ok = copy.deepcopy(inf)
    keep_ok["ipcch"]["acled"] = KEEP
    assert check(keep_ok)
    refreshes = {
        "acled": {"action": "refresh", "file": ref(4), "start": "2026-01-03", "end": "2026-09-25", "regions": ["Eastern Africa"]},
        "research_inputs": {**{f: KEEP for f in v2.RESEARCH_FAMILIES},
                            "nino34_anom": {"action": "refresh", "file": ref(5), "start": "2026-01", "end": "2026-08"}},
        "history_snapshot": {"action": "refresh", "file": ref(6)},
        "wfp": {"action": "refresh", "file": ref(7), "start": "2026-01", "end": "2026-08"}}
    for key, choice in refreshes.items():
        bad = copy.deepcopy(inf)
        bad["ipcch"][key] = choice
        refused(bad, "inference-only cannot refresh")


def test_generation_plus_inference_never_names_a_batch_and_declares_every_input():
    data = request()
    data["ipcch"]["feature_batch"] = {"batch_id": "old", "manifest": ref(3)}
    refused(data, "feature_batch is only for IPCCH inference-only")
    gen_only = request(operations=ops(ipcch_generation=True))
    del gen_only["ipcch"]["wfp"]
    refused(gen_only, "declares keep or refresh for every input")


def test_month_rules_real_and_smoke():
    refused(request(execution_month="2026-11"), "later than the current UTC month")
    assert check(request(execution_month="2026-10"))                                   # same month as now
    smoke = request(mode="smoke", execution_month="2027-03", release={"namespace": "smoke", "expected_pointer_generation": "0"})
    assert check(smoke)                                                               # smoke: no wall-clock check
    refused(request(execution_month="2026-08"), "earlier than the current IPCCH release month")
    assert check(request(execution_month="2026-08", publication="candidate"))          # FCC6: candidate exempt
    assert check(request(execution_month="2026-08", operations=ops(ipcch_generation=True)))   # generation-only
    assert check(request(execution_month="2026-09"))                                   # same M as current: rerun
    assert check(request(execution_month="2026-08"), current=None)                     # nothing current
    late_utc = datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)
    refused(request(execution_month="2026-11"), "later than", now=late_utc)


def test_acled_refresh_declaration():
    def acled(**over):
        base = {"action": "refresh", "file": ref(4), "start": "2009-12-26", "end": "2016-12-30", "regions": ["Eastern Africa"]}
        data = request()
        data["ipcch"]["acled"] = {**base, **over}
        return data
    assert check(acled())                                                             # Saturday .. Friday
    refused(acled(start="2009-12-27"), "Saturday start")
    refused(acled(end="2016-12-31"), "Friday end")
    refused(acled(start="2016-12-31", end="2009-12-25"), "Saturday start to a later Friday")
    refused(acled(regions=[]), "non-empty list")
    refused(acled(regions=["A", "A"]), "unique")
    refused(acled(start="2009-02-30"), "valid date")
    keep_extra = request()
    keep_extra["ipcch"]["acled"] = {"action": "keep", "file": ref(4)}
    refused(keep_extra, "keep carries no other field")


def test_research_inputs_and_snapshot_shapes():
    data = request()
    data["ipcch"]["research_inputs"]["idp_local"] = {"action": "refresh", "file": ref(5), "start": "2026-08", "end": "2026-01"}
    refused(data, "reversed")
    data = request()
    del data["ipcch"]["research_inputs"]["bbg_oilgas"]
    refused(data, "fields mismatch")
    data = request()
    data["ipcch"]["history_snapshot"] = {"action": "refresh", "file": ref(6), "start": "2026-01", "end": "2026-08"}
    refused(data, "fields mismatch")                                                 # FCC8: no interval fields


def fews_delivery():
    """A complete FEWS NET delivery block (the v1 models/assets/diagnostics/contracts rules, FEWS NET only)."""
    from cloud.orchestrator import delivery_manifest as dm
    models = [{"system": "fewsnet", "horizon_months": h, "package_id": f"fewsnet-202610-{h}m",
               "package_manifest": ref(40 + h), "acceptance_report": ref(60 + h), "feature_schema_sha256": "b" * 64}
              for h in dm.HORIZONS_MONTHS]
    diagnostics = [{"system": "fewsnet", "horizon_months": h, "family": f, "status": "unavailable", "evidence": None,
                    "reason": "missing_evidence"} for h in dm.HORIZONS_MONTHS for f in dm.DIAGNOSTIC_FAMILIES["fewsnet"]]
    diagnostics[0] = {"system": "fewsnet", "horizon_months": 0, "family": "polygon_confidence", "status": "available",
                      "evidence": ref(80), "evidence_model_package_id": "fewsnet-202610-0m", "evidence_horizon_months": 0}
    contract = lambda v: {"version": v, "sha256": "d" * 64}
    return {"models": models, "assets": {"fewsnet": {k: ref(90 + i) for i, k in enumerate(dm.ASSET_KINDS["fewsnet"])}},
            "diagnostics": diagnostics,
            "contracts": {"feature": contract("feature-v1"), "fill": contract(dm.FILL_POLICY_VERSION),
                          "output": contract("september-v3-output-v1"), "diagnostic": contract("diag-v1")}}


def test_fewsnet_operation_mapping():
    choice = {"action": "keep", "retained_snapshot": ref(9), "converter_contract":
              {"version": "september-h5-raw-converter-v1", "sha256": "b" * 64}}
    inf_only = request(operations=ops(fewsnet_inference=True), ipcch=None,
                       fewsnet={"prepared_snapshot": {"prepare_id": "prep-2026-10", "origin_month": "2026-08", "manifest": ref(8)},
                                "delivery": fews_delivery()})
    assert check(inf_only)["fewsnet"]["prepared_snapshot"]["prepare_id"] == "prep-2026-10"
    no_snapshot = copy.deepcopy(inf_only)
    del no_snapshot["fewsnet"]["prepared_snapshot"]
    refused(no_snapshot, "fields mismatch")
    both = request(operations=ops(fewsnet_generation=True, fewsnet_inference=True), ipcch=None,
                   fewsnet={"acled": choice, "wfp": choice, "prepare_request": ref(11), "delivery": fews_delivery()})
    assert "prepared_snapshot" not in check(both)["fewsnet"]
    with_snapshot = copy.deepcopy(both)
    with_snapshot["fewsnet"]["prepared_snapshot"] = inf_only["fewsnet"]["prepared_snapshot"]
    refused(with_snapshot, "fields mismatch")                                        # this run's prepare only
    all_four = request(operations=ops(ipcch_generation=True, ipcch_inference=True, fewsnet_generation=True,
                                      fewsnet_inference=True),
                       fewsnet={"acled": choice, "wfp": choice, "prepare_request": ref(11), "delivery": fews_delivery()})
    assert check(all_four)                                                           # R38: real composes all four


def test_request_identity_and_reference_verification():
    with pytest.raises(v2.DeliveryRequestV2Error, match="request_uri"):
        v2.validate_request_v2(request(), request_uri="gs://ops-bucket/requests/other/run_manifest.json",
                               request_generation="5", now_utc=NOW, production_namespace="prod",
                               smoke_namespace="smoke", current_ipcch_execution_month=None)
    out = check(request())
    refs = dict(v2.iter_object_refs(out))
    assert set(refs) == {"runtime.environment_manifest", "ipcch.model_combination.envelope", "ipcch.country_reference"}
    table = {(r["uri"], r["generation"]): r["sha256"] for r in refs.values()}
    assert len(v2.verify_reference_identities(out, lambda u, g: table.get((u, g)))) == 3
    with pytest.raises(ReferenceIdentityError, match="sha256 mismatch"):
        v2.verify_reference_identities(out, lambda u, g: "f" * 64)
    with pytest.raises(ReferenceIdentityError, match="not found"):
        v2.verify_reference_identities(out, lambda u, g: None)


def test_is_v2_routes_only_the_new_version():
    assert v2.is_v2(request())
    assert not v2.is_v2({"schema_version": "fewsnet-ipcch-delivery-request-v1"})


def test_ipcch_wfp_refresh_is_a_research_prepared_interval_file():
    """Supervisor contract correction 2026-10-30: IPCCH WFP refresh = {action, file, start, end} (research HDX
    processed series, R59 semantics); the old raw_upload/converter shape is FEWS NET only."""
    data = request()
    data["ipcch"]["wfp"] = {"action": "refresh", "file": ref(7), "start": "2026-01", "end": "2026-08"}
    out = check(data)
    assert out["ipcch"]["wfp"]["end"] == "2026-08"
    assert ("ipcch.wfp.file", ref(7)) in v2.iter_object_refs(out)
    old = request()
    old["ipcch"]["wfp"] = {"action": "refresh", "raw_upload": ref(7),
                           "converter_contract": {"version": "september-h5-raw-converter-v1", "sha256": "c" * 64}}
    refused(old, "raw_upload/converter shape is FEWS NET only")
    for bad, match in (({"action": "refresh", "file": ref(7), "start": "2026-09", "end": "2026-08"}, "reversed"),
                       ({"action": "refresh", "file": ref(7), "start": "2026-01"}, "ipcch.wfp"),
                       ({"action": "refresh", "file": ref(7), "start": "2026-1", "end": "2026-08"}, "ipcch.wfp.start")):
        data = request()
        data["ipcch"]["wfp"] = bad
        refused(data, match)


def mixed_request():
    choice = {"action": "keep", "retained_snapshot": ref(9), "converter_contract":
              {"version": "september-h5-raw-converter-v1", "sha256": "b" * 64}}
    return request(operations=ops(ipcch_generation=True, ipcch_inference=True, fewsnet_inference=True),
                   fewsnet={"prepared_snapshot": {"prepare_id": "prep-2026-10", "origin_month": "2026-08",
                                                  "manifest": ref(8)}, "delivery": fews_delivery()})


@pytest.mark.parametrize("mutate,match", [
    (lambda d: d["models"].pop(), "models must cover exactly"),
    (lambda d: d["models"][1].update(package_id="fewsnet-202610-0m"), "distinct packages"),
    (lambda d: d["assets"]["fewsnet"].pop("geometry"), "assets.fewsnet"),
    (lambda d: d["diagnostics"].pop(), "diagnostics must declare every"),
    (lambda d: d["diagnostics"][0].update(evidence_model_package_id="other"), "evidence must belong"),
    (lambda d: d["contracts"]["fill"].update(version="old-fill"), "contracts.fill.version"),
    (lambda d: d["models"].append({**d["models"][0], "system": "ipcch"}), "unsupported system/horizon"),
])
def test_fews_delivery_block_is_fully_validated(mutate, match):
    data = mixed_request()
    mutate(data["fewsnet"]["delivery"])
    refused(data, match)


def test_iter_refs_include_every_nested_fews_delivery_reference():
    out = check(mixed_request())
    fields = [f for f, _ in v2.iter_object_refs(out)]
    assert "fewsnet.delivery.models[6m].package_manifest" in fields and "fewsnet.delivery.assets.history_panel" in fields
    assert "fewsnet.delivery.diagnostics[0m/polygon_confidence].evidence" in fields
    assert sum(f.startswith("fewsnet.delivery.") for f in fields) == 3 * 2 + 5 + 1


def test_integrated_preflight_executes_nothing_when_a_nested_fews_ref_is_invalid():
    """Mixed IPCCH generation + FEWS NET inference: one wrong nested FEWS delivery hash rejects the whole request before
    any IPCCH lock, collection, store write or provider call (R17)."""
    data = mixed_request()
    good = {(r["uri"], r["generation"]): r["sha256"] for _, r in v2.iter_object_refs(check(data))}
    calls = []
    kw = dict(request_uri=URI, request_generation="5", now_utc=NOW, production_namespace="prod",
              smoke_namespace="smoke", current_ipcch_execution_month="2026-09",
              trusted_prefixes={"real": ["gs://ops-bucket/objects/"]}, batch_roots={"real": "gs://ops-bucket/ipcch-v2/real"})
    admitted = v2.admit(data, resolve=lambda u, g: good.get((u, g)), **kw)
    assert admitted["validation_level"] == "admitted" and len(admitted["verified_references"]) == len(good)
    bad = copy.deepcopy(data)
    bad["fewsnet"]["delivery"]["diagnostics"][0]["evidence"] = ref(81)            # a different object
    resolve = lambda u, g: (calls.append((u, g)), good.get((u, g), "f" * 64))[1]
    with pytest.raises(ReferenceIdentityError, match="fewsnet.delivery.diagnostics"):
        v2.admit(bad, resolve=resolve, **kw)
    malformed = copy.deepcopy(data)
    malformed["fewsnet"]["delivery"]["assets"]["fewsnet"]["roster"]["sha256"] = "not-a-hash"
    calls.clear()
    with pytest.raises(v2.DeliveryRequestV2Error):
        v2.admit(malformed, resolve=resolve, **kw)
    assert calls == []                                       # structural refusal: not even a reference lookup


def test_model_combination_references_the_envelope_only():
    data = request()
    data["ipcch"]["model_combination"] = {"combination_id": "c", "package_manifest": ref(1)}
    refused(data, "ipcch.model_combination")                                       # old shape refused
    data["ipcch"]["model_combination"] = {"combination_id": "c", "envelope": ref(1), "package_manifest": ref(2)}
    refused(data, "ipcch.model_combination")
    out = check(request())
    assert ("ipcch.model_combination.envelope", ref(1)) in v2.iter_object_refs(out)


def test_r39_month_rules_apply_to_ipcch_operations_only():
    """A real FEWS NET-only request keeps FEWS month handling: no IPCCH future-M rule, no IPCCH M-2 derivation."""
    choice = {"action": "keep", "retained_snapshot": ref(9), "converter_contract":
              {"version": "september-h5-raw-converter-v1", "sha256": "b" * 64}}
    fews_only = request(operations=ops(fewsnet_generation=True, fewsnet_inference=True), ipcch=None,
                        fewsnet={"acled": choice, "wfp": choice, "prepare_request": ref(11), "delivery": fews_delivery()}, execution_month="2026-12")
    out = check(fews_only)                                                          # M later than the UTC month: allowed
    assert "feature_origin" not in out["derived"] and out["derived"]["fewsnet_origin_month"] == "2026-12"
    inf_only = request(operations=ops(fewsnet_inference=True), ipcch=None,
                       fewsnet={"prepared_snapshot": {"prepare_id": "prep-2026-10", "origin_month": "2026-10", "manifest": ref(8)},
                                "delivery": fews_delivery()})
    assert check(inf_only)["derived"]["fewsnet_origin_month"] == "2026-10"         # the prepared snapshot's own origin
    ipcch_future = request(execution_month="2026-12")
    refused(ipcch_future, "later than the current UTC month")


def test_country_reference_is_an_inference_input_only():
    data = request()
    del data["ipcch"]["country_reference"]
    refused(data, "needs ipcch.country_reference")
    gen = request(operations=ops(ipcch_generation=True))
    gen["ipcch"]["country_reference"] = ref(21)
    refused(gen, "generation-only omits it")
    bad = request()
    bad["ipcch"]["country_reference"] = {"uri": "gs://ops-bucket/objects/", "generation": "1", "sha256": "a" * 64}
    refused(bad, "ipcch.country_reference")


def fews_generation_world(origin="2026-10", outside=False):
    """A real FEWS NET generation + inference request whose prepare_request is the existing both-system schema."""
    import hashlib
    import json

    from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES
    from cloud.orchestrator import prepare
    n = iter(range(200, 400))
    body = {"schema_version": prepare.PREPARE_SCHEMA_VERSION, "prepare_id": "prep-2026-10-v2", "origin_month": origin,
            "cutoff_utc": "2026-10-05T12:00:00Z", "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
            "systems": {s: {"geometry": ref(next(n)), "roster": ref(next(n)),
                            "history": {f: ref(next(n)) for f in SYSTEM_FAMILIES[s]}} for s in ("fewsnet", "ipcch")},
            "operator": "ops@example.org"}
    if outside:                                           # one nested (unused IPCCH) ref outside the trusted namespace
        body["systems"]["ipcch"]["roster"] = {**body["systems"]["ipcch"]["roster"], "uri": "gs://elsewhere/roster.csv"}
    data = json.dumps(body).encode()
    pref = {"uri": "gs://ops-bucket/prepare_requests/prep-2026-10-v2/prepare_request.json", "generation": "7",
            "sha256": hashlib.sha256(data).hexdigest()}
    choice = {"action": "keep", "retained_snapshot": ref(9), "converter_contract":
              {"version": "september-h5-raw-converter-v1", "sha256": "b" * 64}}
    req = request(operations=ops(fewsnet_generation=True, fewsnet_inference=True), ipcch=None, execution_month=origin,
                  fewsnet={"acled": choice, "wfp": choice, "prepare_request": pref, "delivery": fews_delivery()})
    return req, body, {(pref["uri"], pref["generation"]): data}


def test_fews_generation_admission_validates_the_prepare_request_and_every_nested_ref():
    """D1: the pinned prepare_request body is read, validated with the existing validator (origin = FEWS origin) and
    ALL its nested references - including unused IPCCH declarations - are admitted and verified before anything runs."""
    from cloud.orchestrator.delivery_manifest import ReferenceIdentityError
    req, body, blobs = fews_generation_world()
    kw = dict(request_uri=URI, request_generation="5", now_utc=NOW, production_namespace="prod",
              smoke_namespace="smoke", current_ipcch_execution_month=None,
              trusted_prefixes={"real": ["gs://ops-bucket/"]}, batch_roots={"real": "gs://ops-bucket/ipcch-v2/real"},
              read=lambda u, g: blobs.get((u, g)))
    import hashlib
    sha = {(u, g): hashlib.sha256(d).hexdigest() for (u, g), d in blobs.items()}
    out = check(req)
    good = {(r["uri"], r["generation"]): r["sha256"] for _, r in v2.iter_object_refs(out)}
    good.update(sha)
    for s in body["systems"].values():
        for r in (s["geometry"], s["roster"], *s["history"].values()):
            good[(r["uri"], r["generation"])] = r["sha256"]
    admitted = v2.admit(req, resolve=lambda u, g: good.get((u, g)), **kw)
    fields = {r["field"] for r in admitted["verified_references"]}
    assert "fewsnet.prepare_request" in fields and "fewsnet.prepare_request.systems.ipcch.history.gosif_sd" in fields
    assert admitted["fewsnet_prepare"]["prepare_id"] == "prep-2026-10-v2"
    nested = body["systems"]["ipcch"]["roster"]
    with pytest.raises(ReferenceIdentityError, match="systems.ipcch.roster"):           # unused IPCCH ref still verified
        v2.admit(req, resolve=lambda u, g: None if (u, g) == (nested["uri"], nested["generation"]) else good.get((u, g)), **kw)
    other, _, other_blobs = fews_generation_world(origin="2026-09")
    other["execution_month"] = "2026-10"                                                 # prepare origin != FEWS origin
    with pytest.raises(v2.DeliveryRequestV2Error, match="origin 2026-09 is not the FEWS NET origin 2026-10"):
        v2.admit(other, resolve=lambda u, g: "0" * 64, **{**kw, "read": lambda u, g: other_blobs.get((u, g))})
    with pytest.raises(ReferenceIdentityError, match="not the pinned bytes"):
        v2.admit(req, resolve=lambda u, g: good.get((u, g)), **{**kw, "read": lambda u, g: b"{}"})
    far, _, far_blobs = fews_generation_world(outside=True)
    seen = []
    with pytest.raises(v2.DeliveryRequestV2Error, match="systems.ipcch.roster .* outside the trusted real namespace"):
        v2.admit(far, resolve=lambda u, g: seen.append(u), **{**kw, "read": lambda u, g: far_blobs.get((u, g))})
    assert seen == []                                     # lexical refusal before any resolve
    missing = copy.deepcopy(req)
    del missing["fewsnet"]["prepare_request"]
    refused(missing, "fields mismatch")
