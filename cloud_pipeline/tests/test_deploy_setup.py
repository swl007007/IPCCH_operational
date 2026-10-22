import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("setup", Path(__file__).resolve().parents[1] / "deploy/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


CFG = dict(project="dest", region="us-central1", bucket="out", request_bucket="request", image_uri="registry/image@sha256:" + "a" * 64, service_account="runtime@dest", workflow_service_account="workflow@dest", namespace="staging", prepare_job="monthly-prepare", earth_engine_project="ee-project")


def test_destination_setup_contains_prepare_and_full_workflow_settings():
    cfg = CFG
    commands = list(setup.commands(cfg))
    assert len(commands) == 9
    assert commands[0][4] == "monthly-prepare"
    assert commands[0][commands[0].index("--command") + 1] == "python3"
    assert "--max-retries" in commands[0]
    workflow = next(c for c in commands if c[:3] == ["gcloud", "workflows", "deploy"])
    env = dict(item.split("=", 1) for item in workflow[-1].split(","))
    assert env["DELIVERY_IMAGE_URI"] == cfg["image_uri"] and env["PREPARE_JOB"] == "monthly-prepare"
    assert env["EARTH_ENGINE_PROJECT"] == "ee-project" and env["BATCH_PARENT"] == "projects/dest/locations/us-central1"
    assert env["BATCH_SERVICE_ACCOUNT"] == "runtime@dest"
    assert (env["PREPARE_POLL_SECONDS"], env["PREPARE_MAX_POLLS"]) == ("300", "96")
    assert commands[-1][-3] == "bucket=request"


def test_workflow_grants_are_scoped_to_its_jobs_reads_and_dispatch_claims():
    commands = list(setup.commands(CFG))
    grants = [c for c in commands if "add-iam-policy-binding" in c]
    assert all("serviceAccount:workflow@dest" in c for c in grants)
    assert {c[4] for c in grants if c[1] == "run"} == {"oct-delivery", "monthly-prepare"}
    assert {(c[4], c[c.index("--role") + 1]) for c in grants if c[1] == "storage"} == {
        ("gs://request", "roles/storage.objectViewer"), ("gs://out", "roles/storage.objectViewer"),
        ("gs://out", "roles/storage.objectCreator")}
    creator = next(c for c in grants if "roles/storage.objectCreator" in c)
    assert creator[-1] == ('--condition=expression=resource.name.startsWith("projects/_/buckets/out/objects/dispatch/"),'
                           "title=workflow-dispatch-claims")
