"""Destination operator CLI. Mutations preview unless --execute is supplied."""

from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SYSTEMS = ("fewsnet", "ipcch")
HORIZONS = (0, 6, 12)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def safe(root, relative):
    part = Path(relative)
    if (
        part.is_absolute()
        or ".." in part.parts
        or "\\" in str(relative)
        or ":" in str(relative)
    ):
        raise ValueError(f"unsafe relative path: {relative}")
    path = (Path(root) / part).resolve()
    if Path(root).resolve() not in path.parents:
        raise ValueError(f"path escapes root: {relative}")
    return path


def config(path):
    cfg = read(path)
    required = (
        "project",
        "region",
        "bucket",
        "request_bucket",
        "service_account",
        "image_uri",
        "namespace",
        "prepare_job",
        "earth_engine_project",
        "operator",
        "work_dir",
    )
    if any(not cfg.get(k) or "REPLACE" in str(cfg[k]) for k in required):
        raise ValueError("fill every destination field in project.example.json")
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", cfg["image_uri"]):
        raise ValueError("image_uri must be digest pinned")
    for key in ("bucket", "request_bucket"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", cfg[key]):
            raise ValueError(f"invalid {key}")
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", cfg["namespace"])
        or cfg["namespace"] == "released"
    ):
        raise ValueError("invalid or reserved namespace")
    work = Path(cfg["work_dir"]).expanduser()
    cfg["work_dir"] = str((Path(path).resolve().parent / work).resolve())
    return cfg


