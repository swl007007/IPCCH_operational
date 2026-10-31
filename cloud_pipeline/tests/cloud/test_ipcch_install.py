"""Task 10-30 CP3 (R3, R4, AC3, AC4): the concrete v2 deployment config, the verified /opt/ipcch installation (stage +
verify, every member re-hashed, smoke isolated from the real handoff) and the self-contained runtime smoke providers."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cloud.ipcch import binding as bd
from cloud.ipcch import entrypoint_v2 as ep
from cloud.ipcch import install
from cloud.ipcch import publication as pub
from tests.cloud import ipcch_smoke_fixture as fx
from tests.cloud.ipcch_binding_fixtures import finalize_entries
from tests.cloud.test_ipcch_assembly import inputs
from tests.cloud.test_ipcch_binding import add_population
from tests.cloud.test_ipcch_generation import package  # noqa: F401 (fixture)
from tests.cloud.test_ipcch_initial import write_bundle

RUNTIME = Path(__file__).resolve().parents[2]
CONFIG = RUNTIME / "deploy" / "ipcch_v2_deployment.food-crisis-test.json"


# --------------------------------------------------------------------------- concrete deployment config


def test_concrete_deployment_config_is_valid_and_publishes_to_the_legacy_current():
    cfg = ep.load_config(str(CONFIG))
    assert pub.pointer_uri(cfg["roots"]["real"], cfg["namespaces"]["production"]) == \
        "gs://food-crisis-test-ipcch-data/monthly-staging/current.json"
    legacy = "gs://{bucket}/{namespace}/current.json".format(bucket="food-crisis-test-ipcch-data", namespace="monthly-staging")
    assert pub.pointer_uri(cfg["roots"]["real"], cfg["namespaces"]["production"]) == legacy   # pipeline.py's pointer
    smoke, real = (cfg["roots"][m].rstrip("/") + "/" for m in ("smoke", "real"))
    assert not smoke.startswith(real) and not real.startswith(smoke)                         # non-nested (R48)
    assert cfg["store_roots"]["real"].endswith("/real") and cfg["store_roots"]["smoke"].endswith("/smoke")
    assert all(p.startswith("gs://food-crisis-test-ipcch-data/") for p in cfg["trusted_prefixes"]["real"])
    assert not any(p.startswith("gs://food-crisis-test-ipcch-data/") for p in cfg["trusted_prefixes"]["smoke"])
    assert cfg["installed"] == install.expected_installed()
    assert "fewsnet" not in cfg and "@sha256:" not in CONFIG.read_text()                  # no self-referential digest
    assert cfg["run_timeout_seconds"] == ep.RUN_TIMEOUT_SECONDS and cfg["producer_asset_root"] == \
        "projects/feisty-flames-511718-d4/assets/"
    assert cfg["verification"]["status"] == "pending-live-verification" and cfg["verification"]["pending_live_checks"]
    assert ep.resolve_factory(cfg["providers"]["smoke"]).__module__ == "cloud.ipcch.smoke_providers"


def test_runtime_smoke_providers_import_no_test_code():
    probe = ("import sys, cloud.ipcch.smoke_providers as s; "
             "print(sorted(m for m in sys.modules if m == 'pytest' or m.split('.')[0] == 'tests'))")
    out = subprocess.run([sys.executable, "-c", probe], cwd=RUNTIME, capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONPATH": str(RUNTIME)})
    assert out.stdout.strip() == "[]"


# --------------------------------------------------------------------------- stage / verify


@pytest.fixture
def sources(tmp_path, package):                                           # noqa: F811
    real = tmp_path / "real"
    real.mkdir()
    bundle, man = write_bundle(real, inputs(), fixture=False)
    add_population(bundle, man)
    finalize_entries(str(bundle))
    env = bd.build_envelope(str(package), str(bundle), envelope_version=1, created_at="2026-10-31T00:00:00Z",
                            acceptor="research lead", accepted_at="2026-10-31")
    sha = bd.write_envelope(env, str(real / "env.json"))
    smoke_root = tmp_path / "smoke-src"
    smoke_root.mkdir()
    fx.build_bundle(smoke_root)
    return {"envelope": str(real / "env.json"), "package": str(package), "handoff": str(bundle),
            "smoke_fixture_root": str(smoke_root), "config": str(CONFIG), "envelope_sha256": sha}


def test_stage_verifies_and_records_every_artifact_and_the_installed_tree_reverifies(tmp_path, sources):
    out = tmp_path / "ctx" / "ipcch"
    body = install.stage(out=out, **sources)
    recorded = json.loads((out / install.INSTALL_MANIFEST).read_text())
    assert recorded == body and body["envelope"]["sha256"] == sources["envelope_sha256"]
    listed = json.loads((Path(sources["handoff"]) / bd.HANDOFF_MANIFEST).read_text())["files"]
    assert body["handoff"]["members"] == len(listed) and set(body["handoff"]["member_sha256"]) == set(listed)
    assert body["smoke_fixture"]["manifest_sha256"] != body["handoff"]["manifest_sha256"]
    assert body["config"]["sha256"] == bd.sha256_file(str(CONFIG))
    assert install.verify_against(out, recorded, envelope_sha256=sources["envelope_sha256"]) == body
    assert install.main(["verify", "--root", str(out), "--envelope-sha256", sources["envelope_sha256"],
                         "--against", str(out / install.INSTALL_MANIFEST)]) == 0


def _staged(tmp_path, sources, name="ctx"):
    out = tmp_path / name / "ipcch"
    install.stage(out=out, **sources)
    return out, json.loads((out / install.INSTALL_MANIFEST).read_text())


def test_any_altered_missing_or_extra_installed_member_is_refused(tmp_path, sources):
    out, recorded = _staged(tmp_path, sources)
    member = next(iter(sorted(recorded["handoff"]["member_sha256"])))
    with open(out / "handoff-bundle" / member, "ab") as f:
        f.write(b"x")
    with pytest.raises(install.InstallError, match=f"member {member} differs"):
        install.verify_against(out, recorded, envelope_sha256=sources["envelope_sha256"])
    out2, rec2 = _staged(tmp_path, sources, "ctx2")
    (out2 / "handoff-bundle" / "extra.csv").write_text("x")
    with pytest.raises(install.InstallError, match="unlisted files"):
        install.verify_against(out2, rec2, envelope_sha256=sources["envelope_sha256"])
    out3, rec3 = _staged(tmp_path, sources, "ctx3")
    pkg_file = next(p for p in (out3 / "package").rglob("*") if p.is_file() and p.name != bd.PACKAGE_MANIFEST)
    pkg_file.write_bytes(pkg_file.read_bytes() + b"x")
    with pytest.raises(install.InstallError, match="differs from"):
        install.verify_against(out3, rec3, envelope_sha256=sources["envelope_sha256"])
    out4, rec4 = _staged(tmp_path, sources, "ctx4")
    smoke_member = next(iter(sorted(rec4["smoke_fixture"]["member_sha256"])))
    with open(out4 / "smoke-fixture" / "bundle" / smoke_member, "ab") as f:
        f.write(b"x")
    with pytest.raises(install.InstallError, match="differs from its manifest"):
        install.verify_against(out4, rec4, envelope_sha256=sources["envelope_sha256"])


def test_wrong_envelope_pin_is_refused_before_anything_is_copied(tmp_path, sources):
    out = tmp_path / "ctx" / "ipcch"
    with pytest.raises(install.InstallError, match="not the pinned sha256"):
        install.stage(out=out, **{**sources, "envelope_sha256": "0" * 64})
    assert not out.exists()


def test_the_real_handoff_can_never_be_installed_as_the_smoke_fixture(tmp_path, sources):
    fake_root = tmp_path / "smoke-real"
    shutil.copytree(sources["handoff"], fake_root / "bundle")
    with pytest.raises(install.InstallError, match="fixture: true"):
        install.stage(out=tmp_path / "ctx" / "ipcch", **{**sources, "smoke_fixture_root": str(fake_root)})


@pytest.mark.parametrize("change, match", [
    (lambda c: c.update(fewsnet={"image_uri": "r/i@sha256:" + "a" * 64}), "image digest"),
    (lambda c: c["installed"]["real"].update(bundle_dir="/opt/other"), "install layout"),
    (lambda c: c.update(run_timeout_seconds=86400), "deployment config invalid"),
])
def test_installed_config_must_match_the_layout_and_carry_no_digest(tmp_path, sources, change, match):
    cfg = json.loads(CONFIG.read_text())
    change(cfg)
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps(cfg))
    with pytest.raises(install.InstallError, match=match):
        install.stage(out=tmp_path / "ctx" / "ipcch", **{**sources, "config": str(path)})


def test_build_context_requires_every_install_input():
    out = subprocess.run(["bash", str(RUNTIME / "deploy" / "build_context.sh"), "--envelope", "x"], capture_output=True,
                         text=True)
    assert out.returncode == 2 and "missing --envelope-sha256" in out.stderr
    dockerfile = (RUNTIME / "deploy" / "Dockerfile").read_text()
    assert "COPY ipcch /opt/ipcch" in dockerfile and "cloud.ipcch.install verify" in dockerfile
    assert "--against /opt/ipcch/INSTALL.json" in dockerfile and "ARG IPCCH_ENVELOPE_SHA256" in dockerfile


# --------------------------------------------------------------------------- the runtime smoke route


def test_the_runtime_smoke_provider_runs_the_whole_smoke_route(tmp_path, package):   # noqa: F811
    from tests.cloud.test_ipcch_entrypoint_v2 import ROOTS, Reader, config, put_request
    from tests.cloud.test_ipcch_run_v2 import raw, smoke_world
    store, refs, _, _ = smoke_world(tmp_path, package)
    cfg = config(tmp_path, package, providers={"smoke": "cloud.ipcch.smoke_providers:entrypoint_providers",
                                               "real": "cloud.ipcch.entrypoint_v2:real_providers"})
    req = raw(fx.smoke_request(refs, tmp_path / "env.json", inference=True))
    req["publication"] = "current"
    out = ep.run(cfg, request_uri=put_request(refs, req), request_generation="1", store=store,
                 reader=Reader(refs, store))
    assert out["status"] == "succeeded" and out["systems"]["ipcch"]["result"]["publication"]["status"] == "published"
    assert pub.read_current(store, ROOTS["smoke"], "smoke")["record"]["systems"]["ipcch"]["mode"] == "smoke"
