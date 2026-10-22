"""The cloud Workflow reads the pinned request and dispatches the selected steps (definition checks),
and ``resolve`` binds a remote-update intent only to its succeeded preparation."""

import hashlib
import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from cloud.common.object_store import LocalObjectStore  # noqa: E402
from cloud.orchestrator import delivery_job as dj  # noqa: E402
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from cloud.orchestrator import delivery_run  # noqa: E402
from tests.cloud import test_delivery_manifest as tm  # noqa: E402

WORKFLOW = Path(__file__).resolve().parents[2] / "deploy/workflow.yaml"
STEPS = yaml.safe_load(WORKFLOW.read_text())["main"]["steps"]
BY_NAME = {name: body for step in STEPS for name, body in step.items()}


def _args(step):
    return BY_NAME[step]["args"]["body"]["overrides"]["containerOverrides"][0]["args"]


def _flags(args):
    tail = args[3:]
    return [value for value in tail[::2]]


def test_trigger_filter_ignores_the_workflows_own_resolved_writes():
    pattern = BY_NAME["filter"]["switch"][0]["condition"]
    regex = re.search(r'"(\^requests/.+?\$)"', pattern).group(1).replace("\\\\", "\\")
    assert re.match(regex, "requests/oct2026-r2/run_manifest.json")
    assert not re.match(regex, "resolved_requests/oct2026-r2/run_manifest.json")
    assert delivery_run.request_from_event({"bucket": "b", "name": "resolved_requests/r1/run_manifest.json",
                                            "generation": 3}) is None


def test_request_is_read_at_the_event_generation_and_routed_by_its_execution_block():
    read = BY_NAME["read_intent"]
    assert read["call"] == "googleapis.storage.v1.objects.get" and read["args"]["generation"] == "${generation}"
    conditions = [case["condition"] for case in BY_NAME["route"]["switch"]]
    assert conditions == ["${execution == null}", "${not(execution.remote_update)}"]
    assert all(case["next"] == "run_job" for case in BY_NAME["route"]["switch"])  # legacy/remote-off: as before


def test_remote_update_runs_the_prepare_job_on_the_exact_prepare_request():
    args = _args("run_prepare_job")
    assert args[:3] == ["-m", "cloud.orchestrator.prepare", "plan"]
    assert _flags(args) == ["--request-uri", "--request-generation", "--output-root", "--earth-engine-project",
                            "--batch-parent", "--batch-image-uri", "--batch-service-account"]
    assert args[4] == "${prepare_uri}" and args[6] == "${prepare_generation}"
    assert BY_NAME["run_prepare_job"]["args"]["connector_params"] == {"skip_polling": True}


def test_readiness_is_the_durable_status_object_with_a_bounded_wait_never_the_job():
    wait = BY_NAME["wait_for_preparation"]
    assert wait["try"]["call"] == "googleapis.storage.v1.objects.get"
    assert BY_NAME["locate_preparation"]["assign"][4] == {
        "status_object": '${"prepared/" + prepare_id + "/prepare_status.json"}'}
    retry = wait["except"]["steps"][0]["status_not_written"]["switch"][0]
    assert retry["condition"] == "${e.code == 404 and polls < max_polls}" and retry["next"] == "sleep_before_poll"
    assert "raise" in wait["except"]["steps"][1]["preparation_unavailable"]
    assert BY_NAME["count_poll"]["next"] == "wait_for_preparation"
    outcome = BY_NAME["preparation_outcome"]["switch"]
    assert outcome[0]["condition"] == '${prepare_status.status != "succeeded"}' and "raise" in outcome[0]
    assert outcome[1]["condition"] == "${len(execution.inference_systems) == 0}" and "return" in outcome[1]
    assert BY_NAME["preparation_outcome"]["next"] == "run_resolve_job"
    names = list(BY_NAME)
    assert names.index("run_prepare_job") < names.index("wait_for_preparation") < names.index("run_resolve_job")


def test_resolve_job_argv_parses_with_every_configured_flag():
    args = _args("run_resolve_job")
    assert args[:3] == ["-m", "cloud.orchestrator.delivery_job", "resolve"]
    assert _flags(args) == ["--request-uri", "--request-generation", "--output-root", "--release-namespace",
                            "--image-uri"]
    with pytest.raises(SystemExit) as missing:
        dj.main(["resolve", "--request-uri", "gs://b/requests/r1/run_manifest.json"])
    assert missing.value.code == 2


# --- resolve_intent -------------------------------------------------------------------------------


