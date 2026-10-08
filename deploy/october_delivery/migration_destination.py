"""Destination uploads and requests; dry-run is the default and never opens a cloud client."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
from migration_package import sha256, verify, write_json  # noqa: E402


def config(environ):
    names = (
        "PROJECT",
        "REGION",
        "BUCKET",
        "REQUEST_BUCKET",
        "SA",
        "WORKFLOW_SA",
        "NAMESPACE",
        "IMAGE",
    )
    result = {name: environ.get(name, "") for name in names}
    if any(not value or "REPLACE" in value for value in result.values()):
        raise ValueError(
            "fill all destination environment variables from config.env.example"
        )
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", result["IMAGE"]):
        raise ValueError("IMAGE must be digest-pinned")
    for key in ("BUCKET", "REQUEST_BUCKET"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", result[key]):
            raise ValueError(f"invalid {key}")
    return result


def upload_file(client, bucket, name, path):
    blob = client.bucket(bucket).blob(name)
    blob.upload_from_filename(str(path), if_generation_match=0)
    if (
        not blob.generation
        or not str(blob.generation).isdigit()
        or int(blob.generation) <= 0
    ):
        raise ValueError("upload returned no positive generation")
    return {
        "uri": f"gs://{bucket}/{name}",
        "generation": str(blob.generation),
        "sha256": sha256(path),
    }


def check_refs(root, cfg, refs, inventory):
    expected = {
        name for name in inventory["files"] if name.startswith(("assets/", "models/"))
    }
    if set(refs) != expected:
        raise ValueError("upload receipt does not cover the exact payload")
    for name, ref in refs.items():
        if (
            not ref["uri"].startswith(f"gs://{cfg['BUCKET']}/")
            or not re.fullmatch(r"[1-9][0-9]*", ref["generation"])
            or ref["sha256"] != inventory["files"][name]["sha256"]
        ):
            raise ValueError(f"invalid destination receipt: {name}")


def prepare_request(cfg, refs, args):
    from cloud.batch.remote_sources import EXTRACTION_CONTRACT_VERSION, SYSTEM_FAMILIES
    from cloud.orchestrator.prepare import (
        PREPARE_SCHEMA_VERSION,
        validate_prepare_request,
    )

    body = {
        "schema_version": PREPARE_SCHEMA_VERSION,
        "prepare_id": args.prepare_id,
        "origin_month": args.origin,
        "cutoff_utc": args.cutoff,
        "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
        "operator": args.operator,
        "systems": {
            s: {
                "geometry": refs[f"assets/{s}/geometry.geojson"],
                "roster": refs[f"assets/{s}/roster.csv"],
                "history": {
                    f: refs[f"assets/{s}/history/{f}.csv"] for f in SYSTEM_FAMILIES[s]
                },
            }
            for s in ("fewsnet", "ipcch")
        },
    }
    uri = (
        f"gs://{cfg['BUCKET']}/prepare_requests/{args.prepare_id}/prepare_request.json"
    )
    raw = json.dumps(body, sort_keys=True).encode()
    # Generation 1 is only the structural validator's placeholder; it is never emitted as an object ref.
    validate_prepare_request(
        body,
        request_uri=uri,
        request_generation="1",
        request_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return body, uri


def delivery_request(root, cfg, refs, args, client):
    from cloud.orchestrator import delivery_job as dj, delivery_manifest as dm

    receipt = json.loads(Path(args.runtime_verification).read_text(encoding="utf-8"))
    expected = {
        "image_uri": cfg["IMAGE"],
        "requirements_lock_sha256": sha256(root / "runtime/requirements.lock.txt"),
        "inventory_sha256": sha256(root / "inventory.json"),
        "status": "passed",
    }
    if (
        any(receipt.get(k) != v for k, v in expected.items())
        or not receipt.get("operator")
        or not receipt.get("evidence")
    ):
        raise ValueError(
            "operator-confirmed runtime equivalence receipt required for this exact image/package"
        )
    prepared_ref = json.loads(Path(args.prepared_ref).read_text(encoding="utf-8"))
    if not prepared_ref["uri"].startswith(f"gs://{cfg['BUCKET']}/prepared/"):
        raise ValueError("prepared snapshot must belong to destination bucket")
    downloader = dj.PinnedDownloader(client, Path(args.work) / "downloads")
    prepared = json.loads(downloader.fetch(prepared_ref).read_text(encoding="utf-8"))
    if (
        prepared.get("status") != "succeeded"
        or prepared["origin_month"] != args.origin
        or prepared["prepare_id"] != args.prepare_id
    ):
        raise ValueError("destination preparation not succeeded for this origin/id")

    def put(name, body):
        path = Path(args.work) / name
        write_json(path, body)
        return upload_file(
            client, cfg["BUCKET"], f"migration/{args.run_id}/{name}", path
        )

    runtime = {
        "image_uri": cfg["IMAGE"],
        "environment_manifest": put(
            "environment.json",
            {
                "image_uri": cfg["IMAGE"],
                "requirements_lock_sha256": expected["requirements_lock_sha256"],
            },
        ),
    }
    source = json.loads(
        (root / "reference/source_request.json").read_text(encoding="utf-8")
    )
    models = []
    for old in source["models"]:
        s, h = old["system"], old["horizon_months"]
        prefix = f"models/{s}/{h}m/" if s == "fewsnet" else "models/ipcch/"
        members = [
            {"path": name[len(prefix) :], **ref}
            for name, ref in sorted(refs.items())
            if name.startswith(prefix)
            and (
                s == "fewsnet"
                or "/" not in name[len(prefix) :]
                or name[len(prefix) :].startswith(f"scope_{h}m/")
            )
        ]
        model = {
            key: old[key]
            for key in (
                "system",
                "horizon_months",
                "package_id",
                "feature_schema_sha256",
            )
        }
        manifest = put(
            f"{s}_{h}m_package.json",
            {
                "schema_version": dj.PACKAGE_MANIFEST_SCHEMA,
                **{k: model[k] for k in ("system", "horizon_months", "package_id")},
                "files": members,
            },
        )
        model["package_manifest"] = manifest
        model["acceptance_report"] = put(
            f"{s}_{h}m_acceptance.json",
            {
                "schema_version": dj.ACCEPTANCE_REPORT_SCHEMA,
                **{
                    k: model[k]
                    for k in (
                        "system",
                        "horizon_months",
                        "package_id",
                        "feature_schema_sha256",
                    )
                },
                "status": "accepted",
                "package_manifest_sha256": manifest["sha256"],
                "runtime": {
                    "image_uri": cfg["IMAGE"],
                    "environment_manifest_sha256": runtime["environment_manifest"][
                        "sha256"
                    ],
                },
                "evidence": receipt,
            },
        )
        models.append(model)
    body = {
        key: source[key]
        for key in (
            "schema_version",
            "systems",
            "horizons_months",
            "contracts",
            "diagnostics",
        )
    }
    body.update(
        run_id=args.run_id,
        origin_month=args.origin,
        models=models,
        runtime=runtime,
        prepared_snapshot={
            "prepare_id": args.prepare_id,
            "origin_month": args.origin,
            "manifest": prepared_ref,
        },
        operator=args.operator,
        prepared_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        release={
            "namespace": cfg["NAMESPACE"],
            "expected_pointer_generation": args.pointer_generation,
        },
    )
    body["assets"] = {
        s: {
            field: refs[f"assets/{s}/{filename}"]
            for field, filename in {
                "geometry": "geometry.geojson",
                "roster": "roster.csv",
                "population": "population.csv",
                "country_reference": "population.csv",
                "history_panel": "history_panel.csv",
            }.items()
        }
        for s in ("fewsnet", "ipcch")
    }
    body["assets"]["ipcch"]["fixed_features"] = refs["assets/ipcch/fixed_features.csv"]
    for family in ("wfp", "acled"):
        body[family] = {
            "action": "keep",
            "converter_contract": source[family]["converter_contract"],
            "retained_snapshot": refs[f"assets/retained_{family}.csv"],
        }
    uri = f"gs://{cfg['REQUEST_BUCKET']}/requests/{args.run_id}/run_manifest.json"
    dm.validate_delivery_request(
        body,
        request_uri=uri,
        request_generation="1",
        expected_release_namespace=cfg["NAMESPACE"],
    )
    return body, uri


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("upload", "prepare", "delivery"))
    parser.add_argument(
        "--package", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform create-only uploads; default prints actions only",
    )
    parser.add_argument(
        "--work",
        required=True,
        help="external working directory; never place inside the package",
    )
    parser.add_argument("--refs")
    parser.add_argument("--prepare-id")
    parser.add_argument("--run-id")
    parser.add_argument("--origin", default="2026-10")
    parser.add_argument("--cutoff")
    parser.add_argument("--operator")
    parser.add_argument("--runtime-verification")
    parser.add_argument("--prepared-ref")
    parser.add_argument("--pointer-generation", default="0")
    args = parser.parse_args()
    root = args.package.resolve()
    inventory = verify(root)
    cfg = config(os.environ)
    work = Path(args.work).resolve()
    if work == root or root in work.parents:
        raise ValueError("working directory must be outside the sealed package")
    payload = sorted(
        name for name in inventory["files"] if name.startswith(("assets/", "models/"))
    )
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "command": args.command,
                    "payload_files": len(payload),
                    "destination": f"gs://{cfg['BUCKET']}/migration/",
                    "image": cfg["IMAGE"],
                    "acceptance": "requires destination runtime verification; no objects uploaded",
                },
                indent=2,
            )
        )
        return
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root / "runtime"))
    if args.command == "upload" and not re.fullmatch(
        r"[a-z0-9][a-z0-9._-]{2,62}", args.run_id or ""
    ):
        raise ValueError("upload requires a unique --run-id")
    if args.command != "upload" and not all(
        (args.refs, args.prepare_id, args.operator)
    ):
        raise ValueError("requests require --refs --prepare-id --operator")
    if args.command == "prepare" and not args.cutoff:
        raise ValueError("prepare requires --cutoff UTC timestamp")
    if args.command == "delivery" and not all(
        (args.run_id, args.runtime_verification, args.prepared_ref)
    ):
        raise ValueError(
            "delivery requires --run-id --runtime-verification --prepared-ref"
        )
    from google.cloud import storage

    client = storage.Client(project=cfg["PROJECT"])
    work.mkdir(parents=True, exist_ok=False)
    if args.command == "upload":
        refs = {
            name: upload_file(
                client, cfg["BUCKET"], f"migration/{args.run_id}/{name}", root / name
            )
            for name in payload
        }
        write_json(work / "uploaded_refs.json", refs)
    else:
        refs = json.loads(Path(args.refs).read_text(encoding="utf-8"))
        check_refs(root, cfg, refs, inventory)
        body, uri = (
            prepare_request(cfg, refs, args)
            if args.command == "prepare"
            else delivery_request(root, cfg, refs, args, client)
        )
        path = work / (
            "prepare_request.json" if args.command == "prepare" else "run_manifest.json"
        )
        write_json(path, body)
        if args.command == "prepare":
            bucket, name = uri[5:].split("/", 1)
            write_json(
                work / "prepare_request_ref.json",
                upload_file(client, bucket, name, path),
            )
        else:
            print(
                json.dumps(
                    {
                        "request_local": str(path),
                        "request_uri": uri,
                        "sha256": sha256(path),
                        "submitted": False,
                    }
                )
            )


if __name__ == "__main__":
    main()
