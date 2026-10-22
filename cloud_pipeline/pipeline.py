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
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SYSTEMS = ("fewsnet", "ipcch")
HORIZONS = (0, 6, 12)
HOLD = "maintenance/hold.json"


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

    @property
    def store(self):
        from cloud.common.object_store import GCSObjectStore

        return GCSObjectStore(self.client)

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

    def pin(self, spec):
        """gs://bucket/object#generation -> exact ref with the SHA-256 of those bytes."""
        uri, _, generation = spec.partition("#")
        if not uri.startswith("gs://") or not re.fullmatch(r"[1-9][0-9]*", generation):
            raise ValueError(f"pin objects as gs://bucket/object#generation: {spec}")
        from cloud.orchestrator.delivery_job import PinnedDownloader

        digest = PinnedDownloader(
            self.client, Path(self.cfg["work_dir"]) / "verify"
        ).resolve(uri, generation)
        return {"uri": uri, "generation": generation, "sha256": digest}

    def delete(self, uri, generation):
        self.blob(uri).delete(if_generation_match=int(generation))

    def fetch(self, ref, destination):
        from cloud.orchestrator.delivery_job import PinnedDownloader

        source = PinnedDownloader(
            self.client, Path(self.cfg["work_dir"]) / "downloads"
        ).fetch(ref)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


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


FROZEN_REF_FIELDS = ("evidence", "source_availability", "source_evidence", "source_declarations")


def baseline_ref_fields(entry):
    """Diagnostic fields the baseline supplies as local files (pinned on upload)."""
    if entry["status"] == "available":
        return ("evidence",)
    return FROZEN_REF_FIELDS if entry["status"] == "frozen_output" else ()


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
        for field in baseline_ref_fields(entry):
            relative = entry[field]["local_path"]
            required_assets.add(relative)
            entry[field] = {
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
        for field in baseline_ref_fields(entry):
            entry[field] = refs[entry[field]["local_path"]]
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
    """Durable cloud state of a run: preparation (this run's or the reused snapshot), dispatch
    records, the delivery run status and, for candidates, the candidate record."""
    valid_run_id(run_id)
    root = f"gs://{cfg['bucket']}"
    state_path = Path(cfg["work_dir"]) / "runs" / run_id / "state.json"
    state = (
        read(state_path)
        if state_path.exists()
        else {"run_id": run_id, "phase": "unknown"}
    )
    prepare_id = state.get("prepare_id", run_id)
    prepared = cloud.latest(f"{root}/prepared/{prepare_id}/prepare_status.json")
    delivery = cloud.latest(f"{root}/runs/{run_id}/run_status.json")
    dispatch = {
        stage: (cloud.latest(f"{root}/dispatch/{run_id}/{stage}.json") or [None])[0]
        for stage in ("claim", "admission", "resolution")
    }
    candidate = cloud.latest(f"{root}/candidates/{run_id}/candidate.json")
    selection = state.get("intent", {}).get("execution")
    rejected = [r for r in dispatch.values() if r and r.get("status") == "rejected"]
    resolution = dispatch["resolution"]
    prepare_only = selection is not None and not selection["inference_systems"]
    if prepare_only and resolution and resolution["status"] == "resolved":
        terminal = "prepared"  # the immutable snapshot ref is the result; no delivery is dispatched
    else:
        terminal = None
    return {
        **state,
        "preparation": prepared[0] if prepared else None,
        "preparation_mode": None
        if selection is None
        else ("prepared by the workflow" if selection["remote_update"] else f"reused {prepare_id}"),
        "dispatch": dispatch,
        "delivery": delivery[0] if delivery else None,
        "candidate": {"record": candidate[0], "ref": candidate[1]} if candidate else None,
        "prepared_snapshot": resolution["prepared_snapshot"] if terminal else None,
        "status": terminal
        or (
            delivery[0]["status"]
            if delivery
            else (
                "preparation_failed"
                if prepared and prepared[0]["status"] == "failed"
                else ("dispatch_rejected" if rejected else state["phase"])
            )
        ),
    }


def run(args, cfg, cloud=None):
    """Publish this month's initial workflow intent. The cloud Workflow runs the selected steps
    (preparation, snapshot binding, delivery); this process never launches or polls them."""
    from cloud.orchestrator.delivery_manifest import _timestamp

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
        "execution": execution_options(args),
    }
    if not args.execute:
        return {
            "mode": "preview",
            "run_id": run_id,
            "prepare_request": body if intent["execution"]["remote_update"] else None,
            "intent": intent,
        }
    cloud = cloud or Cloud(cfg)
    require_admission(cfg, cloud, run_id)
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
    if state["phase"] == "submitted":  # resume: the intent is already published
        return status(cfg, run_id, cloud)
    return submit_intent(args, cfg, cloud, init, choices, body, uri, state, state_path, deadline)