class Reader:
    def __init__(self, objects):
        self.objects = objects

    def read_bytes(self, uri, generation):
        return self.objects.get((uri, str(generation)))


def _intent(prepare_ref, *, inference=("fewsnet",)):
    request = tm._request()
    request["prepared_snapshot"] = None
    request["execution"] = {"remote_update": True, "inference_systems": list(inference),
                            "prepare_request": prepare_ref,
                            "inherit": ({"ipcch": {"source_delivery_id": "src", "origin_month": "2026-10",
                                                   "manifest": tm._ref("deliveries/src/manifest.json"),
                                                   "archive": tm._ref("deliveries/src/bundle.tar.gz")}}
                                        if inference == ("fewsnet",) else {}),
                            "publication": "candidate"}
    return request


def _world(tmp_path, *, status="succeeded", request_matches=True):
    store = LocalObjectStore(tmp_path / "gcs")
    prepare_bytes = json.dumps({"prepare_id": "prep-a"}).encode()
    prepare_uri = "gs://data/prepare_requests/prep-a/prepare_request.json"
    prepare_ref = {"uri": prepare_uri, "generation": "5", "sha256": hashlib.sha256(prepare_bytes).hexdigest()}
    reader = Reader({(prepare_uri, "5"): prepare_bytes})
    if status is not None:
        store.write_text("gs://data/prepared/prep-a/prepare_status.json", json.dumps({"status": status}))
    manifest = {"status": "succeeded", "origin_month": "2026-10", "prepare_id": "prep-a",
                "request": prepare_ref if request_matches else {**prepare_ref, "generation": "6"}}
    meta = store.write_text("gs://data/prepared/prep-a/prepared_manifest.json", json.dumps(manifest))
    reader.objects[("gs://data/prepared/prep-a/prepared_manifest.json", str(meta.generation))] = json.dumps(
        manifest).encode()
    intent = _intent(prepare_ref)
    data = json.dumps(intent).encode()
    ref = {"uri": tm.REQUEST_URI, "generation": tm.GENERATION, "sha256": hashlib.sha256(data).hexdigest()}
    return store, reader, ref, data


def test_resolve_binds_the_intent_to_its_succeeded_snapshot_create_only(tmp_path):
    store, reader, ref, data = _world(tmp_path)
    resolved_ref, resolved = dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data",
                                               store=store, reader=reader)
    assert resolved_ref["uri"] == "gs://ipcch-requests/resolved_requests/oct2026-r1/run_manifest.json"
    body = json.loads(resolved)
    assert body["prepared_snapshot"]["prepare_id"] == "prep-a" and body["execution"] == json.loads(data)["execution"]
    validated = dm.validate_delivery_request(body, request_uri=resolved_ref["uri"],
                                             request_generation=resolved_ref["generation"])
    assert dm.selected_systems(validated) == ("fewsnet",)
    again, _ = dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data", store=store,
                                 reader=reader)  # event replay reuses the identical resolution
    assert again == resolved_ref


@pytest.mark.parametrize("change,message", [
    ({"status": "failed"}, "is failed; no inference"),
    ({"request_matches": False}, "not the succeeded preparation of this intent"),
])
def test_resolve_never_proceeds_without_this_intents_succeeded_preparation(tmp_path, change, message):
    store, reader, ref, data = _world(tmp_path, **change)
    with pytest.raises(dj.AcceptanceError, match=message):
        dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data", store=store, reader=reader)


def test_resolve_waits_for_a_status_object_and_rejects_prepare_only_intents(tmp_path):
    store, reader, ref, data = _world(tmp_path, status=None)
    with pytest.raises(dj.AcceptanceError, match="not finished"):
        dj.resolve_intent(intent_ref=ref, intent_bytes=data, output_root="gs://data", store=store, reader=reader)
    prepare_only = _intent(json.loads(data)["execution"]["prepare_request"], inference=())
    raw = json.dumps(prepare_only).encode()
    with pytest.raises(dj.AcceptanceError, match="only an unresolved remote-update intent"):
        dj.resolve_intent(intent_ref={**ref, "sha256": hashlib.sha256(raw).hexdigest()}, intent_bytes=raw,
                          output_root="gs://data", store=store, reader=reader)


def test_a_resolved_path_is_accepted_only_for_bound_remote_update_requests():
    resolved_uri = "gs://ipcch-requests/resolved_requests/oct2026-r1/run_manifest.json"
    with pytest.raises(dm.DeliveryManifestError, match="resolved request"):
        dm.validate_delivery_request(tm._request(), request_uri=resolved_uri, request_generation="3")
