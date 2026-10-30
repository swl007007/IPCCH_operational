"""CP6 operator handoff examples, VALIDATED by the production validators before they are written.

Writes `examples/` (this directory): the v2 deployment config (checked by `entrypoint_v2.load_config`), one v2
request per supported shape (each checked by `delivery_request_v2.validate_request_v2` AND the lexical namespace
admission `admit_namespaces` against the example config; the FEWS generation example also through
`read_prepare_request` with its pinned body and nested refs) and the FEWS NET prepare request body
(`prepare.validate_prepare_request`). Object refs are illustrative
(`gs://ops-real/inputs/...`, generation, sha256 of the name): an operator replaces them with the exact uploaded
objects; the validators check shape and rules, admission later verifies every ref's bytes.

Run: ~/.venvs/fewsnet-test-lock-20261022/bin/python operator_examples.py   (exit 1 if any example is invalid)
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

OP = Path(__file__).resolve().parents[5] / "cloud_pipeline"
sys.path.insert(0, str(OP))

from cloud.ipcch import entrypoint_v2 as ep  # noqa: E402
from cloud.orchestrator import delivery_manifest as dm  # noqa: E402
from cloud.orchestrator import delivery_request_v2 as v2  # noqa: E402
from tests.cloud.ipcch_smoke_fixture import acled_interval  # noqa: E402

OUT = Path(__file__).with_name("examples")
NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
IMAGE = "us-central1-docker.pkg.dev/<project>/<repository>/delivery@sha256:" + "0" * 64


def ref(name: str, bucket: str = "gs://ops-real/inputs") -> dict:
    return {"uri": f"{bucket}/{name}", "generation": "1730000000000001",
            "sha256": hashlib.sha256(name.encode()).hexdigest()}


def deployment() -> dict:
    return {
        "roots": {"real": "gs://example-delivery/v2", "smoke": "gs://example-delivery-smoke/v2"},
        "store_roots": {"real": "gs://example-ipcch-store/ipcch-v2/real", "smoke": "gs://example-ipcch-store/ipcch-v2/smoke"},
        "namespaces": {"production": "prod", "smoke": "smoke"},
        # real: operator inputs, FEWS NET prepare requests (the existing path gs://<bucket>/prepare_requests/<id>/...)
        # and the FEWS NET snapshots a v2 generation writes under roots.real/prepared/; smoke: fixture inputs only
        "trusted_prefixes": {"real": ["gs://ops-real/inputs/", "gs://ops-real/prepare_requests/",
                                      "gs://example-delivery/v2/prepared/"],
                             "smoke": ["gs://ops-smoke/inputs/"]},
        "installed": {
            "real": {"envelope": "/opt/ipcch/envelope/ipcch-combination-envelope-v2-accepted.json",
                     "package_root": "/opt/ipcch/package", "bundle_dir": "/opt/ipcch/handoff-bundle"},
            "smoke": {"envelope": "/opt/ipcch/envelope/ipcch-combination-envelope-v2-accepted.json",
                      "package_root": "/opt/ipcch/package", "bundle_dir": "/opt/ipcch/fixture-root/bundle",
                      "fixture_root": "/opt/ipcch/fixture-root"}},
        "providers": {"real": "cloud.ipcch.entrypoint_v2:real_providers",
                      "smoke": "<fixture module>:entrypoint_providers"},
        "earth_engine_project": "<ee-project>", "export_root": "gs://example-exports/v2", "work_dir": "/tmp/ipcch-v2-work",
        "fewsnet": {"image_uri": IMAGE}}


def base(run_id, mode="real", M="2026-10", **ops) -> dict:
    return {"schema_version": v2.SCHEMA_VERSION, "run_id": run_id, "mode": mode, "execution_month": M,
            "operations": {op: bool(ops.get(op, False)) for op in v2.OPERATIONS}, "ipcch": None, "fewsnet": None,
            "publication": "current", "runtime": {"image_uri": IMAGE, "environment_manifest": ref("env-manifest.json")},
            "release": {"namespace": "prod" if mode == "real" else "smoke", "expected_pointer_generation": "<current gen>"},
            "operator": "operator@example.org", "prepared_at": "2026-11-02T09:00:00Z"}


def combination(bucket="gs://ops-real/inputs") -> dict:
    return {"combination_id": "ipcch-validity-h2h8h14-final-20261030",
            "envelope": ref("ipcch-combination-envelope-v2-accepted.json", bucket)}


def ipcch_generation_inputs(M, bucket="gs://ops-real/inputs") -> dict:
    o = f"{int(M[:4]) - (1 if int(M[5:]) <= 2 else 0):04d}-{(int(M[5:]) - 3) % 12 + 1:02d}"
    start, end = acled_interval(o)
    keep = {"action": "keep"}
    return {"acled": {"action": "refresh", "file": ref("acled-regional-aggregate.csv", bucket), "start": start,
                      "end": end, "regions": ["Eastern Africa", "Middle Africa"]},
            "research_inputs": {f: keep for f in v2.RESEARCH_FAMILIES}, "history_snapshot": keep, "wfp": keep}


def fews_delivery() -> dict:
    contract = lambda v: {"version": v, "sha256": "d" * 64}
    models = [{"system": "fewsnet", "horizon_months": h, "package_id": f"<fews package id>/{h}m",
               "package_manifest": ref(f"fewsnet/{h}m/package_manifest.json"),
               "acceptance_report": ref(f"fewsnet/{h}m/acceptance.json"), "feature_schema_sha256": "e" * 64}
              for h in dm.HORIZONS_MONTHS]
    return {"models": models,
            "assets": {"fewsnet": {k: ref(f"fewsnet/{k}") for k in dm.ASSET_KINDS["fewsnet"]}},
            "diagnostics": [{"system": "fewsnet", "horizon_months": h, "family": f, "status": "unavailable",
                             "evidence": None, "reason": "missing_evidence"}
                            for h in dm.HORIZONS_MONTHS for f in dm.DIAGNOSTIC_FAMILIES["fewsnet"]],
            "contracts": {"feature": contract("feature-v1"), "fill": contract(dm.FILL_POLICY_VERSION),
                          "output": contract("september-v3-output-v1"), "diagnostic": contract("diag-v1")}}


def prepare_request_body() -> dict:
    """The existing FEWS NET preparation request (schema unchanged: both systems declared; the v2 adapter runs it with
    the FEWS NET-only scope). Nested refs are pinned inputs under the trusted real prefix."""
    from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES
    from cloud.orchestrator import prepare
    return {"schema_version": prepare.PREPARE_SCHEMA_VERSION, "prepare_id": "fews-2026-10-a", "origin_month": "2026-10",
            "cutoff_utc": "2026-11-01T00:00:00Z", "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
            "systems": {sys_: {"geometry": ref(f"{sys_}/geometry.geojson"), "roster": ref(f"{sys_}/roster.csv"),
                               "history": {f: ref(f"{sys_}/history/{f}.csv") for f in SYSTEM_FAMILIES[sys_]}}
                        for sys_ in ("fewsnet", "ipcch")},
            "operator": "operator@example.org"}


PREPARE_URI = "gs://ops-real/prepare_requests/fews-2026-10-a/prepare_request.json"


def prepare_request_ref() -> dict:
    data = (json.dumps(prepare_request_body(), indent=2) + "\n").encode()
    return {"uri": PREPARE_URI, "generation": "1730000000000001", "sha256": hashlib.sha256(data).hexdigest()}


def fews_choice(name) -> dict:
    return {"action": "keep", "retained_snapshot": ref(f"retained_{name}.csv"),
            "converter_contract": {"version": dm.RAW_CONVERTER_CONTRACT_VERSION, "sha256": "b" * 64}}


def examples() -> dict[str, dict]:
    out = {}
    r = base("ipcch-2026-10-a", ipcch_generation=True, ipcch_inference=True)
    r["ipcch"] = {"model_combination": combination(), "country_reference": ref("ipcch-country-reference.csv"),
                  **ipcch_generation_inputs("2026-10")}
    out["real-ipcch-generation-inference-current"] = r
    r = base("ipcch-2026-10-gen", ipcch_generation=True)
    r["ipcch"] = {"model_combination": combination(), **ipcch_generation_inputs("2026-10")}
    out["real-ipcch-generation-only"] = r
    r = base("ipcch-2026-10-inf", ipcch_inference=True)
    r["ipcch"] = {"model_combination": combination(), "country_reference": ref("ipcch-country-reference.csv"),
                  "feature_batch": {"batch_id": "ipcch-2026-10-ipcch-2026-10-gen-0a1b2c3d4e5f",
                                    "manifest": ref("feature_batches/ipcch-2026-10-ipcch-2026-10-gen-0a1b2c3d4e5f/"
                                                    "manifest.json", "gs://example-ipcch-store/ipcch-v2/real")}}
    out["real-ipcch-inference-only-named-batch"] = r
    r = base("fews-2026-10-a", fewsnet_generation=True, fewsnet_inference=True)
    r["fewsnet"] = {"acled": fews_choice("acled"), "wfp": fews_choice("wfp"),
                    "prepare_request": prepare_request_ref(),
                    "delivery": fews_delivery()}
    out["real-fewsnet-generation-inference"] = r
    r = base("fews-2026-10-inf", fewsnet_inference=True)
    # the snapshot the combined example's generation writes (roots.real/prepared/<prepare_id>/prepared_manifest.json)
    r["fewsnet"] = {"prepared_snapshot": {"prepare_id": "fews-2026-10-a", "origin_month": "2026-10",
                                          "manifest": ref("fews-2026-10-a/prepared_manifest.json",
                                                          "gs://example-delivery/v2/prepared")},
                    "delivery": fews_delivery()}
    out["real-fewsnet-inference-only-prepared-snapshot"] = r
    r = base("smoke-2026-10-a", mode="smoke", ipcch_generation=True, ipcch_inference=True)
    r["ipcch"] = {"model_combination": combination("gs://ops-smoke/inputs"),
                  "country_reference": ref("fixture-country-reference.csv", "gs://ops-smoke/inputs"),
                  **ipcch_generation_inputs("2026-10", "gs://ops-smoke/inputs")}
    out["smoke-ipcch-generation-inference"] = r
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    cfg_path = OUT / "deployment.example.json"
    cfg_path.write_text(json.dumps(deployment(), indent=2) + "\n")
    ep.load_config(str(cfg_path))                                     # raises on an invalid config
    failures = []
    for name, body in examples().items():
        checked = copy.deepcopy(body)
        checked["release"]["expected_pointer_generation"] = "0"       # placeholder resolved for validation only
        try:
            validated = v2.validate_request_v2(
                checked, request_uri=f"gs://ops-real/requests/{body['run_id']}/run_manifest.json"
                if body["mode"] == "real" else f"gs://ops-smoke/requests/{body['run_id']}/run_manifest.json",
                request_generation="1", now_utc=NOW, production_namespace="prod", smoke_namespace="smoke",
                current_ipcch_execution_month=None)
            cfg = deployment()                                          # lexical admission (R48), before any resolve
            v2.admit_namespaces(validated, cfg["trusted_prefixes"], cfg["store_roots"])
            if "prepare_request" in (validated.get("fewsnet") or {}):  # the pinned body + its nested refs (D1)
                body_bytes = (json.dumps(prepare_request_body(), indent=2) + "\n").encode()
                v2.read_prepare_request(validated, lambda u, g: body_bytes if u == PREPARE_URI else None)
                v2.admit_namespaces(validated, cfg["trusted_prefixes"], cfg["store_roots"])
        except Exception as exc:                                        # noqa: BLE001 - reported, then exit 1
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
        (OUT / f"{name}.json").write_text(json.dumps(body, indent=2) + "\n")
    (OUT / "fews-prepare-request.json").write_text(json.dumps(prepare_request_body(), indent=2) + "\n")
    from cloud.orchestrator.prepare import validate_prepare_request
    pr = prepare_request_ref()
    validate_prepare_request(prepare_request_body(), request_uri=pr["uri"], request_generation=pr["generation"],
                             request_sha256=pr["sha256"])
    print(f"{len(examples())} request examples + prepare request + deployment config written to {OUT}")
    for f in failures:
        print("INVALID", f)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