def delivery_request(cfg, cloud, init, args, choices, state, snapshot):
    """The delivery request for this run's bound inputs (legacy and selected runs alike)."""
    run_id = state["run_id"]
    request = copy.deepcopy(init["delivery"])
    refs = init["refs"]
    request.update(
        run_id=run_id,
        origin_month=args.month,
        models=init["models"],
        runtime=init["runtime"],
        prepared_snapshot=snapshot,
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
    return request


def execution_options(args):
    """Manifest step selection. Default = the monthly run: remote update, both systems, current."""
    remote = getattr(args, "remote_update", None) or "on"
    infer = getattr(args, "infer", None)
    systems = list(SYSTEMS) if infer is None else ([] if infer in ("", "none") else infer.split(","))
    inherit = {}
    if getattr(args, "inherit", None):
        system, _, source = args.inherit.partition("=")
        if not (system and source and args.inherit_manifest and args.inherit_archive):
            raise ValueError(
                "--inherit SYSTEM=SOURCE_DELIVERY_ID needs --inherit-manifest and --inherit-archive"
            )
        inherit[system] = {
            "source_delivery_id": source,
            "manifest": args.inherit_manifest,
            "archive": args.inherit_archive,
        }
    prepared = getattr(args, "prepared_manifest", None)
    if (remote == "on") == bool(prepared):
        raise ValueError(
            "--remote-update on prepares a new snapshot; off requires --prepared-manifest"
        )
    return {
        "remote_update": remote == "on",
        "inference_systems": systems,
        "inherit": inherit,
        "prepared_manifest": prepared,
        "publication": getattr(args, "publication", None) or "current",
    }


def submit_intent(args, cfg, cloud, init, choices, body, uri, state, state_path, deadline):
    """Publish the initial workflow intent; the cloud Workflow (not this process) runs the
    selected steps. Remote update on: its exact prepare request is published here and prepared
    in the cloud. Off: the named succeeded snapshot is reused; no preparation is started."""
    from cloud.orchestrator.delivery_manifest import validate_delivery_request

    run_id, work = state["run_id"], Path(state_path).parent
    selection = state["intent"]["execution"]
    if "pinned" not in state:
        state["pinned"] = {
            "inherit": {
                system: inherited_source(cloud, work, system, source, args.month)
                for system, source in selection["inherit"].items()
            },
            "prepared_manifest": cloud.pin(selection["prepared_manifest"])
            if selection["prepared_manifest"]
            else None,
        }
        save(state_path, state)
    pinned = state["pinned"]
    if selection["remote_update"]:
        if "prepare_request" not in state:
            state["prepare_request"] = put_json(cloud, uri, body, work)
        state["prepare_id"], snapshot = body["prepare_id"], None
    else:
        cloud.fetch(pinned["prepared_manifest"], work / "prepared_manifest.json")
        manifest = read(work / "prepared_manifest.json")
        if manifest.get("status") != "succeeded" or manifest.get("origin_month") != args.month:
            raise ValueError("--prepared-manifest is not a succeeded snapshot for this month")
        state["prepare_id"] = manifest["prepare_id"]
        snapshot = {
            "prepare_id": manifest["prepare_id"],
            "origin_month": args.month,
            "manifest": pinned["prepared_manifest"],
        }
    save(state_path, state)
    request = delivery_request(cfg, cloud, init, args, choices, state, snapshot)
    request["execution"] = {
        "remote_update": selection["remote_update"],
        "inference_systems": selection["inference_systems"],
        "prepare_request": state.get("prepare_request") if selection["remote_update"] else None,
        "inherit": pinned["inherit"],
        "publication": selection["publication"],
    }
    request_uri = f"gs://{cfg['request_bucket']}/requests/{run_id}/run_manifest.json"
    validate_delivery_request(
        request,
        request_uri=request_uri,
        request_generation="1",
        expected_release_namespace=cfg["namespace"],
    )
    if "request_body" not in state:
        state["request_body"] = request
        save(state_path, state)
    if deadline <= datetime.now(timezone.utc):
        raise ValueError("execution deadline has passed; the intent was not submitted")
    state["delivery_request"] = put_json(cloud, request_uri, state["request_body"], work)
    state["phase"] = "submitted"
    save(state_path, state)
    return status(cfg, run_id, cloud)


def inherited_source(cloud, work, system, source, month):
    """Pinned refs of an inherited system's accepted source; its named delivery ID must be the
    source manifest's recorded run (the archive's own run ID is checked again in the receipt)."""
    manifest, archive = cloud.pin(source["manifest"]), cloud.pin(source["archive"])
    cloud.fetch(manifest, Path(work) / f"inherited_{system}_manifest.json")
    recorded = read(Path(work) / f"inherited_{system}_manifest.json").get("provenance", {}).get("run_id")
    if recorded != source["source_delivery_id"]:
        raise ValueError(f"inherited {system} source is run {recorded}, not {source['source_delivery_id']}")
    return {"source_delivery_id": source["source_delivery_id"], "origin_month": month,
            "manifest": manifest, "archive": archive}


def require_admission(cfg, cloud, run_id):
    """Both operator and cloud dispatch respect a maintenance hold: only its bound runs proceed."""
    hold = cloud.latest(f"gs://{cfg['bucket']}/{HOLD}")
    if hold and run_id not in hold[0]["admitted_run_ids"]:
        raise ValueError(
            f"monthly admission is paused by maintenance {hold[0]['operation_id']}; {run_id} is not admitted"
        )


def download(args, cfg, cloud):
    """Download and verify a published release or, with ``--candidate``, the run's exact validated
    candidate (before promotion; the current pointer is never read or changed)."""
    current = status(cfg, args.run_id, cloud)
    if current["status"] != "succeeded":
        raise ValueError("delivery has not succeeded")
    if getattr(args, "candidate", False):
        found = current["candidate"]
        if (
            not found
            or found["record"]["run_id"] != args.run_id
            or found["record"]["validation"] != "passed"
        ):
            raise ValueError("validated candidate record missing")
        record, record_ref = found["record"], found["ref"]
    else:
        if not (current["delivery"].get("release") or {}).get("release_record"):
            raise ValueError("run has no published release (a candidate? use --candidate)")
        release = cloud.latest(current["delivery"]["release"]["release_record"])
        if (
            not release
            or release[0]["run_id"] != args.run_id
            or release[0]["validation"] != "passed"
        ):
            raise ValueError("accepted release record missing")
        record, record_ref = release
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    cloud.fetch(record["manifest"], out / "manifest.json")
    cloud.fetch(record["archive"], out / "webapp_model_bundle.tar.gz")
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
    receipt = {
        "run_id": args.run_id,
        "kind": "candidate" if getattr(args, "candidate", False) else "release",
        "record": record_ref,
        "record_sha256": record_ref["sha256"],
        "manifest": record["manifest"],
        "archive": record["archive"],
        "members": len(seen),
        "output": str(out),
    }
    save(out.parent / f"{out.name}.download.json", receipt)
    return {"status": "verified", **receipt}


RECEIPT_SCHEMA = "operator-candidate-receipt-v1"
HOLD_SCHEMA = "maintenance-hold-v1"
SHARED_WORKFLOW = "oct-delivery-trigger"


def verify_candidate(args, cfg, cloud):
    """Bind a downloaded candidate's integrity and relocated replay into a receipt (no promotion).

    Checks: the download is this run's candidate record, inventory and pre-package validation pass,
    and a relocated replay with the bundle's own runtime reproduces every table while inherited
    systems are copied, never scored. Inherited sources must be the request's pinned sources.
    """
    import os
    import tarfile

    from cloud.orchestrator.delivery_bundle import inherited_systems, validate_delivery, verify_inventory

    out = Path(args.download).resolve()
    downloaded = read(out.parent / f"{out.name}.download.json")
    found = status(cfg, args.run_id, cloud)["candidate"]
    if downloaded["kind"] != "candidate" or not found or found["ref"] != downloaded["record"]:
        raise ValueError("download is not this run's current candidate record")
    record = found["record"]
    for name, key in (("manifest.json", "manifest"), ("webapp_model_bundle.tar.gz", "archive")):
        if sha(out / name) != record[key]["sha256"]:
            raise ValueError(f"downloaded {name} is not the candidate's {key}")
    verify_inventory(out)
    validation = validate_delivery(out)
    work = Path(cfg["work_dir"]) / "runs" / args.run_id
    cloud.fetch(record["request"], work / "executed_request.json")
    request = read(work / "executed_request.json")
    relocated, replayed = out.parent / f"{out.name}-relocated", out.parent / f"{out.name}-replay"
    relocated.mkdir(exist_ok=False)
    with tarfile.open(out / "webapp_model_bundle.tar.gz", "r:gz") as archive:
        archive.extractall(relocated, filter="data")
    isolated = out.parent / f"{out.name}-replay-cwd"
    isolated.mkdir(exist_ok=False)
    probe = ("import sys, cloud.orchestrator.delivery_bundle as b, fewsnet_partitioned_rf_pipeline as f, "
             "model_pipeline as m; print('REPLAY_RUNTIME ' + __import__('json').dumps([b.__file__, f.__file__, "
             "list(m.__path__)]), file=sys.stderr); sys.exit(b.main(sys.argv[1:]))")
    completed = subprocess.run(  # -P and an empty cwd: only the bundle's runtime/ is importable as source
        [args.python or sys.executable, "-P", "-c", probe, "rescore", "--root", str(relocated), "--output", str(replayed)],
        capture_output=True, text=True, cwd=isolated, env={**os.environ, "PYTHONPATH": str(relocated / "runtime")},
    )
    (out.parent / f"{out.name}-replay.json").write_text(completed.stdout + completed.stderr[-4000:])
    replay = json.loads(completed.stdout) if completed.returncode in (0, 1) and completed.stdout else {}
    runtime = next((json.loads(line.split(" ", 1)[1]) for line in completed.stderr.splitlines()
                    if line.startswith("REPLAY_RUNTIME ")), None)
    bundled = str((relocated / "runtime").resolve())
    inherited = inherited_systems(out)
    expected = (request.get("execution") or {}).get("inherit", {})
    checks = {
        "candidate_record_bound": True,
        "inventory_verified": True,
        "pre_package_validation": validation["status"] == "passed",
        "relocated_replay_all_equal": completed.returncode == 0 and replay.get("all_equal") is True,
        "replay_used_bundled_runtime": runtime is not None and all(
            str(Path(item).resolve()).startswith(bundled) for item in [runtime[0], runtime[1], *runtime[2]]),
        "inherited_not_rescored": all(
            replay.get("summary", {}).get(str(h), {}).get(system) == "inherited"
            for h in HORIZONS for system in inherited
        ),
        "inherited_sources_match_request": set(inherited) == set(expected) and all(
            inherited[system]["manifest"] == expected[system]["manifest"]
            and inherited[system]["archive"] == expected[system]["archive"]
            for system in inherited
        ),
        "inherited_source_runs_match": all(
            inherited[system].get("source_run_id") == expected[system]["source_delivery_id"]
            == inherited[system].get("source_delivery_id")
            for system in inherited if system in expected
        ),
    }
    extra = []
    for path in args.check or []:
        body = read(path)
        extra.append({"path": str(Path(path).resolve()), "sha256": sha(path), "status": body.get("status")})
        checks[f"extra:{Path(path).name}"] = body.get("status") == "passed"
    inventory = read(out / "manifest.json")
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "run_id": args.run_id,
        "verified_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidate": found["ref"],
        "manifest": record["manifest"],
        "archive": record["archive"],
        "request": record["request"],
        "execution": record.get("execution"),
        "image_uri": inventory.get("provenance", {}).get("image_uri"),
        "model_inventory_sha256": sha(out / "model_inventory.json"),
        "validation_failures": validation["failures"],
        "replay": {"summary": replay.get("summary"), "all_equal": replay.get("all_equal"), "runtime": runtime,
                   "output_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest()},
        "extra_checks": extra,
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
    }
    path = work / "candidate_receipt.json"
    save(path, receipt)
    if args.execute and receipt["status"] == "passed":
        receipt_ref = cloud.put(
            f"gs://{cfg['bucket']}/candidates/{args.run_id}/verification_receipt.json", path
        )
        return {**receipt, "receipt": receipt_ref, "local": str(path)}
    return {**receipt, "local": str(path)}


def gcloud_json(argv):
    completed = subprocess.run(argv, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout or "null")


def shared_runtime(cfg, runner):
    """Live shared job/workflow settings: the predecessor a failed switch restores."""
    project, region = cfg["project"], cfg["region"]
    jobs = {}
    for name in ("oct-delivery", cfg["prepare_job"]):
        body = runner(["gcloud", "run", "jobs", "describe", name, "--project", project, "--region", region,
                       "--format=json"])
        container = body["spec"]["template"]["spec"]["template"]["spec"]["containers"][0]
        jobs[name] = {
            "image": container["image"],
            "command": container.get("command", []),
            "args": container.get("args", []),
            "env": container.get("env", []),
            "service_account": body["spec"]["template"]["spec"]["template"]["spec"].get("serviceAccountName"),
            "template_sha256": hashlib.sha256(
                json.dumps(body["spec"]["template"], sort_keys=True).encode()
            ).hexdigest(),
        }
    workflow = runner(["gcloud", "workflows", "describe", SHARED_WORKFLOW, "--project", project,
                       "--location", region, "--format=json"])
    source = workflow.get("sourceContents", "")
    return {
        "jobs": jobs,
        "workflow": {
            "revision_id": workflow.get("revisionId"),
            "service_account": workflow.get("serviceAccount"),
            "env": workflow.get("userEnvVars", {}),
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        },
        "workflow_source": source,
    }


def active_work(cfg, runner):
    """Running shared-job executions, active workflow executions and unfinished Batch jobs."""
    project, region = cfg["project"], cfg["region"]
    running = []
    for name in ("oct-delivery", cfg["prepare_job"]):
        executions = runner(["gcloud", "run", "jobs", "executions", "list", "--job", name, "--project", project,
                             "--region", region, "--format=json"]) or []
        running += [
            {"job": name, "execution": item["metadata"]["name"]}
            for item in executions
            if not item.get("status", {}).get("completionTime")
        ]
    workflows = runner(["gcloud", "workflows", "executions", "list", SHARED_WORKFLOW, "--project", project,
                        "--location", region, "--filter=state:ACTIVE", "--format=json"]) or []
    batch = runner(["gcloud", "batch", "jobs", "list", "--project", project, "--location", region,
                    "--filter=status.state:(QUEUED OR SCHEDULED OR RUNNING)", "--format=json"]) or []
    return {
        "job_executions": running,
        "workflow_executions": [item["name"] for item in workflows],
        "batch_jobs": [item["name"] for item in batch],
    }


def _setup_commands(cfg):
    import importlib.util

    spec = importlib.util.spec_from_file_location("deploy_setup", ROOT / "deploy" / "setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The Eventarc trigger already exists and is unchanged; only jobs, grants and workflow move.
    return [c for c in module.commands(cfg) if c[:3] != ["gcloud", "eventarc", "triggers"]]


def _grant_identity(argv):
    """(resource, role, member, condition) of one setup add-iam-policy-binding command."""
    resource = argv[4]
    condition = next((a.split("=", 1)[1].split("),title=")[0] + ")" for a in argv
                      if a.startswith("--condition=expression=")), None)
    return (resource, argv[argv.index("--role") + 1], argv[argv.index("--member") + 1], condition)


def _policy_grants(resource, policy):
    return {(resource, binding["role"], member, (binding.get("condition") or {}).get("expression"))
            for binding in (policy or {}).get("bindings", []) for member in binding.get("members", [])}


def gate_commands(cfg, operation):
    """Install the hold-aware Workflow before any job change: the new grants it needs (prepare job,
    request/data object read, dispatch-claim create) then the new source with the predecessor
    delivery image (jobs unchanged), so only the bound runs are admitted from here on."""
    commands = _setup_commands(cfg)
    grants = [c for c in commands if "add-iam-policy-binding" in c]
    workflow = next(c for c in commands if c[:3] == ["gcloud", "workflows", "deploy"])
    env = dict(item.split("=", 1) for item in workflow[-1].split(","))
    env["DELIVERY_IMAGE_URI"] = operation["predecessor"]["workflow"]["env"]["DELIVERY_IMAGE_URI"]
    return grants + [workflow[:-1] + [",".join(f"{k}={v}" for k, v in env.items())]]


def restore_commands(cfg, operation):
    """Concrete commands that put the recorded predecessor shared settings back: job images/args,
    the predecessor workflow source and env, and removal of only the grants it did not have."""
    project, region = cfg["project"], cfg["region"]
    predecessor = operation["predecessor"]
    commands = [
        ["gcloud", "run", "jobs", "update", name, "--project", project, "--region", region,
         "--image", job["image"], "--args=" + ",".join(job["args"])]
        for name, job in predecessor["jobs"].items()
    ]
    env = predecessor["workflow"]["env"]
    commands.append(["gcloud", "workflows", "deploy", SHARED_WORKFLOW, "--project", project, "--location",
                     region, "--source", str(Path(operation["directory"]) / "predecessor-workflow.yaml"),
                     "--service-account", predecessor["workflow"]["service_account"],
                     "--set-env-vars", ",".join(f"{k}={v}" for k, v in sorted(env.items()))])
    existing = {tuple(item) for item in predecessor["grants"]}
    for argv in _setup_commands(cfg):
        if "add-iam-policy-binding" in argv and _grant_identity(argv) not in existing:
            commands.append([a.replace("add-iam-policy-binding", "remove-iam-policy-binding") for a in argv])
    return commands


def _identities(runtime):
    return {"jobs": {name: {k: job[k] for k in ("image", "command", "args", "env")}
                     for name, job in runtime["jobs"].items()},
            "workflow": {k: runtime["workflow"][k] for k in ("env", "source_sha256", "service_account")}}


def _grants(cfg, runner):
    project, region = cfg["project"], cfg["region"]
    grants = set()
    for name in ("oct-delivery", cfg["prepare_job"]):
        grants |= _policy_grants(name, runner(["gcloud", "run", "jobs", "get-iam-policy", name, "--project", project,
                                               "--region", region, "--format=json"]))
    for bucket in (cfg["request_bucket"], cfg["bucket"]):
        grants |= _policy_grants("gs://" + bucket, runner(["gcloud", "storage", "buckets", "get-iam-policy",
                                                           "gs://" + bucket, "--format=json"]))
    return sorted(grants, key=str)


def maintenance(args, cfg, cloud=None, runner=gcloud_json):
    """Bounded maintenance operation on the shared jobs/workflow, owned by one operation ID.

    hold: record the predecessor shared settings/grants, then pause operator admission (create-only
    hold object admitting only the bound runs). gate: install the hold-aware Workflow (grants + new
    source, predecessor job image) and verify it, so cloud dispatch is paused too; then reconcile
    active work again. apply: change the jobs/workflow image once nothing else is running.
    restore: put every predecessor back (pointer first checked for drift, then fallback, config,
    pointer and shared settings). release: verify all live identities equal the activated (or
    restored) record, then delete the hold at its generation. Interruption keeps the hold.
    """
    directory = Path(cfg["work_dir"]) / "operations" / args.operation_id
    path = directory / "operation.json"
    hold_uri = f"gs://{cfg['bucket']}/{HOLD}"
    operation = read(path) if path.exists() else None
    command = args.maintenance_command
    if command == "hold":
        admitted = args.admit.split(",")
        for run_id in admitted:
            valid_run_id(run_id)
        if not args.execute:
            return {"mode": "preview", "operation_id": args.operation_id, "admitted_run_ids": admitted}
        cloud = cloud or Cloud(cfg)
        existing = cloud.latest(hold_uri)
        if existing and existing[0]["operation_id"] != args.operation_id:
            raise ValueError(f"maintenance {existing[0]['operation_id']} already holds admission")
        if operation is None:
            predecessor = shared_runtime(cfg, runner)
            predecessor["grants"] = _grants(cfg, runner)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "predecessor-workflow.yaml").write_text(predecessor.pop("workflow_source"))
            operation = {
                "operation_id": args.operation_id,
                "owner": cfg["operator"],
                "directory": str(directory),
                "admitted_run_ids": admitted,
                "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "predecessor": predecessor,
                "phase": "hold_pending",
            }
            save(path, operation)  # durable before admission is paused
        if operation["admitted_run_ids"] != admitted:
            raise ValueError("operation is bound to different admitted runs")
        body = {
            "schema_version": HOLD_SCHEMA,
            "operation_id": args.operation_id,
            "owner": operation["owner"],
            "admitted_run_ids": admitted,
            "created_utc": operation["created_utc"],
            "predecessor_sha256": hashlib.sha256(
                json.dumps(operation["predecessor"], sort_keys=True).encode()
            ).hexdigest(),
        }
        operation["hold"] = put_json(cloud, hold_uri, body, directory)
        if operation["phase"] == "hold_pending":
            operation["phase"] = "holding"
        operation["active_at_hold"] = active_work(cfg, runner)
        save(path, operation)
        return {"status": operation["phase"], "hold": operation["hold"], "active_work": operation["active_at_hold"],
                "next": gate_commands(cfg, operation), "restore_commands": restore_commands(cfg, operation)}
    if operation is None:
        raise ValueError(f"no maintenance operation {args.operation_id}")
    cloud = cloud or Cloud(cfg)
    hold = cloud.latest(hold_uri)
    if command == "status":
        return {**operation, "hold_object": hold, "active_work": active_work(cfg, runner),
                "live": _identities(shared_runtime(cfg, runner)),
                "restore_commands": restore_commands(cfg, operation)}
    if not hold or hold[0]["operation_id"] != args.operation_id:
        raise ValueError("this operation does not hold admission")
    if command == "gate":
        commands = gate_commands(cfg, operation)
        if not args.execute:
            return {"mode": "preview", "commands": commands}
        if operation["phase"] not in ("holding", "gating"):
            raise ValueError(f"operation is {operation['phase']}; the gate follows the hold")
        operation["phase"] = "gating"
        save(path, operation)
        for argv in commands:
            subprocess.run(argv, check=True)
        live = shared_runtime(cfg, runner)
        source = (ROOT / "deploy" / "workflow.yaml").read_text()
        if live["workflow"]["source_sha256"] != hashlib.sha256(source.encode()).hexdigest() or any(
                job["image"] != operation["predecessor"]["jobs"][name]["image"] for name, job in live["jobs"].items()):
            raise ValueError("live workflow is not the hold-aware source over the unchanged jobs")
        operation["gate"] = {"workflow_revision": live["workflow"]["revision_id"],
                             "source_sha256": live["workflow"]["source_sha256"],
                             "active_after_gate": active_work(cfg, runner)}
        operation["phase"] = "gated"
        save(path, operation)
        return {"status": "gated", **operation["gate"]}
    if command == "apply":
        if operation["phase"] not in ("gated", "applying"):
            raise ValueError(f"operation is {operation['phase']}; install and verify the gate before job changes")
        busy = active_work(cfg, runner)
        if any(busy.values()) and not args.reconciled:
            raise ValueError(f"active work must be finished or reconciled first: {busy}")
        commands = _setup_commands(cfg)
        if not args.execute:
            return {"mode": "preview", "commands": commands, "active_work": busy}
        operation.update(phase="applying", reconciled=args.reconciled, applied_commands=commands)
        save(path, operation)
        for argv in commands:
            subprocess.run(argv, check=True)
        operation["intended"] = _identities(shared_runtime(cfg, runner))
        operation["phase"] = "shared_changed"
        save(path, operation)
        return {"status": "shared_changed", "intended": operation["intended"]}
    if command == "restore":
        commands = restore_commands(cfg, operation)
        if not args.execute:
            return {"mode": "preview", "commands": commands, "promotion": operation.get("promotion")}
        operation["phase"] = "restoring"
        save(path, operation)
        _restore_activation(cfg, cloud, operation)
        for argv in commands:
            subprocess.run(argv, check=True)
        operation["phase"] = "restored"
        save(path, operation)
        return {"status": "restored"}
    if command == "release":
        outcome = operation["phase"]
        if outcome not in ("activated", "restored"):
            raise ValueError(f"operation is {outcome}; release only after activation or restoration")
        live = _identities(shared_runtime(cfg, runner))
        checks = {"shared_runtime": live == (operation.get("intended") if outcome == "activated"
                                             else _identities(operation["predecessor"]))}
        if outcome == "activated":
            checks["images"] = all(job["image"] == cfg["image_uri"] for job in live["jobs"].values())
        if operation.get("promotion"):
            want = "intended" if outcome == "activated" else "prior"
            checks.update({f"{name}_{want}": state == want
                           for name, state in _activation_states(cloud, operation["promotion"]).items()})
        if not all(checks.values()):
            raise ValueError(f"live identities differ from the recorded {outcome} state; the hold stays: {checks}")
        if not args.execute:
            return {"mode": "preview", "release": outcome, "checks": checks}
        cloud.delete(hold_uri, operation["hold"]["generation"])
        operation["phase"] = "released_" + outcome
        operation["released_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save(path, operation)
        return {"status": operation["phase"], "checks": checks}
    raise ValueError(f"unknown maintenance command {command}")


def _manifest_sha(directory):
    member = Path(directory) / "manifest.json"
    return sha(member) if member.is_file() else None


def _inspect(cloud, promotion):
    """Actual state of each promotion step (prior, midway, intended or foreign) and the observed
    pointer generation the next pointer mutation must be conditioned on."""
    prior, intended = promotion["prior"], promotion["intended"]
    current = cloud.latest(prior["pointer_uri"])
    generation = current[1]["generation"] if current else "0"
    if current and current[0].get("release_record") == intended["release_record"]:
        pointer = "intended"
    elif generation == prior["pointer_generation"] or (
            current and prior["pointer_body"] is not None and current[0] == json.loads(prior["pointer_body"])):
        pointer = "prior"  # untouched, or the predecessor body CAS-restored at a new generation
    else:
        pointer = "foreign"
    config = Path(prior["config_path"])
    digest = sha(config) if config.is_file() else None
    config_state = ("intended" if digest == intended["config_sha256"]
                    else "prior" if digest == prior["config_sha256"] else "foreign")
    states = {"pointer": pointer, "operator_config": config_state, "fallback": _fallback_state(promotion)}
    return states, generation


def _activation_states(cloud, promotion):
    return _inspect(cloud, promotion)[0]


def _fallback_state(promotion):
    f, prior, intended = promotion["fallback"], promotion["prior"], promotion["intended"]
    layout = (_manifest_sha(f["active"]), _manifest_sha(f["staged"]), _manifest_sha(f["predecessor"]))
    old, new = prior["fallback_manifest_sha256"], intended["fallback_manifest_sha256"]
    return {(old, new, None): "prior", (None, new, old): "midway", (new, None, old): "intended"}.get(layout, "foreign")


def _rename_from(promotion, expected, source, target):
    """One fallback rename, only from the expected layout re-checked immediately before it."""
    if _fallback_state(promotion) != expected:
        raise ValueError(f"fallback layout changed outside this operation (expected {expected})")
    Path(source).rename(target)


def _write_config_from(path, expected_sha256, data):
    """Write the normal config only if its current bytes are still the recorded expected bytes."""
    if sha(path) != expected_sha256:
        raise ValueError("normal operator config changed outside this operation; not overwritten")
    _write_bytes(path, data)


def _restore_activation(cfg, cloud, operation):
    """Undo promotion steps by inspection, never by ledger flags. Drift anywhere stops before any
    change; the pointer goes first, conditioned on the inspected generation of our pointer, so a
    concurrent release landing after inspection fails the precondition before local defaults or
    the fallback change; every local write re-checks its recorded identity immediately before."""
    promotion = operation.get("promotion")
    if not promotion:
        return
    states, generation = _inspect(cloud, promotion)
    if "foreign" in states.values():
        raise ValueError(f"state changed outside this operation; nothing restored: {states}")
    f, prior = promotion["fallback"], promotion["prior"]
    if states["pointer"] == "intended":
        if prior["pointer_body"] is None:  # the predecessor was an absent pointer
            cloud.delete(prior["pointer_uri"], generation)
        else:  # CAS the recorded predecessor body back over exactly the inspected pointer generation
            cloud.store.write_text(prior["pointer_uri"], prior["pointer_body"], if_generation_match=int(generation))
    if states["operator_config"] == "intended":
        _write_config_from(prior["config_path"], promotion["intended"]["config_sha256"],
                           Path(promotion["config_backup"]).read_bytes())
    if states["fallback"] == "intended":
        _rename_from(promotion, "intended", f["active"], f["staged"])
        states["fallback"] = "midway"
    if states["fallback"] == "midway":
        _rename_from(promotion, "midway", f["predecessor"], f["active"])
    after = _activation_states(cloud, promotion)
    if set(after.values()) != {"prior"}:
        raise ValueError(f"restore did not reach every recorded predecessor: {after}")


def _write_bytes(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _publish_resumable(store, root, run_id, namespace, expected, record):
    """The existing publish CAS; after an interruption between the immutable release record and the
    pointer write, an identical record is reused and only the pointer CAS is repeated."""
    from cloud.orchestrator.delivery_run import publish

    record_uri = f"{root}/{namespace}/releases/{run_id}/release.json"
    existing = store.get_metadata(record_uri)
    if existing is None:
        return publish(store, root, run_id=run_id, namespace=namespace, expected_pointer_generation=expected,
                       release_record=record, validate=lambda: None)
    if store.read_text(record_uri) != json.dumps(dict(record), indent=2, sort_keys=True) + "\n":
        raise ValueError(f"{record_uri} already holds a different release record")
    pointer = {"run_id": run_id, "release_record": record_uri, "release_record_generation": existing.generation}
    moved = store.write_text(f"{root}/{namespace}/current.json", json.dumps(pointer, indent=2, sort_keys=True) + "\n",
                             if_generation_match=int(expected))
    return {"pointer_uri": f"{root}/{namespace}/current.json", "pointer_generation": moved.generation,
            "release_record": record_uri}


def promote(args, cfg, cloud=None, runner=gcloud_json):
    """Promote the exact verified candidate: release pointer CAS against the expected predecessor,
    then the normal operator config and the active fallback. Prior and intended identities are
    recorded before any change; every step (and resume/restore) acts on the inspected actual state,
    so an interrupted switch finishes or restores without rescoring and never overwrites a
    concurrent pointer or config change."""
    directory = Path(cfg["work_dir"]) / "operations" / args.operation_id
    path = directory / "operation.json"
    operation = read(path)
    if operation["phase"] not in ("shared_changed", "promoting", "activation_inconsistent"):
        raise ValueError(f"operation is {operation['phase']}; promotion needs the applied shared change")
    if args.run_id not in operation["admitted_run_ids"]:
        raise ValueError("run is not bound to this maintenance operation")
    cloud = cloud or Cloud(cfg)
    hold = cloud.latest(f"gs://{cfg['bucket']}/{HOLD}")
    if not hold or hold[0]["operation_id"] != args.operation_id:
        raise ValueError("this operation does not hold admission")
    receipt = read(args.receipt)
    found = status(cfg, args.run_id, cloud)["candidate"]
    if (receipt.get("schema_version") != RECEIPT_SCHEMA or receipt["status"] != "passed"
            or receipt["run_id"] != args.run_id or not found or receipt["candidate"] != found["ref"]
            or receipt["manifest"] != found["record"]["manifest"] or receipt["archive"] != found["record"]["archive"]):
        raise ValueError("receipt is not a passed verification of this run's candidate")
    if receipt["image_uri"] != cfg["image_uri"]:
        raise ValueError("candidate runtime is not this operator config's image")
    run_state = read(Path(cfg["work_dir"]) / "runs" / args.run_id / "state.json")
    expected = run_state["request_body"]["release"]["expected_pointer_generation"]
    root, namespace = f"gs://{cfg['bucket']}", cfg["namespace"]
    pointer_uri = f"{root}/{namespace}/current.json"
    normal, staged, active = Path(args.normal_config), Path(args.fallback_staged), Path(args.fallback_active)
    promotion = operation.get("promotion")
    if promotion is None:
        current = cloud.latest(pointer_uri)
        if (current[1]["generation"] if current else "0") != expected:
            raise ValueError(f"current pointer is not the expected predecessor generation {expected}")
        if _manifest_sha(staged) != receipt["manifest"]["sha256"]:
            raise ValueError("staged fallback is not the verified candidate")
        backup = directory / "predecessor-normal-config.json"
        prior_config = normal.read_bytes()
        intended_config = (json.dumps({**json.loads(prior_config), "image_uri": cfg["image_uri"],
                                       "work_dir": cfg["work_dir"]}, indent=2, sort_keys=True) + "\n").encode()
        promotion = {
            "run_id": args.run_id,
            "receipt_sha256": sha(args.receipt),
            "config_backup": str(backup),
            "intended_config_text": intended_config.decode(),
            "fallback": {"active": str(active), "staged": str(staged),
                         "predecessor": str(active.with_name(active.name + ".predecessor-" + args.operation_id))},
            "prior": {"pointer_uri": pointer_uri, "pointer_generation": expected,
                      "pointer_body": cloud.store.read_text(pointer_uri) if current else None,
                      "config_path": str(normal), "config_sha256": hashlib.sha256(prior_config).hexdigest(),
                      "fallback_manifest_sha256": _manifest_sha(active)},
            "intended": {"release_record": f"{root}/{namespace}/releases/{args.run_id}/release.json",
                         "config_sha256": hashlib.sha256(intended_config).hexdigest(),
                         "fallback_manifest_sha256": receipt["manifest"]["sha256"]},
        }
        if not args.execute:
            return {"mode": "preview", "promotion": promotion}
        directory.mkdir(parents=True, exist_ok=True)
        if backup.exists() and backup.read_bytes() != prior_config:
            raise ValueError("an older predecessor config backup differs from the current normal config")
        backup.write_bytes(prior_config)
        operation["promotion"] = promotion
    elif promotion["run_id"] != args.run_id or promotion["receipt_sha256"] != sha(args.receipt):
        raise ValueError("operation is promoting a different candidate/receipt")
    if not args.execute:
        return {"mode": "preview", "promotion": promotion, "states": _activation_states(cloud, promotion)}
    operation["phase"] = "promoting"
    save(path, operation)  # prior/intended identities are durable before any change
    states = _activation_states(cloud, promotion)
    if "foreign" in states.values():
        operation["phase"] = "activation_inconsistent"
        save(path, operation)
        raise ValueError(f"state changed outside this operation; stopping: {states}")
    if states["pointer"] == "prior":
        receipt_ref = cloud.put(f"{root}/candidates/{args.run_id}/verification_receipt.json", args.receipt)
        _publish_resumable(cloud.store, root, args.run_id, namespace, expected,
                           {**found["record"], "candidate": found["ref"], "verification_receipt": receipt_ref})
    try:
        if states["operator_config"] == "prior":  # re-checked now: no edit during cloud publication
            _write_config_from(normal, promotion["prior"]["config_sha256"], promotion["intended_config_text"].encode())
        f = promotion["fallback"]
        if states["fallback"] == "prior":
            _rename_from(promotion, "prior", f["active"], f["predecessor"])
            states["fallback"] = "midway"
        if states["fallback"] == "midway":
            _rename_from(promotion, "midway", f["staged"], f["active"])
    except ValueError:
        operation["phase"] = "activation_inconsistent"
        save(path, operation)
        raise
    after = _activation_states(cloud, promotion)
    live = _identities(shared_runtime(cfg, runner))
    reconciled = {**{name: state == "intended" for name, state in after.items()},
                  "shared_runtime": live == operation.get("intended")
                  and all(job["image"] == cfg["image_uri"] for job in live["jobs"].values())}
    promotion["reconciled"] = reconciled
    operation["phase"] = "activated" if all(reconciled.values()) else "activation_inconsistent"
    save(path, operation)
    return {"status": operation["phase"], "reconciled": reconciled, "states": after}


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
    for name in ("init", "run", "status", "download", "models", "verify", "maintenance", "promote"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--execute", action="store_true")
        if name == "init":
            command.add_argument("--baseline", default=str(ROOT / "bootstrap"))
        if name in ("status", "download", "verify", "promote"):
            command.add_argument("--run-id", required=True)
        if name == "download":
            command.add_argument("--output", required=True)
            command.add_argument("--candidate", action="store_true",
                                 help="the run's validated candidate (before promotion)")
        if name == "verify":
            command.add_argument("--download", required=True, help="directory from download --candidate")
            command.add_argument("--python", help="interpreter for the relocated replay (exact-lock env)")
            command.add_argument("--check", action="append", help="extra passed-check JSON to bind")
        if name in ("maintenance", "promote"):
            command.add_argument("--operation-id", required=True)
        if name == "maintenance":
            sub = command.add_subparsers(dest="maintenance_command", required=True)
            for action in ("hold", "status", "gate", "apply", "restore", "release"):
                item = sub.add_parser(action)
                if action == "hold":
                    item.add_argument("--admit", required=True, help="comma-separated admitted run IDs")
                if action == "apply":
                    item.add_argument("--reconciled", help="how still-active work was resolved")
        if name == "promote":
            command.add_argument("--receipt", required=True)
            command.add_argument("--normal-config", required=True)
            command.add_argument("--fallback-staged", required=True)
            command.add_argument("--fallback-active", required=True)
        if name == "run":
            for field in ("month", "cutoff", "deadline"):
                command.add_argument("--" + field, required=True)
            command.add_argument("--run-id")
            command.add_argument("--remote-update", choices=["on", "off"],
                                 help="default on: the cloud Workflow prepares this month's snapshot")
            command.add_argument("--infer", help="comma-separated systems, or none (default: both)")
            command.add_argument("--prepared-manifest", help="remote off: succeeded snapshot gs://...#generation")
            command.add_argument("--inherit", help="SYSTEM=SOURCE_DELIVERY_ID for an unscored system")
            command.add_argument("--inherit-manifest", help="gs://...#generation of the source manifest")
            command.add_argument("--inherit-archive", help="gs://...#generation of the source archive")
            command.add_argument("--publication", choices=["candidate", "current"])
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
        elif args.command == "verify":
            result = verify_candidate(args, cfg, Cloud(cfg))
        elif args.command == "maintenance":
            result = maintenance(args, cfg)
        elif args.command == "promote":
            result = promote(args, cfg)
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
