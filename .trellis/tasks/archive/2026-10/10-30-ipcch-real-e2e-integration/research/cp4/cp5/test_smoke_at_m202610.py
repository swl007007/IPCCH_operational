"""CP5 offline pre-check (task 10-30): the deployed smoke route (runtime smoke providers, fixture bundle, fixture
country reference) at the execution month the live freeze will actually produce (2026-10 -> O 2026-08), generation +
inference + current publication on fake stores. The committed suite exercises 2027-03 only."""

import json

from cloud.ipcch import entrypoint_v2 as ep
from cloud.ipcch import publication as pub
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.test_ipcch_generation import package  # noqa: F401 (fixture)


def test_smoke_route_at_execution_month_2026_10(tmp_path, package):   # noqa: F811
    from tests.cloud.test_ipcch_entrypoint_v2 import ROOTS, Reader, config, put_request
    from tests.cloud.test_ipcch_run_v2 import raw, smoke_world
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package, providers={"smoke": "cloud.ipcch.smoke_providers:entrypoint_providers",
                                               "real": "cloud.ipcch.entrypoint_v2:real_providers"})
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", execution_month="2026-10", inference=True))
    req["publication"] = "current"
    out = ep.run(cfg, request_uri=put_request(refs, req), request_generation="1", store=store,
                 reader=Reader(refs, store))
    print("SMOKE_2026_10", json.dumps({k: out[k] for k in ("status",)}),
          json.dumps(out["systems"]["ipcch"]["result"]["publication"], default=str)[:600])
    assert out["status"] == "succeeded"
    rec = pub.read_current(store, ROOTS["smoke"], "smoke")["record"]["systems"]["ipcch"]
    assert rec["mode"] == "smoke" and rec["execution_month"] == "2026-10" and rec["feature_origin"] == "2026-08"
