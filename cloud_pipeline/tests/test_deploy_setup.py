import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("setup", Path(__file__).resolve().parents[1] / "deploy/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_destination_setup_contains_prepare_and_full_workflow_settings():
    cfg = dict(project="dest", region="us-central1", bucket="out", request_bucket="request", image_uri="registry/image@sha256:" + "a" * 64, service_account="runtime@dest", workflow_service_account="workflow@dest", namespace="staging", prepare_job="monthly-prepare")
    commands = list(setup.commands(cfg))
    assert len(commands) == 5
    assert commands[0][4] == "monthly-prepare"
    assert commands[0][commands[0].index("--command") + 1] == "python3"
    assert "--max-retries" in commands[0]
    assert "DELIVERY_IMAGE_URI=" + cfg["image_uri"] in commands[3][-1]
    assert commands[4][-3] == "bucket=request"
