"""Build and verify the self-contained October migration package (stdlib only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def safe_path(value):
    p = PurePosixPath(value)
    if (
        not value
        or p.is_absolute()
        or ".." in p.parts
        or "\\" in value
        or ":" in value
        or str(p) != value
    ):
        raise ValueError(f"unsafe package path: {value}")
    return p


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def verify(root):
    root = Path(root)
    inventory = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
    expected = inventory["files"]
    actual = set()
    for p in root.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"symlink forbidden: {p}")
        if p.is_file():
            actual.add(p.relative_to(root).as_posix())
    if actual != set(expected) | {"inventory.json"}:
        raise ValueError(
            f"inventory mismatch missing={set(expected) - actual}, unexpected={actual - set(expected) - {'inventory.json'}}"
        )
    for name, record in expected.items():
        safe_path(name)
        path = root / name
        if path.stat().st_size != record["size"] or sha256(path) != record["sha256"]:
            raise ValueError(f"checksum mismatch: {name}")
    return inventory


def extract(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as tar:
        seen = set()
        for member in tar:
            safe_path(member.name)
            if not member.isfile() or member.name in seen:
                raise ValueError(f"unsafe/duplicate archive member: {member.name}")
            seen.add(member.name)
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
    return verify(destination)


def build(args):
    repo, assets, cache, bundle = map(
        Path, (args.repo, args.assets, args.cache, args.bundle)
    )
    output = Path(args.output)
    archive = output.with_suffix(".tar.gz")
    if output.exists() or archive.exists():
        raise FileExistsError("package destination or archive already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=output.name + ".staging-", dir=output.parent))
    mapping = {}
    request = json.loads((cache / "run_manifest.json").read_text(encoding="utf-8"))
    prepared = json.loads(
        (cache / "prepared_manifest.json").read_text(encoding="utf-8")
    )
    manifests = list((cache / "downloads").rglob("debug-smoke-20261008a.json"))
    if len(manifests) != 1:
        raise ValueError("exact consumed inputs manifest is required")
    consumed = json.loads(manifests[0].read_text(encoding="utf-8"))["files"]

    def copy(source, member, expected=None):
        safe_path(member)
        source = Path(source)
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing/nonregular input: {source}")
        target = stage / member
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError(f"duplicate package member: {member}")
        shutil.copyfile(source, target)
        digest = sha256(target)
        if expected and digest != expected:
            raise ValueError(f"consumed checksum mismatch: {source}")
        mapping[member] = {"source": str(source), "sha256": digest}

    for package in (
        "cloud",
        "fewsnet_partitioned_rf_pipeline",
        "model_pipeline",
        "tools",
    ):
        files = [
            p
            for p in (repo / package).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix in {".py", ".json", ".csv"}
        ]
        if not files:
            raise ValueError(f"missing runtime package: {package}")
        for source in files:
            copy(source, "runtime/" + source.relative_to(repo).as_posix())
    deploy = repo / "deploy/october_delivery"
    for name in ("Dockerfile", "requirements.lock.txt"):
        copy(deploy / name, "runtime/" + name)
    for name in (
        "migration_package.py",
        "migration_destination.py",
        "deploy_delivery.sh",
        "workflow.yaml",
    ):
        copy(deploy / name, "deploy/" + name)
    copy(deploy / "MIGRATION.md", "README.md")
    copy(deploy / "config.env.example", "config.env.example")
    for system in ("fewsnet", "ipcch"):
        for name in ("geometry", "roster"):
            filename = name + (".geojson" if name == "geometry" else ".csv")
            copy(
                assets / system / filename,
                f"assets/{system}/{filename}",
                prepared["systems"][system][name]["sha256"],
            )
        for family, ref in prepared["systems"][system]["history"].items():
            copy(
                assets / system / "history" / (family + ".csv"),
                f"assets/{system}/history/{family}.csv",
                ref["sha256"],
            )
        panel = (
            "fewsnet_refreshed_raw.csv" if system == "fewsnet" else "ipcch_panel.csv"
        )
        matches = list((cache / "downloads").rglob(panel))
        if len(matches) != 1:
            raise ValueError(f"exact consumed panel missing: {panel}")
        copy(
            matches[0],
            f"assets/{system}/history_panel.csv",
            request["assets"][system]["history_panel"]["sha256"],
        )
        copy(
            bundle / system / "country_population_reference.csv",
            f"assets/{system}/population.csv",
            request["assets"][system]["population"]["sha256"],
        )
        prefix = system + "_package/"
        for name, ref in consumed.items():
            if name.startswith(prefix):
                relative = name[len(prefix) :]
                copy(
                    bundle / system / "model_package" / relative,
                    f"models/{system}/{relative}",
                    ref["sha256"],
                )
    copy(
        args.fixed_panel,
        "assets/ipcch/fixed_features.csv",
        request["assets"]["ipcch"]["fixed_features"]["sha256"],
    )
    for family in ("wfp", "acled"):
        copy(
            cache / f"retained_{family}.csv",
            f"assets/retained_{family}.csv",
            request[family]["retained_snapshot"]["sha256"],
        )
    for folder in ("inputs", "scopes"):
        for source in (bundle / folder).rglob("*"):
            if source.is_file():
                copy(source, "reference/" + source.relative_to(bundle).as_posix())
    for name in (
        "manifest.json",
        "bundle_manifest.json",
        "model_inventory.json",
        "reports/diagnostic_availability.csv",
    ):
        copy(bundle / name, "reference/" + name)
    # Old object references are evidence only; destination helpers never submit this document.
    copy(cache / "run_manifest.json", "reference/source_request.json")
    write_json(stage / "source-map.json", mapping)
    files = {
        p.relative_to(stage).as_posix(): {"size": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(stage.rglob("*"))
        if p.is_file()
    }
    write_json(
        stage / "inventory.json",
        {"schema_version": "october-migration-v1", "files": files},
    )
    verify(stage)
    temp_archive = stage.parent / (stage.name + ".tar.gz")
    with tarfile.open(temp_archive, "w:gz") as tar:
        for name in sorted(set(files) | {"inventory.json"}):
            tar.add(stage / name, arcname=name, recursive=False)
    # Stream-verify every archived member without creating a second full payload copy.
    with tarfile.open(temp_archive, "r:gz") as tar:
        members = set()
        for member in tar:
            safe_path(member.name)
            if not member.isfile() or member.name in members:
                raise ValueError("invalid archive member")
            members.add(member.name)
            expected = files.get(
                member.name,
                {
                    "size": (stage / "inventory.json").stat().st_size,
                    "sha256": sha256(stage / "inventory.json"),
                },
            )
            with tar.extractfile(member) as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if member.size != expected["size"] or digest != expected["sha256"]:
                raise ValueError("archive checksum mismatch")
        if members != set(files) | {"inventory.json"}:
            raise ValueError("archive inventory mismatch")
    stage.rename(output)
    temp_archive.rename(archive)
    return {
        "package": str(output),
        "archive": str(archive),
        "archive_sha256": sha256(archive),
        "files": len(files),
        "bytes": sum(row["size"] for row in files.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build")
    for flag in ("repo", "assets", "cache", "bundle", "fixed-panel", "output"):
        p.add_argument("--" + flag, required=True)
    p = sub.add_parser("verify")
    p.add_argument("package")
    p = sub.add_parser("extract")
    p.add_argument("archive")
    p.add_argument("destination")
    args = parser.parse_args()
    if args.command == "build":
        result = build(args)
    elif args.command == "verify":
        result = {"verified_files": len(verify(args.package)["files"])}
    else:
        result = {
            "verified_files": len(extract(args.archive, args.destination)["files"])
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
