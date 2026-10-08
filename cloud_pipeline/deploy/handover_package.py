"""Create and verify a closed handover archive without sealing the working tree."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

MEMBERS = (
    "LICENSE",
    "pipeline.py",
    "project.example.json",
    "requirements.lock.txt",
    "README.md",
    "QUICKSTART.md",
    "OPERATIONS.md",
    "cloud",
    "fewsnet_partitioned_rf_pipeline",
    "model_pipeline",
    "tools",
    "deploy",
    "bootstrap",
    "fallback",
)


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(name):
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or ":" in name
        or path.as_posix() != name
    ):
        raise ValueError(f"unsafe archive member: {name}")
    return path


def verify(archive):
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive members")
        for member in members:
            safe_path(member.name)
            if not member.isfile():
                raise ValueError("archive must contain only regular files")
        inventory = json.load(tar.extractfile("inventory.json"))
        entries = inventory["files"]
        expected = {entry["path"]: entry for entry in entries}
        if len(expected) != len(entries) or set(names) != set(expected) | {
            "inventory.json"
        }:
            raise ValueError("inventory membership mismatch")
        for name, entry in expected.items():
            if (
                tar.getmember(name).size != entry["size_bytes"]
                or digest(tar.extractfile(name)) != entry["sha256"]
            ):
                raise ValueError(f"archive identity mismatch: {name}")
    return inventory


def build(root, archive):
    root, archive = Path(root).resolve(), Path(archive).resolve()
    paths = []
    for relative in MEMBERS:
        source = root / relative
        if not source.exists():
            raise ValueError(f"missing handover member: {relative}")
        paths.extend(source.rglob("*") if source.is_dir() else [source])
    entries = []
    for path in sorted(paths):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"symlink in payload: {relative}")
        if path.is_dir():
            continue
        if (
            not path.is_file()
            or path == archive
            or any(part.startswith(".") for part in relative.parts)
        ):
            raise ValueError(f"unsupported payload member: {relative}")
        with path.open("rb") as stream:
            checksum = digest(stream)
        entries.append(
            {
                "path": relative.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": checksum,
            }
        )
    inventory = {"schema_version": "cloud-handover-v1", "files": entries}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "x:gz") as tar:
        for entry in entries:
            tar.add(root / entry["path"], arcname=entry["path"], recursive=False)
        data = (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode()
        info = tarfile.TarInfo("inventory.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    verify(archive)
    with archive.open("rb") as stream:
        checksum = digest(stream)
    with archive.with_name(archive.name + ".sha256").open("x") as stream:
        stream.write(f"{checksum}  {archive.name}\n")
    return inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("build")
    create.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    create.add_argument("--archive", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    result = (
        build(args.root, args.archive)
        if args.command == "build"
        else verify(args.archive)
    )
    print(json.dumps({"status": "verified", "files": len(result["files"])}))


if __name__ == "__main__":
    main()
