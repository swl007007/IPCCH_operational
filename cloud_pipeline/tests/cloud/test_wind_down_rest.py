"""REST backend of the wind-down helper (fake session; no cloud calls)."""
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "wind_down", Path(__file__).resolve().parents[2] / "deploy/wind_down.py")
wind_down = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wind_down)


class Response:
    def __init__(self, status, body):
        self.status_code, self.text = status, json.dumps(body) if body is not None else ""


class Session:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url):
        self.calls.append((method, url))
        return self.routes.get((method, url), Response(404, {"error": "not found"}))


RUN = "https://run.googleapis.com/v2/projects/p/locations/l/jobs/oct-deliver-debug/executions/oct-deliver-debug-xfr48"
BATCH = "https://batch.googleapis.com/v1/projects/p/locations/l/jobs/ipcch-prepare-full-window-20261008c"


def test_rest_backend_maps_v2_execution_state_and_targets_exact_resources():
    session = Session({("GET", RUN): Response(200, {"taskCount": 1, "runningCount": 1}),
                       ("GET", BATCH): Response(200, {"status": {"state": "RUNNING"}}),
                       ("POST", RUN + ":cancel"): Response(200, {}), ("DELETE", BATCH): Response(200, {})})
    backend = wind_down.RestBackend(session)

    execution = backend.describe_execution("p", "l", "oct-deliver-debug-xfr48")
    assert wind_down._execution_state(execution) == "RUNNING"
    assert wind_down._batch_state(backend.describe_batch("p", "l", "ipcch-prepare-full-window-20261008c")) == "RUNNING"
    assert backend.cancel_execution("p", "l", "oct-deliver-debug-xfr48")["returncode"] == 0
    assert backend.delete_batch("p", "l", "ipcch-prepare-full-window-20261008c")["returncode"] == 0
    assert [call[1] for call in session.calls] == [RUN, BATCH, RUN + ":cancel", BATCH]


def test_rest_backend_terminal_unknown_and_failed_actions_are_explicit():
    session = Session({("GET", RUN): Response(200, {"taskCount": 1, "succeededCount": 1,
                                                    "completionTime": "2026-10-08T17:00:00Z"})})
    backend = wind_down.RestBackend(session)

    assert wind_down._execution_state(backend.describe_execution("p", "l", "oct-deliver-debug-xfr48")) == "TERMINAL"
    assert wind_down._batch_state(backend.describe_batch("p", "l", "missing-job")) == "UNKNOWN"
    assert backend.delete_batch("p", "l", "missing-job")["returncode"] == 404
