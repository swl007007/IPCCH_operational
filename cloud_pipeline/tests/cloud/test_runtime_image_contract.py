import importlib
import subprocess
import sys
from pathlib import Path


def test_dockerfile_documents_single_image_entrypoints_and_digest_metadata():
    dockerfile = Path("deploy/Dockerfile").read_text(encoding="utf-8")

    assert "cloud.orchestrator.prepare" in dockerfile
    assert "prepare_extract" in dockerfile
    assert "model_pipeline" in dockerfile
    assert "ipcch.entrypoint.prepare_plan" in dockerfile
    assert "requirements.lock.txt" in dockerfile


def test_cloud_runtime_dependencies_include_launch_model_loader_requirements():
    requirements = Path("requirements.lock.txt").read_text(encoding="utf-8")

    assert "xgboost" in requirements


def test_required_cloud_entrypoint_modules_import():
    for module_name in (
        "cloud.orchestrator.prepare",
        "cloud.batch.evi_worker",
        "cloud.orchestrator.delivery_job",
    ):
        assert importlib.import_module(module_name)


def test_documented_module_entrypoints_expose_cli_help():
    for module_name in (
        "cloud.orchestrator.prepare",
        "cloud.batch.evi_worker",
        "cloud.orchestrator.delivery_job",
    ):
        result = subprocess.run(
            [sys.executable, "-m", module_name, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "usage:" in result.stdout
