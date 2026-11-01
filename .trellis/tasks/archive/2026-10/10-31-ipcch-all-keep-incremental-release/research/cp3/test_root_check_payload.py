"""Offline branch checks of root_check_payload.run (fakes; no network) + the pinned SDK request mapping."""
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import root_check_payload as rc  # noqa: E402


class Resp:
    def __init__(self, status):
        self.status = status


class HttpError(Exception):
    def __init__(self, status, body=b'{"error":{}}'):
        super().__init__(f"HTTP {status}")
        self.resp, self.content = Resp(status), body


def ee_error(status):
    """EEException raised while handling an HttpError (the SDK's wrapping), so __context__ carries the status."""
    try:
        raise HttpError(status)
    except HttpError:
        try:
            raise RuntimeError(f"EEException: status {status}")
        except RuntimeError as exc:
            return exc


class Api:
    def __init__(self, lists, create=None):
        self.lists, self.create, self.calls = list(lists), create, []

    def list_root(self):
        self.calls.append("list")
        r = self.lists.pop(0)
        if isinstance(r, BaseException):
            raise r
        return {"assets": []}

    def create_root(self):
        self.calls.append("create")
        if isinstance(self.create, BaseException):
            raise self.create
        return {"name": rc.ROOT, "type": "FOLDER"}



def absent_ok(ids):
    return list(ids)


OK_ID = {"metadata_server_email": rc.EXPECTED_IDENTITY}


@pytest.mark.parametrize("ident", [{"metadata_server_email": "other@x.iam.gserviceaccount.com"},
                                   {"metadata_server_error": "ConnectionError: metadata unreachable"},
                                   {"metadata_server_email": rc.EXPECTED_IDENTITY, "metadata_server_error": "x"}, {}])
def test_identity_mismatch_or_metadata_error_stops_before_any_call(ident):
    api = Api(["ok"])
    called = []
    code, res = rc.run(api, lambda ids: called.append(ids) or ids, ident)
    assert code == 2 and res["branch"] == "stop_identity" and api.calls == [] and not called


def test_listable_root_never_creates():
    api = Api(["ok"])
    code, res = rc.run(api, absent_ok, OK_ID)
    assert code == 0 and res["passed"] and res["branch"] == "listable_no_create" and "create" not in api.calls


def test_404_creates_exactly_once_then_relists():
    api = Api([ee_error(404), "ok"])
    code, res = rc.run(api, absent_ok, OK_ID)
    assert code == 0 and res["created"] and api.calls.count("create") == 1 and api.calls[:3] == ["list", "create", "list"]


def test_409_already_exists_is_readback_only():
    api = Api([ee_error(404), "ok"], create=ee_error(409))
    code, res = rc.run(api, absent_ok, OK_ID)
    assert code == 0 and not res["created"] and res["branch"] == "already_exists_readback_only"
    assert api.calls.count("create") == 1


@pytest.mark.parametrize("err", [ee_error(403), ee_error(500), socket.timeout("timed out")])
def test_create_failure_stops_without_relist_or_transport(err):
    api = Api([ee_error(404)], create=err)
    called = []
    code, res = rc.run(api, lambda ids: called.append(ids) or ids, OK_ID)
    assert code == 2 and res["branch"] == "stop_create_failed" and api.calls == ["list", "create"] and not called


@pytest.mark.parametrize("err", [ee_error(403), ee_error(500), socket.timeout("timed out")])
def test_list_permission_timeout_or_error_stops_without_create(err):
    api = Api([err])
    code, res = rc.run(api, absent_ok, OK_ID)
    assert code == 2 and res["branch"] == "stop_list_failed" and api.calls == ["list"]


def test_relist_failure_after_create_stops():
    api = Api([ee_error(404), ee_error(404)])
    code, res = rc.run(api, absent_ok, OK_ID)
    assert code == 2 and res["branch"] == "created+stop_relist_failed" and api.calls.count("create") == 1


def test_transport_absent_child_must_be_reported_absent():
    code, res = rc.run(Api(["ok"]), lambda ids: [], OK_ID)
    assert code == 2 and res["branch"].endswith("+stop_transport_absent_child") and not res["passed"]


def test_http_status_and_body_from_context():
    e = ee_error(404)
    assert rc.http_status(e) == 404 and rc.http_body(e).startswith('{"error"')
    assert rc.http_status(socket.timeout("x")) is None


def test_pinned_sdk_request_mapping(monkeypatch):
    """ee 1.7.36: createAsset({'type':'FOLDER'}, 'projects/P/assets/') -> assets.create(parent='projects/P', assetId='',
    body={'type':'FOLDER'}); listAssets({'parent':'projects/P/assets'}) -> projects.listAssets(parent='projects/P')."""
    import ee
    from ee import data
    assert ee.__version__ == "1.7.36"
    seen = {}

    class Assets:
        def create(self, **kw):
            seen["create"] = kw
            return "CREATE_CALL"

    class Projects:
        def assets(self):
            return Assets()

        def listAssets(self, **kw):
            seen["list"] = kw
            return "LIST_CALL"

        def listAssets_next(self, request, response):      # the SDK follows pages itself; one page here
            seen["list_pages"] = seen.get("list_pages", 0) + 1
            return None

    monkeypatch.setattr(data, "_get_cloud_projects", lambda: Projects())
    monkeypatch.setattr(data, "_execute_cloud_call", lambda call, num_retries=None: {"called": call})
    assert data.createAsset({"type": "FOLDER"}, rc.ROOT) == {"called": "CREATE_CALL"}
    assert seen["create"]["parent"] == "projects/feisty-flames-511718-d4" and seen["create"]["assetId"] == ""
    assert seen["create"]["body"]["type"] == "FOLDER"
    monkeypatch.setattr(data, "_execute_cloud_call", lambda call, num_retries=None: {"assets": [], "called": call})
    assert data.listAssets({"parent": rc.LIST_PARENT, "pageSize": 1}) == {"assets": []}
    assert seen["list"]["parent"] == "projects/feisty-flames-511718-d4" and seen["list_pages"] == 1


def test_budget_exhausted_starts_no_further_call():
    left = iter([100, 100, 2])              # list ok, create ok, then too little budget to relist
    api = Api([ee_error(404), "ok"])
    code, res = rc.run(api, absent_ok, OK_ID, budget=lambda: next(left))
    assert code == 2 and api.calls == ["list", "create"] and res["steps"][-1]["not_started"]


def test_pinned_sdk_init_keeps_zero_retries_and_custom_transport(monkeypatch):
    """data.initialize after setMaxRetries(0): resources are built with num_retries=0 and OUR http_transport (whose
    socket timeout bounds discovery/getAlgorithms/list/create); no network (builder recorded)."""
    from ee import _cloud_api_utils as cau
    from ee import data
    built = []
    monkeypatch.setattr(cau, "build_cloud_resource", lambda *a, **kw: built.append(kw) or object())
    sentinel = object()
    data.setMaxRetries(0)
    data.initialize(credentials=None, project="feisty-flames-511718-d4", http_transport=sentinel)
    assert data._get_state().max_retries == 0 and len(built) == 2
    assert all(kw["num_retries"] == 0 and kw["http_transport"] is sentinel for kw in built)
