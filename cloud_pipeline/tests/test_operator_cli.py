import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import pipeline as p
from cloud.batch.remote_sources import SYSTEM_FAMILIES
from cloud.orchestrator.delivery_job import (
    PACKAGE_MANIFEST_SCHEMA,
    ACCEPTANCE_REPORT_SCHEMA,
)
from cloud.orchestrator.delivery_manifest import validate_delivery_request
from tests.cloud.test_delivery_manifest import _request


def digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class Fake:
    def __init__(self):
        self.objects = {}
        self.launches = 0
        self.fail_launch = False
        self.fail_request = False

    def put(self, uri, path):
        raw = Path(path).read_bytes()
        if uri in self.objects:
            assert self.objects[uri] == raw
        self.objects[uri] = raw
        if self.fail_request and uri.endswith("/run_manifest.json"):
            self.fail_request = False
            raise OSError("interrupted after upload")
        return dict(uri=uri, generation="1", sha256=hashlib.sha256(raw).hexdigest())

    def latest(self, uri):
        if uri not in self.objects:
            return None
        raw = self.objects[uri]
        return json.loads(raw), dict(
            uri=uri, generation="1", sha256=hashlib.sha256(raw).hexdigest()
        )

    def launch(self, ref, deadline):
        self.launches += 1
        if self.fail_launch:
            raise OSError("ambiguous submission")
        return {"name": "execution-1"}

    def fetch(self, ref, destination):
        raw = self.objects[ref["uri"]]
        assert hashlib.sha256(raw).hexdigest() == ref["sha256"]
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(raw)

    def blob(self, uri):
        return NS(generation="1", reload=lambda: None)

    def json(self, uri, body):
        self.objects[uri] = json.dumps(body).encode()
        return self.latest(uri)[1]


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "baseline"
    root.mkdir()
    request = _request()
    cfg = dict(
        project="destination",
        bucket="destination-bucket",
        request_bucket="requests-bucket",
        image_uri=request["runtime"]["image_uri"],
        namespace="dual-system",
        work_dir=str(tmp_path / "work"),
        region="us-central1",
        service_account="test@example.com",
        prepare_job="prep",
        earth_engine_project="destination",
        operator="test@example.com",
    )
    environment = dict(
        image_uri=cfg["image_uri"],
        requirements_lock_sha256=p.sha(p.ROOT / "requirements.lock.txt"),
    )
    baseline = dict(
        schema_version="operator-baseline/v1",
        runtime=environment,
        models=[],
        delivery={
            k: request[k]
            for k in (
                "schema_version",
                "systems",
                "horizons_months",
                "contracts",
                "diagnostics",
            )
        },
        sources={f: request[f]["converter_contract"] for f in ("acled", "wfp")},
    )
    baseline["delivery"]["diagnostics"][0]["evidence"] = {
        "local_path": "evidence/diagnostic.csv"
    }
    names = [
        "evidence/diagnostic.csv",
        "assets/retained_acled.csv",
        "assets/retained_wfp.csv",
    ]
    for system in p.SYSTEMS:
        names += [
            f"assets/{system}/{name}"
            for name in (
                "geometry.geojson",
                "roster.csv",
                "population.csv",
                "history_panel.csv",
            )
        ]
        names += [f"assets/{system}/history/{f}.csv" for f in SYSTEM_FAMILIES[system]]
    names += ["assets/ipcch/fixed_features.csv"]
    for name in names:
        target = p.safe(root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture")
    for selected in request["models"]:
        system, h = selected["system"], selected["horizon_months"]
        model = {
            k: selected[k]
            for k in ("system", "horizon_months", "package_id", "feature_schema_sha256")
        }
        if system == "fewsnet":
            from fewsnet_partitioned_rf_pipeline.local.package import (
                LOCAL_PACKAGE_FILES,
            )

            members = LOCAL_PACKAGE_FILES
        else:
            members = [
                "model_package_manifest.json",
                "training_export_summary.json",
            ] + [
                f"scope_{h}m/{n}"
                for n in (
                    "feature_columns.json",
                    "feature_contract.csv",
                    "model_metadata.json",
                    "phase2_worse_model.json",
                    "phase3_worse_model.json",
                    "phase4_worse_model.json",
                    "phase5_worse_model.json",
                )
            ]
        directory = p.model_directory(root, model)
        files = []
        for name in members:
            target = p.safe(directory, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps({"feature_schema_sha256": "b" * 64})
                if name == "training_report.json"
                else "fixture"
            )
            files.append(dict(path=name, sha256=p.sha(target)))
        if system == "ipcch":
            model["feature_schema_sha256"] = p.sha(
                directory / f"scope_{h}m/feature_contract.csv"
            )
        model["manifest"] = dict(
            schema_version=PACKAGE_MANIFEST_SCHEMA,
            system=system,
            horizon_months=h,
            package_id=model["package_id"],
            files=files,
        )
        model["environment"] = environment
        model["acceptance"] = dict(
            schema_version=ACCEPTANCE_REPORT_SCHEMA,
            status="accepted",
            system=system,
            horizon_months=h,
            package_id=model["package_id"],
            feature_schema_sha256=model["feature_schema_sha256"],
            package_manifest_sha256=digest(model["manifest"]),
            runtime=dict(
                image_uri=cfg["image_uri"],
                environment_manifest_sha256=digest(environment),
            ),
            evidence={"receipt": "fixture"},
        )
        baseline["models"].append(model)
    baseline["files"] = {
        f.relative_to(root).as_posix(): dict(
            sha256=p.sha(f), size_bytes=f.stat().st_size
        )
        for f in root.rglob("*")
        if f.is_file()
    }
    p.save(root / "baseline.json", baseline)
    args = NS(baseline=str(root), execute=True)
    return cfg, root, baseline, args, Fake()


def run_args(**kwargs):
    return NS(
        **(
            dict(
                execute=True,
                month="2026-10",
                cutoff="2026-10-08T00:00:00Z",
                deadline="2099-10-08T00:00:00Z",
                run_id="operator-test",
                wait_seconds=0,
                acled="keep",
                wfp="keep",
                acled_raw=None,
                wfp_raw=None,
            )
            | kwargs
        )
    )


def test_init_run_resume_download(setup):
    cfg, root, baseline, args, cloud = setup
    (root / "credentials.json").write_text("must not upload")
    p.initialize(args, cfg, cloud)
    assert not any("credentials" in key for key in cloud.objects)
    assert p.initialize(args, cfg, cloud)["status"] == "initialized"
    assert p.run(run_args(), cfg, cloud)["status"] == "preparing"
    base = "gs://destination-bucket"
    cloud.json(
        base + "/prepared/operator-test/prepare_status.json", dict(status="succeeded")
    )
    cloud.json(
        base + "/prepared/operator-test/prepared_manifest.json",
        dict(status="succeeded", origin_month="2026-10", prepare_id="operator-test"),
    )
    cloud.fail_request = True
    with pytest.raises(OSError):
        p.run(run_args(), cfg, cloud)
    result = p.run(run_args(), cfg, cloud)
    assert result["status"] == "submitted" and cloud.launches == 1
    uri = "gs://requests-bucket/requests/operator-test/run_manifest.json"
    validate_delivery_request(
        cloud.latest(uri)[0], request_uri=uri, request_generation="1"
    )
    raw = b"result"
    cloud.objects[base + "/deliveries/operator-test/results.csv"] = raw
    manifest = cloud.json(
        base + "/deliveries/operator-test/manifest.json",
        dict(
            files=[
                dict(
                    path="results.csv",
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size_bytes=len(raw),
                )
            ]
        ),
    )
    cloud.objects[base + "/deliveries/operator-test/webapp_model_bundle.tar.gz"] = (
        b"archive"
    )
    archive = dict(
        uri=base + "/deliveries/operator-test/webapp_model_bundle.tar.gz",
        generation="1",
        sha256=hashlib.sha256(b"archive").hexdigest(),
    )
    release = base + "/dual-system/releases/operator-test/release.json"
    cloud.json(
        release,
        dict(
            run_id="operator-test",
            validation="passed",
            manifest=manifest,
            archive=archive,
        ),
    )
    cloud.json(
        base + "/runs/operator-test/run_status.json",
        dict(status="succeeded", release=dict(release_record=release)),
    )
    out = root.parent / "download"
    assert (
        p.download(NS(run_id="operator-test", output=out), cfg, cloud)["status"]
        == "verified"
    )
    assert (out / "results.csv").read_bytes() == raw


def test_ambiguous_launch_never_repeats(setup):
    cfg, root, b, args, cloud = setup
    p.initialize(args, cfg, cloud)
    cloud.fail_launch = True
    with pytest.raises(OSError):
        p.run(run_args(), cfg, cloud)
    assert p.run(run_args(), cfg, cloud)["status"] == "preparation_submission_pending"
    assert cloud.launches == 1
    with pytest.raises(ValueError, match="different inputs"):
        p.run(run_args(cutoff="2026-10-09T00:00:00Z"), cfg, cloud)
    with pytest.raises(ValueError, match="deadline"):
        p.run(run_args(deadline="2000-01-01T00:00:00Z"), cfg, cloud)
    with pytest.raises(ValueError, match="run ID"):
        p.run(run_args(run_id="../bad"), cfg, cloud)
    with pytest.raises(ValueError, match="destination"):
        p.run(run_args(), cfg | {"project": "changed"}, cloud)


@pytest.mark.parametrize(
    "mutation", ["bytes", "manifest", "missing", "duplicate", "environment"]
)
def test_rejects_unbound_baseline(setup, mutation):
    cfg, root, b, args, cloud = setup
    m = b["models"][0]
    if mutation == "bytes":
        (root / "assets/retained_acled.csv").write_text("changed")
    elif mutation == "manifest":
        m["acceptance"]["package_manifest_sha256"] = "0" * 64
    elif mutation == "environment":
        m["environment"] = dict(m["environment"], requirements_lock_sha256="0" * 64)
    else:
        if mutation == "missing":
            m["manifest"]["files"].pop()
        else:
            m["manifest"]["files"].append(m["manifest"]["files"][0])
        m["acceptance"]["package_manifest_sha256"] = digest(m["manifest"])
    p.save(root / "baseline.json", b)
    with pytest.raises(ValueError):
        p.initialize(args, cfg, cloud)
    assert not cloud.objects


def test_preview_no_cloud_and_select_rollback(setup, monkeypatch):
    cfg, root, b, args, cloud = setup
    monkeypatch.setattr(p, "Cloud", lambda cfg: pytest.fail("preview opened cloud"))
    assert p.initialize(NS(baseline=root, execute=False), cfg)["mode"] == "preview"
    p.initialize(args, cfg, cloud)
    original = copy.deepcopy(p.load_initialized(cfg)["delivery"]["diagnostics"])
    model = copy.deepcopy(b["models"][0])
    model["package_id"] = "nested/version-2"
    model["manifest"]["package_id"] = model["package_id"]
    model["acceptance"]["package_id"] = model["package_id"]
    model["acceptance"]["package_manifest_sha256"] = digest(model["manifest"])
    package = p.model_directory(root, model)
    p.save(package / "operator-model.json", model)
    import fewsnet_partitioned_rf_pipeline.local.package as loader

    monkeypatch.setattr(loader, "load_local_model_package", lambda directory: None)
    reg = NS(
        model_command="register",
        system="fewsnet",
        horizon=0,
        package=package,
        execute=True,
    )
    assert p.models(reg, cfg, cloud)["selected"] is False
    sel = NS(
        model_command="select",
        system="fewsnet",
        horizon=0,
        version=model["package_id"],
        execute=True,
    )
    p.models(sel, cfg, cloud)
    assert all(
        e["status"] == "unavailable"
        for e in p.load_initialized(cfg)["delivery"]["diagnostics"]
        if e["system"] == "fewsnet" and e["horizon_months"] == 0
    )
    sel.version = b["models"][0]["package_id"]
    p.models(sel, cfg, cloud)
    assert sorted(
        p.load_initialized(cfg)["delivery"]["diagnostics"], key=str
    ) == sorted(original, key=str)


def test_launch_overrides_entire_argv(monkeypatch):
    calls = []
    monkeypatch.setattr(
        p.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or NS(stdout="{}"),
    )
    client = object.__new__(p.Cloud)
    client.cfg = dict(
        project="p",
        region="r",
        bucket="b",
        earth_engine_project="e",
        image_uri="i",
        service_account="s",
        prepare_job="job",
    )
    client.launch(dict(uri="gs://bucket/r", generation="1"), "2099-01-01T00:00:00Z")
    assert calls[0][-1].startswith("--args=-m,cloud.orchestrator.prepare,plan,")


def test_model_diagnostics_and_shared_members_rejected_before_mutation(
    setup, monkeypatch
):
    cfg, root, b, args, cloud = setup
    p.initialize(args, cfg, cloud)
    import fewsnet_partitioned_rf_pipeline.local.package as loader

    monkeypatch.setattr(loader, "load_local_model_package", lambda directory: None)
    model = copy.deepcopy(b["models"][0])
    model["diagnostics"] = []
    package = p.model_directory(root, model)
    p.save(package / "operator-model.json", model)
    before = dict(cloud.objects)
    for execute in (False, True):
        with pytest.raises(ValueError, match="diagnostics"):
            p.models(
                NS(
                    model_command="register",
                    system="fewsnet",
                    horizon=0,
                    package=package,
                    execute=execute,
                ),
                cfg,
                cloud,
            )
    assert cloud.objects == before
    bad = copy.deepcopy(b["models"])
    ipcch = [m for m in bad if m["system"] == "ipcch"]
    ipcch[0]["manifest"]["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="shared member"):
        p.shared_members(bad)


def test_init_missing_assets_stops_before_upload(setup):
    cfg, root, b, args, cloud = setup
    del b["files"]["assets/retained_acled.csv"]
    p.save(root / "baseline.json", b)
    with pytest.raises(ValueError, match="required operational assets"):
        p.initialize(args, cfg, cloud)
    assert not cloud.objects


def test_deadline_expires_during_preparation_without_submission(setup, monkeypatch):
    from datetime import datetime, timezone

    cfg, root, baseline, args, cloud = setup
    p.initialize(args, cfg, cloud)
    clock = NS(value=datetime(2026, 10, 8, tzinfo=timezone.utc))
    monkeypatch.setattr(
        p,
        "datetime",
        NS(fromisoformat=datetime.fromisoformat, now=lambda tz: clock.value),
    )
    original_launch = cloud.launch

    def launch(ref, deadline):
        result = original_launch(ref, deadline)
        clock.value = datetime(2100, 1, 1, tzinfo=timezone.utc)
        return result

    monkeypatch.setattr(cloud, "launch", launch)
    with pytest.raises(ValueError, match="deadline"):
        p.run(run_args(), cfg, cloud)
    assert cloud.launches == 1
    assert not any(uri.endswith("/run_manifest.json") for uri in cloud.objects)
