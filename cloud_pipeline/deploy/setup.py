"""Preview destination provisioning; --execute applies the printed commands."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess


def commands(cfg):
    required = (
        "project",
        "region",
        "bucket",
        "request_bucket",
        "image_uri",
        "service_account",
        "workflow_service_account",
        "namespace",
        "prepare_job",
    )
    if any(not cfg.get(k) or "REPLACE" in str(cfg[k]) for k in required):
        raise ValueError("fill deployment config including workflow_service_account")
    import re

    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", cfg["image_uri"]):
        raise ValueError("image_uri must be digest pinned")
    p, region, image, sa = (
        cfg[k] for k in ("project", "region", "image_uri", "service_account")
    )
    workflow_sa = cfg["workflow_service_account"]
    run = ["--project", p, "--region", region]
    common = [
        "--image",
        image,
        "--service-account",
        sa,
        "--max-retries",
        "0",
        "--tasks",
        "1",
        "--command",
        "python3",
    ]
    yield [
        "gcloud",
        "run",
        "jobs",
        "deploy",
        cfg["prepare_job"],
        *run,
        *common,
        "--memory",
        "8Gi",
        "--cpu",
        "2",
        "--task-timeout",
        "4h",
        "--args=-m,cloud.orchestrator.prepare,--help",
    ]
    yield [
        "gcloud",
        "run",
        "jobs",
        "deploy",
        "oct-delivery",
        *run,
        *common,
        "--memory",
        "32Gi",
        "--cpu",
        "8",
        "--task-timeout",
        "4h",
        "--args=-m,cloud.orchestrator.delivery_job,run,--output-root,gs://"
        + cfg["bucket"]
        + ",--release-namespace,"
        + cfg["namespace"]
        + ",--image-uri,"
        + image,
    ]
    yield [
        "gcloud",
        "run",
        "jobs",
        "add-iam-policy-binding",
        "oct-delivery",
        *run,
        "--member",
        "serviceAccount:" + workflow_sa,
        "--role",
        "roles/run.developer",
    ]
    environment = {
        "DELIVERY_LOCATION": region,
        "DELIVERY_JOB": "oct-delivery",
        "DELIVERY_OUTPUT_ROOT": "gs://" + cfg["bucket"],
        "DELIVERY_RELEASE_NAMESPACE": cfg["namespace"],
        "DELIVERY_IMAGE_URI": image,
    }
    yield [
        "gcloud",
        "workflows",
        "deploy",
        "oct-delivery-trigger",
        "--project",
        p,
        "--location",
        region,
        "--source",
        str(Path(__file__).with_name("workflow.yaml")),
        "--service-account",
        workflow_sa,
        "--set-env-vars",
        ",".join(k + "=" + v for k, v in environment.items()),
    ]
    yield [
        "gcloud",
        "eventarc",
        "triggers",
        "create",
        "oct-delivery-requests",
        "--project",
        p,
        "--location",
        region,
        "--destination-workflow",
        "oct-delivery-trigger",
        "--destination-workflow-location",
        region,
        "--event-filters",
        "type=google.cloud.storage.object.v1.finalized",
        "--event-filters",
        "bucket=" + cfg["request_bucket"],
        "--service-account",
        workflow_sa,
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    planned = list(commands(json.loads(args.config.read_text(encoding="utf-8"))))
    for command in planned:
        print(shlex.join(command), flush=True)
        if args.execute:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
