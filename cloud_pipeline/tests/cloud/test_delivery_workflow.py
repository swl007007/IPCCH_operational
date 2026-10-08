"""The Workflows override argv must be a complete, parseable delivery_job command (definition check only)."""
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from cloud.orchestrator import delivery_job  # noqa: E402

WORKFLOW = Path(__file__).resolve().parents[2] / "deploy/workflow.yaml"


def _render(value, env, event):
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        expression = value[2:-1]
        if expression.startswith('sys.get_env("'):
            return env[expression.split('"')[1]]
        return {"generation": event["generation"], "output_root": env["DELIVERY_OUTPUT_ROOT"],
                "release_namespace": env["DELIVERY_RELEASE_NAMESPACE"], "image_uri": env["DELIVERY_IMAGE_URI"],
                '"gs://" + bucket + "/" + name': f"gs://{event['bucket']}/{event['name']}"}[expression]
    return value


def test_override_argv_keeps_every_configured_flag_and_parses():
    steps = yaml.safe_load(WORKFLOW.read_text())["main"]["steps"]
    run = next(step["run_job"] for step in steps if "run_job" in step)
    args = run["args"]["body"]["overrides"]["containerOverrides"][0]["args"]
    env = {"DELIVERY_OUTPUT_ROOT": "gs://b", "DELIVERY_RELEASE_NAMESPACE": "dual-system",
           "DELIVERY_IMAGE_URI": "r/i@sha256:" + "c" * 64}
    argv = [_render(a, env, {"bucket": "b", "name": "requests/r1/run_manifest.json", "generation": "17"}) for a in args]

    assert argv[:3] == ["-m", "cloud.orchestrator.delivery_job", "run"]
    with pytest.raises(SystemExit) as missing:  # sanity: the CLI really requires the configured flags
        delivery_job.main(["run", "--request-uri", "gs://b/requests/r1/run_manifest.json", "--request-generation", "17"])
    assert missing.value.code == 2
    flags = dict(zip(argv[3::2], argv[4::2]))
    assert flags == {"--request-uri": "gs://b/requests/r1/run_manifest.json", "--request-generation": "17",
                     "--output-root": "gs://b", "--release-namespace": "dual-system", "--image-uri": env["DELIVERY_IMAGE_URI"]}
    assert run["args"]["connector_params"] == {"skip_polling": True}  # submission is not success
