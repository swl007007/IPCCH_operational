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
    return {"model_combination": {"combination_id": "ipcch-final-h2h8h14-c1", "package_manifest": ref(1)},
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
                                    {"version": "september-h5-raw-converter-v1", "sha256": "b" * 64}}})
    refused(fews, "IPCCH operations only")


def test_inference_only_needs_exactly_one_batch_and_no_refresh():
    inf = request(operations=ops(ipcch_inference=True),
                  ipcch={"model_combination": ipcch_gen()["model_combination"],
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
        "wfp": {"action": "refresh", "raw_upload": ref(7), "converter_contract": {"version": "september-h5-raw-converter-v1",
                                                                                  "sha256": "c" * 64}}}
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
    return {"models": [], "assets": {}, "diagnostics": [], "contracts": {}}


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
                   fewsnet={"acled": choice, "wfp": choice, "delivery": fews_delivery()})
    assert "prepared_snapshot" not in check(both)["fewsnet"]
    with_snapshot = copy.deepcopy(both)
    with_snapshot["fewsnet"]["prepared_snapshot"] = inf_only["fewsnet"]["prepared_snapshot"]
    refused(with_snapshot, "fields mismatch")                                        # this run's prepare only
    all_four = request(operations=ops(ipcch_generation=True, ipcch_inference=True, fewsnet_generation=True,
                                      fewsnet_inference=True),
                       fewsnet={"acled": choice, "wfp": choice, "delivery": fews_delivery()})
    assert check(all_four)                                                           # R38: real composes all four


def test_request_identity_and_reference_verification():
    with pytest.raises(v2.DeliveryRequestV2Error, match="request_uri"):
        v2.validate_request_v2(request(), request_uri="gs://ops-bucket/requests/other/run_manifest.json",
                               request_generation="5", now_utc=NOW, production_namespace="prod",
                               smoke_namespace="smoke", current_ipcch_execution_month=None)
    out = check(request())
    refs = dict(v2.iter_object_refs(out))
    assert set(refs) == {"runtime.environment_manifest", "ipcch.model_combination.package_manifest"}
    table = {(r["uri"], r["generation"]): r["sha256"] for r in refs.values()}
    assert len(v2.verify_reference_identities(out, lambda u, g: table.get((u, g)))) == 2
    with pytest.raises(ReferenceIdentityError, match="sha256 mismatch"):
        v2.verify_reference_identities(out, lambda u, g: "f" * 64)
    with pytest.raises(ReferenceIdentityError, match="not found"):
        v2.verify_reference_identities(out, lambda u, g: None)


def test_is_v2_routes_only_the_new_version():
    assert v2.is_v2(request())
    assert not v2.is_v2({"schema_version": "fewsnet-ipcch-delivery-request-v1"})
