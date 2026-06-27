import importlib
import subprocess
import sys
from pathlib import Path


def test_dockerfile_documents_single_image_entrypoints_and_digest_metadata():
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")

    assert "cloud.orchestrator.main" in dockerfile
    assert "cloud.batch.evi_worker" in dockerfile
    assert "cloud.orchestrator.inference" in dockerfile
    assert "ipcch.entrypoint.orchestrator" in dockerfile
    assert "requirements-cloud.txt" in dockerfile


def test_cloud_runtime_dependencies_include_launch_model_loader_requirements():
    requirements = Path("requirements-cloud.txt").read_text(encoding="utf-8")

    assert "xgboost" in requirements


def test_required_cloud_entrypoint_modules_import():
    for module_name in (
        "cloud.orchestrator.main",
        "cloud.batch.evi_worker",
        "cloud.orchestrator.inference",
    ):
        assert importlib.import_module(module_name)


def test_documented_module_entrypoints_expose_cli_help():
    for module_name in (
        "cloud.orchestrator.main",
        "cloud.batch.evi_worker",
        "cloud.orchestrator.inference",
    ):
        result = subprocess.run(
            [sys.executable, "-m", module_name, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "usage:" in result.stdout