class Cloud:
    def __init__(self, cfg):
        from google.cloud import storage

        self.client = storage.Client(project=cfg["project"])
        self.cfg = cfg

    def blob(self, uri, generation=None):
        bucket, name = uri.removeprefix("gs://").split("/", 1)
        return self.client.bucket(bucket).blob(
            name, generation=int(generation) if generation else None
        )

    def latest(self, uri):
        blob = self.blob(uri)
        try:
            blob.reload()
        except Exception as exc:
            if exc.__class__.__name__ == "NotFound":
                return None
            raise
        raw = self.blob(uri, blob.generation).download_as_bytes()
        return json.loads(raw), {
            "uri": uri,
            "generation": str(blob.generation),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def put(self, uri, path):
        blob = self.blob(uri)
        try:
            blob.upload_from_filename(str(path), if_generation_match=0)
        except Exception as exc:
            if exc.__class__.__name__ != "PreconditionFailed":
                raise
            blob.reload()
            from cloud.orchestrator.delivery_job import PinnedDownloader

            actual = PinnedDownloader(
                self.client, Path(self.cfg["work_dir"]) / "verify"
            ).resolve(uri, str(blob.generation))
            if actual != sha(path):
                raise ValueError(f"existing immutable object differs: {uri}") from exc
        if not blob.generation or int(blob.generation) <= 0:
            raise ValueError("upload returned no generation")
        return {"uri": uri, "generation": str(blob.generation), "sha256": sha(path)}

    def fetch(self, ref, destination):
        from cloud.orchestrator.delivery_job import PinnedDownloader

        source = PinnedDownloader(
            self.client, Path(self.cfg["work_dir"]) / "downloads"
        ).fetch(ref)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def launch(self, ref, deadline):
        cfg = self.cfg
        argv = [
            "-m",
            "cloud.orchestrator.prepare",
            "plan",
            "--request-uri",
            ref["uri"],
            "--request-generation",
            ref["generation"],
            "--output-root",
            f"gs://{cfg['bucket']}",
            "--earth-engine-project",
            cfg["earth_engine_project"],
            "--batch-parent",
            f"projects/{cfg['project']}/locations/{cfg['region']}",
            "--batch-image-uri",
            cfg["image_uri"],
            "--batch-service-account",
            cfg["service_account"],
            "--deadline-utc",
            deadline,
        ]
        completed = subprocess.run(
            [
                "gcloud",
                "run",
                "jobs",
                "execute",
                cfg["prepare_job"],
                "--project",
                cfg["project"],
                "--region",
                cfg["region"],
                "--async",
                "--format=json",
                "--args=" + ",".join(argv),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)


def put_json(cloud, uri, body, work):
    path = Path(work) / ("object-" + hashlib.sha256(uri.encode()).hexdigest() + ".json")
    save(path, body)
    return cloud.put(uri, path)


def model_directory(root, model):
    return Path(root) / (
        "models/fewsnet/" + str(model["horizon_months"]) + "m"
        if model["system"] == "fewsnet"
        else "models/ipcch"
    )


def validate_model(model, directory, runtime, *, load=False):
    from cloud.orchestrator.delivery_job import (
        package_schema_sha256,
        ACCEPTANCE_REPORT_SCHEMA,
        PACKAGE_MANIFEST_SCHEMA,
    )

    system, horizon = model["system"], model["horizon_months"]
    if system not in SYSTEMS or type(horizon) is not int or horizon not in HORIZONS:
        raise ValueError("unsupported model slot")
    manifest, acceptance = model["manifest"], model["acceptance"]
    expected = {
        "system": system,
        "horizon_months": horizon,
        "package_id": model["package_id"],
    }
    if manifest.get("schema_version") != PACKAGE_MANIFEST_SCHEMA or any(
        manifest.get(k) != v for k, v in expected.items()
    ):
        raise ValueError("package manifest identity mismatch")
    if (
        acceptance.get("schema_version") != ACCEPTANCE_REPORT_SCHEMA
        or acceptance.get("status") != "accepted"
        or any(acceptance.get(k) != v for k, v in expected.items())
    ):
        raise ValueError("real package-specific accepted report required")
    if not acceptance.get("evidence"):
        raise ValueError("acceptance requires package-specific evidence")
    if (
        acceptance["runtime"]["image_uri"].split("@")[-1]
        != runtime["image_uri"].split("@")[-1]
    ):
        raise ValueError("runtime digest differs from accepted evidence")
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()
    ).hexdigest()
    if (
        model.get("manifest_sha256", manifest_hash) != manifest_hash
        or acceptance.get("package_manifest_sha256") != manifest_hash
    ):
        raise ValueError("acceptance package manifest identity mismatch")
    environment = model["environment"]
    environment_hash = hashlib.sha256(
        json.dumps(environment, sort_keys=True).encode()
    ).hexdigest()
    if acceptance["runtime"]["environment_manifest_sha256"] != environment_hash:
        raise ValueError("acceptance environment identity mismatch")
    if environment["image_uri"] != acceptance["runtime"]["image_uri"] or environment[
        "requirements_lock_sha256"
    ] != sha(ROOT / "requirements.lock.txt"):
        raise ValueError("accepted environment does not match runtime lock/image")
    safe(directory, model["package_id"])
    if system == "fewsnet":
        from fewsnet_partitioned_rf_pipeline.local.package import LOCAL_PACKAGE_FILES

        required = set(LOCAL_PACKAGE_FILES)
    else:
        required = {"model_package_manifest.json", "training_export_summary.json"} | {
            f"scope_{horizon}m/{name}"
            for name in (
                "feature_columns.json",
                "feature_contract.csv",
                "model_metadata.json",
                "phase2_worse_model.json",
                "phase3_worse_model.json",
                "phase4_worse_model.json",
                "phase5_worse_model.json",
            )
        }
    seen = set()
    for item in manifest["files"]:
        if item["path"] in seen:
            raise ValueError("duplicate package member")
        seen.add(item["path"])
        if sha(safe(directory, item["path"])) != item["sha256"]:
            raise ValueError(f"package member identity mismatch: {item['path']}")
    if seen != required:
        raise ValueError(
            f"incomplete package members: missing {sorted(required - seen)}, extra {sorted(seen - required)}"
        )
    if load:
        if system == "fewsnet":
            from fewsnet_partitioned_rf_pipeline.local.package import (
                load_local_model_package,
            )

            load_local_model_package(directory)
        else:
            from model_pipeline.ipcch_launch_runtime.model_package import (
                load_scope_package,
            )

            load_scope_package(directory, horizon)
    actual = package_schema_sha256(system, horizon, directory)
    if (
        actual != model["feature_schema_sha256"]
        or acceptance.get("feature_schema_sha256") != actual
    ):
        raise ValueError("feature schema does not match accepted package")


def shared_members(models):
    members = {}
    for model in models:
        if model["system"] != "ipcch":
            continue
        for item in model["manifest"]["files"]:
            old = members.setdefault(item["path"], item["sha256"])
            if old != item["sha256"]:
                raise ValueError(f"conflicting IPCCH shared member: {item['path']}")


def publish_model(model, directory, cfg, cloud, runtime):
    safe(directory, model["package_id"])
    prefix = f"gs://{cfg['bucket']}/models/{cfg['image_uri'].split(':')[-1]}/{model['system']}/{model['horizon_months']}m/{model['package_id']}"
    manifest = copy.deepcopy(model["manifest"])
    manifest["files"] = [
        {
            "path": item["path"],
            **cloud.put(
                prefix + "/files/" + item["path"], safe(directory, item["path"])
            ),
        }
        for item in manifest["files"]
    ]
    manifest_ref = put_json(cloud, prefix + "/package.json", manifest, cfg["work_dir"])
    report = copy.deepcopy(model["acceptance"])
    report.update(
        package_manifest_sha256=manifest_ref["sha256"],
        runtime={
            "image_uri": runtime["image_uri"],
            "environment_manifest_sha256": runtime["environment_manifest"]["sha256"],
        },
    )
    report["evidence"] = {
        "original_acceptance": model["acceptance"],
        "rebinding": "identical package member hashes and runtime image digest",
    }
    report_ref = put_json(cloud, prefix + "/acceptance.json", report, cfg["work_dir"])
    return {
        **{
            k: model[k]
            for k in ("system", "horizon_months", "package_id", "feature_schema_sha256")
        },
        "package_manifest": manifest_ref,
        "acceptance_report": report_ref,
    }


def initialize(args, cfg, cloud=None):
    root = Path(args.baseline).resolve()
    baseline = read(root / "baseline.json")
    if baseline.get("schema_version") != "operator-baseline/v1":
        raise ValueError("unsupported baseline descriptor")
    runtime = baseline["runtime"]
    if runtime["image_uri"].split("@")[-1] != cfg["image_uri"].split("@")[
        -1
    ] or runtime["requirements_lock_sha256"] != sha(ROOT / "requirements.lock.txt"):
        raise ValueError(
            "baseline acceptance does not cover configured runtime digest/dependency lock"
        )
    models = baseline["models"]
    if {(m["system"], m["horizon_months"]) for m in models} != {
        (s, h) for s in SYSTEMS for h in HORIZONS
    } or len(models) != 6:
        raise ValueError("baseline requires exactly six model slots")
    for model in models:
        validate_model(model, model_directory(root, model), runtime)
    shared_members(models)
    files = []
    for relative, identity in baseline["files"].items():
        if not relative.startswith(("assets/", "models/", "evidence/")):
            raise ValueError(f"baseline file is not allowlisted: {relative}")
        member = safe(root, relative)
        if (
            member.stat().st_size != identity["size_bytes"]
            or sha(member) != identity["sha256"]
        ):
            raise ValueError(f"baseline identity mismatch: {relative}")
        files.append(member)
    for model in models:
        for item in model["manifest"]["files"]:
            relative = (
                safe(model_directory(root, model), item["path"])
                .relative_to(root)
                .as_posix()
            )
            if baseline["files"].get(relative, {}).get("sha256") != item["sha256"]:
                raise ValueError(
                    f"model member missing from baseline inventory: {relative}"
                )
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("baseline symlinks are not supported")
    from cloud.batch.remote_sources import SYSTEM_FAMILIES
    from cloud.orchestrator.delivery_manifest import _diagnostics

    required_assets = {
        "assets/retained_acled.csv",
        "assets/retained_wfp.csv",
        "assets/ipcch/fixed_features.csv",
    }
    for system in SYSTEMS:
        required_assets.update(
            f"assets/{system}/{name}"
            for name in (
                "geometry.geojson",
                "roster.csv",
                "population.csv",
                "history_panel.csv",
            )
        )
        required_assets.update(
            f"assets/{system}/history/{family}.csv"
            for family in SYSTEM_FAMILIES[system]
        )
    diagnostics = copy.deepcopy(baseline["delivery"]["diagnostics"])
    for entry in diagnostics:
        if entry["status"] == "available":
            relative = entry["evidence"]["local_path"]
            required_assets.add(relative)
            entry["evidence"] = {
                "uri": f"gs://{cfg['bucket']}/baseline/{relative}",
                "generation": "1",
                "sha256": baseline["files"][relative]["sha256"],
            }
    if not required_assets.issubset(baseline["files"]):
        raise ValueError("baseline inventory is missing required operational assets")
    _diagnostics(
        diagnostics,
        {(m["system"], m["horizon_months"]): m["package_id"] for m in models},
    )
    if not args.execute:
        return {"mode": "preview", "command": "init", "files": len(files), "models": 6}
    baseline_id = sha(root / "baseline.json")
    path = Path(cfg["work_dir"]) / "initialized.json"
    if path.exists():
        previous = load_initialized(cfg)
        if previous["baseline_id"] != baseline_id:
            raise ValueError("work directory belongs to another baseline")
        return {"status": "initialized", "initialized": str(path)}
    cloud = cloud or Cloud(cfg)
    refs = {
        p.relative_to(root).as_posix(): cloud.put(
            f"gs://{cfg['bucket']}/baselines/{baseline_id}/{p.relative_to(root).as_posix()}",
            p,
        )
        for p in files
    }
    runtime = {
        "image_uri": cfg["image_uri"],
        "environment_manifest": put_json(
            cloud,
            f"gs://{cfg['bucket']}/environments/{cfg['image_uri'].split(':')[-1]}.json",
            {
                "image_uri": cfg["image_uri"],
                "requirements_lock_sha256": baseline["runtime"][
                    "requirements_lock_sha256"
                ],
            },
            cfg["work_dir"],
        ),
    }
    selected = [
        publish_model(m, model_directory(root, m), cfg, cloud, runtime) for m in models
    ]
    delivery = copy.deepcopy(baseline["delivery"])
    for entry in delivery["diagnostics"]:
        if entry["status"] == "available":
            entry["evidence"] = refs[entry["evidence"]["local_path"]]
    initialized = {
        "baseline_id": baseline_id,
        "refs": refs,
        "runtime": runtime,
        "models": selected,
        "delivery": delivery,
        "sources": baseline["sources"],
        "model_records": models,
        "destination": destination(cfg),
    }
    path = Path(cfg["work_dir"]) / "initialized.json"
    from cloud.orchestrator.delivery_manifest import _diagnostics

    _diagnostics(
        delivery["diagnostics"],
        {(m["system"], m["horizon_months"]): m["package_id"] for m in selected},
    )
    for model, original in zip(selected, models):
        entries = [
            e
            for e in delivery["diagnostics"]
            if (e["system"], e["horizon_months"])
            == (model["system"], model["horizon_months"])
        ]
        save(
            version_path(cfg, model),
            {"model": model, "record": original, "diagnostics": entries},
        )
    save(path, initialized)
    return {"status": "initialized", "initialized": str(path)}


def destination(cfg):
    return {
        k: cfg[k]
        for k in ("project", "bucket", "request_bucket", "image_uri", "namespace")
    }


def load_initialized(cfg):
    body = read(Path(cfg["work_dir"]) / "initialized.json")
    if body["destination"] != destination(cfg):
        raise ValueError("initialized state belongs to a different destination")
    return body


def version_path(cfg, model):
    identity = json.dumps(
        [model["system"], model["horizon_months"], model["package_id"]]
    )
    return (
        Path(cfg["work_dir"])
        / "model_versions"
        / (hashlib.sha256(identity.encode()).hexdigest() + ".json")
    )


def valid_run_id(run_id):
    from cloud.orchestrator.delivery_manifest import _RUN_ID_RE

    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid run ID")


def source_choices(args):
    from tools.refresh_h5_inputs import conflict_aggregates, wfp_aggregates

    result = {}
    for family, converter in [("acled", conflict_aggregates), ("wfp", wfp_aggregates)]:
        action, raw = getattr(args, family), getattr(args, family + "_raw")
        if (action == "refresh") != bool(raw):
            raise ValueError(
                f"{family}: refresh requires raw file; keep rejects raw file"
            )
        result[family] = {"action": action}
        if raw:
            path = Path(raw).resolve()
            converter(path, cutoff=args.month)
            result[family].update(path=str(path), sha256=sha(path))
    return result


def preparation(cfg, init, args, run_id):
    from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES
    from cloud.orchestrator.prepare import (
        PREPARE_SCHEMA_VERSION,
        validate_prepare_request,
    )

    refs = init["refs"]
    body = {
        "schema_version": PREPARE_SCHEMA_VERSION,
        "prepare_id": run_id,
        "origin_month": args.month,
        "cutoff_utc": args.cutoff,
        "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
        "operator": cfg["operator"],
        "systems": {
            s: {
                "geometry": refs[f"assets/{s}/geometry.geojson"],
                "roster": refs[f"assets/{s}/roster.csv"],
                "history": {
                    f: refs[f"assets/{s}/history/{f}.csv"] for f in SYSTEM_FAMILIES[s]
                },
            }
            for s in SYSTEMS
        },
    }
    uri = f"gs://{cfg['bucket']}/prepare_requests/{run_id}/prepare_request.json"
    validate_prepare_request(
        body,
        request_uri=uri,
        request_generation="1",
        request_sha256=hashlib.sha256(json.dumps(body).encode()).hexdigest(),
    )
    return body, uri


def status(cfg, run_id, cloud):
    valid_run_id(run_id)
    root = f"gs://{cfg['bucket']}"
    state_path = Path(cfg["work_dir"]) / "runs" / run_id / "state.json"
    state = (
        read(state_path)
        if state_path.exists()
        else {"run_id": run_id, "phase": "unknown"}
    )
    prepared = cloud.latest(f"{root}/prepared/{run_id}/prepare_status.json")
    delivery = cloud.latest(f"{root}/runs/{run_id}/run_status.json")
    return {
        **state,
        "preparation": prepared[0] if prepared else None,
        "delivery": delivery[0] if delivery else None,
        "status": delivery[0]["status"]
        if delivery
        else (
            "preparation_failed"
            if prepared and prepared[0]["status"] == "failed"
            else state["phase"]
        ),
    }


def run(args, cfg, cloud=None):
    from cloud.orchestrator.delivery_manifest import (
        validate_delivery_request,
        _timestamp,
    )

    _timestamp(args.deadline, "deadline")
    deadline = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
    if args.execute and deadline <= datetime.now(timezone.utc):
        raise ValueError("execution deadline has passed")
    init = load_initialized(cfg)
    choices = source_choices(args)
    run_id = args.run_id or (
        "run-" + args.month.replace("-", "") + "-" + uuid.uuid4().hex[:12]
    )
    valid_run_id(run_id)
    body, uri = preparation(cfg, init, args, run_id)
    intent = {
        "month": args.month,
        "cutoff": args.cutoff,
        "deadline": args.deadline,
        "choices": choices,
        "baseline_id": init["baseline_id"],
        "models": init["models"],
        "runtime": init["runtime"],
        "config": cfg,
        "refs": init["refs"],
        "delivery": init["delivery"],
        "sources": init["sources"],
    }
    if not args.execute:
        return {
            "mode": "preview",
            "run_id": run_id,
            "prepare_request": body,
            "intent": intent,
        }
    cloud = cloud or Cloud(cfg)
    work = Path(cfg["work_dir"]) / "runs" / run_id
    state_path = work / "state.json"
    state = (
        read(state_path)
        if state_path.exists()
        else {"run_id": run_id, "phase": "created", "intent": intent}
    )
    if state["intent"] != intent:
        raise ValueError("run ID is bound to different inputs; use a new ID")
    save(state_path, state)
    if state["phase"] == "created":
        state["prepare_request"] = put_json(cloud, uri, body, work)
        # Save before submission: an interrupted API call must never be silently repeated.
        state["phase"] = "preparation_submission_pending"
        save(state_path, state)
        state["execution"] = cloud.launch(state["prepare_request"], args.deadline)
        state["phase"] = "preparing"
        save(state_path, state)
    until = time.monotonic() + args.wait_seconds
    while True:
        if deadline <= datetime.now(timezone.utc):
            raise ValueError(
                "execution deadline has passed; delivery was not submitted"
            )
        current = status(cfg, run_id, cloud)
        if current["delivery"] or state["phase"] == "submitted":
            return current
        prepared = current["preparation"]
        if prepared and prepared["status"] == "failed":
            raise ValueError(
                "preparation failed; retain this attempt and use a new run ID"
            )
        if prepared and prepared["status"] == "succeeded":
            break
        if time.monotonic() >= until:
            return current
        time.sleep(min(10, max(0, until - time.monotonic())))
    snapshot = cloud.latest(
        f"gs://{cfg['bucket']}/prepared/{run_id}/prepared_manifest.json"
    )
    if (
        not snapshot
        or snapshot[0].get("status") != "succeeded"
        or snapshot[0].get("origin_month") != args.month
        or snapshot[0].get("prepare_id") != run_id
    ):
        raise ValueError("missing or mismatched successful prepared snapshot")
    state.setdefault(
        "prepared_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    state.setdefault("prepared_snapshot", snapshot[1])
    save(state_path, state)
    request = copy.deepcopy(init["delivery"])
    refs = init["refs"]
    request.update(
        run_id=run_id,
        origin_month=args.month,
        models=init["models"],
        runtime=init["runtime"],
        prepared_snapshot={
            "prepare_id": run_id,
            "origin_month": args.month,
            "manifest": state["prepared_snapshot"],
        },
        operator=cfg["operator"],
        prepared_at=state.setdefault(
            "prepared_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
    )
    request["assets"] = {
        s: {
            k: refs[f"assets/{s}/{filename}"]
            for k, filename in [
                ("geometry", "geometry.geojson"),
                ("roster", "roster.csv"),
                ("population", "population.csv"),
                ("country_reference", "population.csv"),
                ("history_panel", "history_panel.csv"),
            ]
        }
        for s in SYSTEMS
    }
    request["assets"]["ipcch"]["fixed_features"] = refs[
        "assets/ipcch/fixed_features.csv"
    ]
    for family, choice in choices.items():
        request[family] = {
            "action": choice["action"],
            "converter_contract": init["sources"][family],
        }
        if choice["action"] == "keep":
            request[family]["retained_snapshot"] = refs[f"assets/retained_{family}.csv"]
        else:
            request[family]["raw_upload"] = cloud.put(
                f"gs://{cfg['bucket']}/raw/{run_id}/{family}/{Path(choice['path']).name}",
                choice["path"],
            )
    if "pointer_generation" not in state:
        pointer = cloud.latest(f"gs://{cfg['bucket']}/{cfg['namespace']}/current.json")
        state["pointer_generation"] = pointer[1]["generation"] if pointer else "0"
    request["release"] = {
        "namespace": cfg["namespace"],
        "expected_pointer_generation": state["pointer_generation"],
    }
    request_uri = f"gs://{cfg['request_bucket']}/requests/{run_id}/run_manifest.json"
    validate_delivery_request(
        request,
        request_uri=request_uri,
        request_generation="1",
        expected_release_namespace=cfg["namespace"],
    )
    save(state_path, state)
    if "request_body" not in state:
        state["request_body"] = request
        save(state_path, state)
    if deadline <= datetime.now(timezone.utc):
        raise ValueError("execution deadline has passed; delivery was not submitted")
    state["delivery_request"] = put_json(
        cloud, request_uri, state["request_body"], work
    )
    state["phase"] = "submitted"
    save(state_path, state)
    return status(cfg, run_id, cloud)


def download(args, cfg, cloud):
    current = status(cfg, args.run_id, cloud)
    if current["status"] != "succeeded":
        raise ValueError("delivery has not succeeded")
    release = cloud.latest(current["delivery"]["release"]["release_record"])
    if (
        not release
        or release[0]["run_id"] != args.run_id
        or release[0]["validation"] != "passed"
    ):
        raise ValueError("accepted release record missing")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    cloud.fetch(release[0]["manifest"], out / "manifest.json")
    cloud.fetch(release[0]["archive"], out / "webapp_model_bundle.tar.gz")
    inventory = read(out / "manifest.json")
    seen = set()
    for item in inventory["files"]:
        if item["path"] in seen or item["path"] in (
            "manifest.json",
            "webapp_model_bundle.tar.gz",
        ):
            raise ValueError("duplicate/reserved delivery member")
        seen.add(item["path"])
        target = safe(out, item["path"])
        uri = f"gs://{cfg['bucket']}/deliveries/{args.run_id}/{item['path']}"
        blob = cloud.blob(uri)
        blob.reload()
        cloud.fetch(
            {"uri": uri, "generation": str(blob.generation), "sha256": item["sha256"]},
            target,
        )
        if target.stat().st_size != item["size_bytes"] or sha(target) != item["sha256"]:
            raise ValueError(f"delivery member identity mismatch: {item['path']}")
    from cloud.orchestrator.delivery_bundle import verify_inventory

    verify_inventory(out)
    return {"status": "verified", "output": str(out)}


def models(args, cfg, cloud=None):
    path = Path(cfg["work_dir"]) / "initialized.json"
    init = load_initialized(cfg)
    if args.model_command == "register":
        package = Path(args.package)
        model = read(package / "operator-model.json")
        if (model["system"], model["horizon_months"]) != (args.system, args.horizon):
            raise ValueError("package slot mismatch")
        validate_model(model, package, init["runtime"], load=True)
        old = next(
            m
            for m in init["models"]
            if (m["system"], m["horizon_months"]) == (args.system, args.horizon)
        )
        if old["feature_schema_sha256"] != model["feature_schema_sha256"]:
            raise ValueError("replacement feature schema is incompatible")
        from cloud.orchestrator.delivery_manifest import (
            DIAGNOSTIC_FAMILIES,
            _diagnostics,
        )

        diagnostics = model.get(
            "diagnostics",
            [
                dict(
                    system=args.system,
                    horizon_months=args.horizon,
                    family=f,
                    status="unavailable",
                    evidence=None,
                    reason="missing_evidence",
                )
                for f in DIAGNOSTIC_FAMILIES[args.system]
            ],
        )
        selected_ids = {
            (m["system"], m["horizon_months"]): m["package_id"] for m in init["models"]
        }
        selected_ids[(args.system, args.horizon)] = model["package_id"]
        remaining = [
            e
            for e in init["delivery"]["diagnostics"]
            if (e["system"], e["horizon_months"]) != (args.system, args.horizon)
        ]
        _diagnostics(remaining + diagnostics, selected_ids)
        if not args.execute:
            return {"mode": "preview", "package_id": model["package_id"]}
        cloud = cloud or Cloud(cfg)
        record = {
            "model": publish_model(model, package, cfg, cloud, init["runtime"]),
            "record": model,
            "diagnostics": diagnostics,
        }
        destination = version_path(cfg, model)
        if destination.exists() and read(destination) != record:
            raise ValueError("immutable model version already exists")
        save(destination, record)
        return {
            "status": "registered",
            "package_id": model["package_id"],
            "selected": False,
        }
    record = read(
        version_path(
            cfg,
            {
                "system": args.system,
                "horizon_months": args.horizon,
                "package_id": args.version,
            },
        )
    )
    key = (args.system, args.horizon)
    selected = [
        record["model"] if (m["system"], m["horizon_months"]) == key else m
        for m in init["models"]
    ]
    records = [
        record["record"] if (m["system"], m["horizon_months"]) == key else m
        for m in init["model_records"]
    ]
    shared_members(records)
    from cloud.orchestrator.delivery_manifest import _models

    _models(selected)
    from cloud.orchestrator.delivery_manifest import _diagnostics

    diagnostics = [
        e
        for e in init["delivery"]["diagnostics"]
        if (e["system"], e["horizon_months"]) != key
    ] + record["diagnostics"]
    _diagnostics(
        diagnostics,
        {(m["system"], m["horizon_months"]): m["package_id"] for m in selected},
    )
    if not args.execute:
        return {"mode": "preview", "selected": selected}
    init["models"], init["model_records"] = selected, records
    init["delivery"]["diagnostics"] = diagnostics
    save(path, init)
    return {"status": "selected", "package_id": args.version}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "run", "status", "download", "models"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--execute", action="store_true")
        if name == "init":
            command.add_argument("--baseline", default=str(ROOT / "bootstrap"))
        if name in ("status", "download"):
            command.add_argument("--run-id", required=True)
        if name == "download":
            command.add_argument("--output", required=True)
        if name == "run":
            for field in ("month", "cutoff", "deadline"):
                command.add_argument("--" + field, required=True)
            command.add_argument("--run-id")
            command.add_argument("--wait-seconds", type=int, default=3600)
            for family in ("acled", "wfp"):
                command.add_argument(
                    "--" + family, choices=["keep", "refresh"], required=True
                )
                command.add_argument("--" + family + "-raw")
        if name == "models":
            sub = command.add_subparsers(dest="model_command", required=True)
            for action in ("register", "select"):
                item = sub.add_parser(action)
                item.add_argument("--system", choices=SYSTEMS, required=True)
                item.add_argument(
                    "--horizon", type=int, choices=HORIZONS, required=True
                )
                item.add_argument(
                    "--package" if action == "register" else "--version", required=True
                )
    args = parser.parse_args(argv)
    try:
        cfg = config(args.config)
        if args.command == "init":
            result = initialize(args, cfg)
        elif args.command == "run":
            result = run(args, cfg)
        elif args.command == "models":
            result = models(args, cfg)
        elif args.command == "status":
            result = status(cfg, args.run_id, Cloud(cfg))
        elif not args.execute:
            result = {
                "mode": "preview",
                "command": "download",
                "run_id": args.run_id,
                "output": args.output,
            }
        else:
            result = download(args, cfg, Cloud(cfg))
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
