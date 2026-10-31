"""Guarded fake-store self-check of readback_v2.post (CP5 evidence code): the smoke route at M=2026-10 publishes to a
fake store; post must pass with the true expectations and fail on a wrong expected M, a forged frozen request
identity and a tampered delivery file."""

import json
import sys
from pathlib import Path

import pytest

from cloud.ipcch import entrypoint_v2 as ep
from cloud.ipcch import publication as pub
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.test_ipcch_generation import package  # noqa: F401

sys.path.insert(0, str(Path(__file__).parent))
import readback_v2 as rb  # noqa: E402


@pytest.fixture
def published(tmp_path, package):   # noqa: F811
    from tests.cloud.test_ipcch_entrypoint_v2 import ROOTS, Reader, config, put_request
    from tests.cloud.test_ipcch_run_v2 import raw, smoke_world
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package, providers={"smoke": "cloud.ipcch.smoke_providers:entrypoint_providers",
                                               "real": "cloud.ipcch.entrypoint_v2:real_providers"})
    pre = pub.read_current(store, cfg["roots"]["smoke"], cfg["namespaces"]["smoke"])
    (tmp_path / "pre.json").write_text(json.dumps(pre))
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", execution_month="2026-10", inference=True))
    req["publication"] = "current"
    out = ep.run(cfg, request_uri=put_request(refs, req), request_generation="1", store=store, reader=Reader(refs, store))
    assert out["status"] == "succeeded"
    reservation = json.loads(store.read_text(f"{cfg['roots']['smoke']}/runs/{req['run_id']}/v2_reservation.json"))
    (tmp_path / "state.json").write_text(json.dumps({"run_id": req["run_id"], "request": reservation["request"]}))
    roster = len(fx.ROSTER) if hasattr(fx, "ROSTER") else None
    return store, cfg, req["run_id"], tmp_path, roster


def run_post(published, name, expect=None, state="state.json"):
    store, cfg, run_id, tmp, roster = published
    exp = expect or {"M": "2026-10", "O": "2026-08", "features": None, "roster": None}
    return rb.post("smoke", run_id, str(tmp / "pre.json"), None, str(tmp / name), str(tmp / state), exp, store=store,
                   cfg=cfg), json.loads((tmp / name).read_text())


def true_expect(published):
    store, cfg, run_id, tmp, _ = published
    body = run_post(published, "probe.json")[1]
    return {"M": "2026-10", "O": "2026-08", "features": body["actual"]["feature_count"],
            "roster": body["actual"]["roster"]["size"]}


def test_post_passes_on_the_published_smoke_run(published):
    rc, body = run_post(published, "ok.json", true_expect(published))
    assert rc == 0 and body["passed"], body["checks"]
    assert body["actual"]["M"] == "2026-10" and body["actual"]["O"] == "2026-08"
    assert set(body["actual"]["targets"]) == {"2", "8", "14"}


def test_post_fails_on_a_wrong_expected_month(published):
    rc, body = run_post(published, "badm.json", {**true_expect(published), "M": "2026-11"})
    assert rc == 1 and body["checks"]["expected_M"] is False


def test_post_fails_on_a_forged_frozen_request(published):
    store, cfg, run_id, tmp, _ = published
    state = json.loads((tmp / "state.json").read_text())
    state["request"]["sha256"] = "0" * 64
    (tmp / "forged.json").write_text(json.dumps(state))
    rc, body = run_post(published, "forged-out.json", true_expect(published), state="forged.json")
    assert rc == 1 and body["checks"]["reserved_request_is_frozen_submission"] is False


def test_post_refuses_a_tampered_delivery_file(published):
    store, cfg, run_id, tmp, _ = published
    rec = pub.read_current(store, cfg["roots"]["smoke"], cfg["namespaces"]["smoke"])["record"]
    base = rec["delivery"]["manifest"]["uri"].rsplit("/", 1)[0]
    entry = json.loads(store.read_text(rec["delivery"]["manifest"]["uri"]))["files"][0]
    uri = f"{base}/{entry['path']}"
    store.write_text(uri, store.read_text(uri) + "x")
    with pytest.raises(Exception, match="differs from the delivery manifest"):
        run_post(published, "tampered.json", true_expect(published))
