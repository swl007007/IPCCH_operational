"""Verified installation of the accepted IPCCH v2 artifacts into the runtime image (task 10-30; R3, R4, AC3, AC4).

Layout under the install root (``/opt/ipcch`` in the image; the deployment config's ``installed`` paths):

    envelope/ipcch-combination-envelope-v2-accepted.json   accepted envelope (sha256 pinned by the operator)
    package/                                               accepted model package (every member re-hashed)
    handoff-bundle/                                        accepted handoff bundle (every listed member re-hashed)
    smoke-fixture/bundle/                                  isolated smoke fixture bundle (manifest fixture: true)
    deployment.json                                        the v2 deployment config (cloud.ipcch.entrypoint_v2)
    INSTALL.json                                           what was verified (identities and every member hash)

``stage`` copies the operator's verified sources into a build context in this layout and verifies the result;
``verify`` re-checks a tree (the Dockerfile runs it on ``/opt/ipcch`` offline, against the staged INSTALL.json and the
build's pinned envelope sha256), so the image cannot hold a substituted, truncated or altered artifact:

* envelope bytes = the pinned sha256; ``binding.verify_combination`` real (accepted) and smoke (fixture root) - this
  re-hashes every package member and rejects unlisted files;
* ``binding.verify_handoff``: manifest, roster and finalized acceptance entries bound by the envelope; then EVERY
  manifest-listed member is re-hashed streaming (the binding checks identity only) and no unlisted file may exist
  besides the manifest and acceptance entries;
* the smoke fixture bundle is admitted inside its fixture root (``verify_fixture_bundle``: fixture: true, never the real
  handoff) and every member re-hashed;
* the deployment config validates (``entrypoint_v2.load_config``), names exactly these installed paths, and carries no
  image digest (no self-reference: the image is built after its config).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

from cloud.ipcch import binding as bd

INSTALL_ROOT = "/opt/ipcch"
LAYOUT = {"envelope": "envelope/ipcch-combination-envelope-v2-accepted.json", "package": "package",
          "handoff": "handoff-bundle", "smoke_root": "smoke-fixture", "smoke_bundle": "smoke-fixture/bundle",
          "config": "deployment.json"}
INSTALL_MANIFEST = "INSTALL.json"
INSTALL_SCHEMA = "ipcch-v2-install-v1"
BUNDLE_SELF_FILES = {bd.HANDOFF_MANIFEST, bd.ACCEPTANCE_ENTRIES}


class InstallError(RuntimeError):
    """An artifact is not the pinned/accepted one; nothing may be installed or built."""


def expected_installed(install_root: str = INSTALL_ROOT) -> dict[str, dict[str, str]]:
    """The deployment config's ``installed`` section for this layout."""
    p = lambda key: f"{install_root.rstrip('/')}/{LAYOUT[key]}"                     # noqa: E731
    return {"real": {"envelope": p("envelope"), "package_root": p("package"), "bundle_dir": p("handoff")},
            "smoke": {"envelope": p("envelope"), "package_root": p("package"), "bundle_dir": p("smoke_bundle"),
                      "fixture_root": p("smoke_root")}}


def rehash_bundle(bundle_dir: str | Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Every manifest-listed member re-hashed (streaming); no member missing and no unlisted file."""
    root = os.path.realpath(bundle_dir)
    listed = manifest.get("files")
    if not isinstance(listed, dict) or not listed:
        raise InstallError(f"{bundle_dir}: manifest lists no files")
    total = 0
    for rel, entry in sorted(listed.items()):
        path = os.path.realpath(os.path.join(root, rel))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            raise InstallError(f"{bundle_dir}: member {rel} is missing or escapes the bundle")
        if bd.sha256_file(path) != entry.get("sha256"):
            raise InstallError(f"{bundle_dir}: member {rel} differs from its manifest sha256")
        total += os.path.getsize(path)
    present = {os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/") for d, _, names in os.walk(root)
               for n in names}
    unlisted = sorted(present - set(listed) - BUNDLE_SELF_FILES)
    if unlisted:
        raise InstallError(f"{bundle_dir}: unlisted files {unlisted[:5]}")
    return {"members": len(listed), "bytes": total,
            "member_sha256": {rel: entry["sha256"] for rel, entry in sorted(listed.items())}}


def verify_tree(root: str | Path, *, envelope_sha256: str, install_root: str = INSTALL_ROOT) -> dict[str, Any]:
    """Verify an install tree (see module docstring); returns the INSTALL manifest body."""
    root = Path(root)
    at = lambda key: str(root / LAYOUT[key])                                      # noqa: E731
    try:
        env_sha = bd.sha256_file(at("envelope"))
        if env_sha != envelope_sha256:
            raise InstallError(f"envelope sha256 {env_sha} != pinned {envelope_sha256}")
        real = bd.verify_combination(at("envelope"), at("package"), mode="real", expected_envelope_sha256=envelope_sha256)
        handoff = bd.verify_handoff(real, at("handoff"))
        smoke = bd.verify_combination(at("envelope"), at("package"), mode="smoke", fixture_root=at("smoke_root"))
        fixture = bd.verify_fixture_bundle(smoke, at("smoke_bundle"))
    except bd.BindingError as exc:
        raise InstallError(str(exc)) from exc
    if fixture["manifest_sha256"] == handoff["manifest_sha256"]:
        raise InstallError("the smoke fixture bundle is the real handoff bundle")
    handoff_members = rehash_bundle(at("handoff"), handoff["_manifest"])
    fixture_members = rehash_bundle(at("smoke_bundle"), fixture["_manifest"])
    config = _verify_config(Path(at("config")), install_root)
    return {"schema": INSTALL_SCHEMA, "install_root": install_root, "layout": dict(LAYOUT),
            "envelope": {"sha256": env_sha, "envelope_id": real.envelope_id, "status": real.status},
            "package": {"package_manifest_sha256": real.package_manifest_sha256, "combination_id": real.combination_id,
                        "feature_order_sha256": real.feature_order_sha256, "feature_count": len(real.feature_order)},
            "handoff": {k: handoff[k] for k in ("manifest_sha256", "roster_size", "roster_sha256",
                                                "acceptance_entries_sha256")} | handoff_members,
            "smoke_fixture": {k: fixture[k] for k in ("manifest_sha256", "roster_size", "roster_sha256")} | fixture_members,
            "config": config}


def _verify_config(path: Path, install_root: str) -> dict[str, Any]:
    from cloud.ipcch import entrypoint_v2

    text = path.read_text(encoding="utf-8")
    if "@sha256:" in text:
        raise InstallError("the installed deployment config must not carry an image digest (no self-reference)")
    try:
        cfg = entrypoint_v2.load_config(str(path))
    except Exception as exc:
        raise InstallError(f"deployment config invalid: {exc}") from exc
    if cfg["installed"] != expected_installed(install_root):
        raise InstallError(f"deployment config installed paths {cfg['installed']} != the install layout")
    if "fewsnet" in cfg:
        raise InstallError("the installed config omits fewsnet (its image_uri would be this image's own digest)")
    return {"sha256": bd.sha256_file(str(path)), "namespaces": cfg["namespaces"], "roots": cfg["roots"]}


def verify_against(root: str | Path, recorded: Mapping[str, Any], *, envelope_sha256: str) -> dict[str, Any]:
    """Re-verify an installed tree and require it to equal what staging recorded."""
    now = verify_tree(root, envelope_sha256=envelope_sha256, install_root=recorded["install_root"])
    if now != dict(recorded):
        changed = sorted(k for k in set(now) | set(recorded) if now.get(k) != recorded.get(k))
        raise InstallError(f"installed tree differs from the staged INSTALL manifest in {changed}")
    return now


def stage(*, out: str | Path, envelope: str, package: str, handoff: str, smoke_fixture_root: str, config: str,
          envelope_sha256: str, install_root: str = INSTALL_ROOT) -> dict[str, Any]:
    """Copy the sources into ``out`` in the install layout (``out`` must not exist), verify, write INSTALL.json."""
    out = Path(out)
    if out.exists():
        raise InstallError(f"{out} already exists; staging never reuses a directory")
    if bd.sha256_file(envelope) != envelope_sha256:                 # refuse before copying gigabytes
        raise InstallError(f"envelope {envelope} is not the pinned sha256 {envelope_sha256}")
    (out / LAYOUT["envelope"]).parent.mkdir(parents=True)
    shutil.copyfile(envelope, out / LAYOUT["envelope"])
    shutil.copytree(package, out / LAYOUT["package"])
    shutil.copytree(handoff, out / LAYOUT["handoff"])
    shutil.copytree(smoke_fixture_root, out / LAYOUT["smoke_root"])
    shutil.copyfile(config, out / LAYOUT["config"])
    body = verify_tree(out, envelope_sha256=envelope_sha256, install_root=install_root)
    (out / INSTALL_MANIFEST).write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Stage or verify the IPCCH v2 runtime installation (/opt/ipcch).")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("stage")
    for flag in ("--out", "--envelope", "--package", "--handoff", "--smoke-fixture-root", "--config",
                 "--envelope-sha256"):
        s.add_argument(flag, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--root", required=True)
    v.add_argument("--envelope-sha256", required=True)
    v.add_argument("--against", help="INSTALL.json written by stage (the installed tree must equal it)")
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            body = stage(out=args.out, envelope=args.envelope, package=args.package, handoff=args.handoff,
                         smoke_fixture_root=args.smoke_fixture_root, config=args.config,
                         envelope_sha256=args.envelope_sha256)
        elif args.against:
            body = verify_against(args.root, json.loads(Path(args.against).read_text(encoding="utf-8")),
                                  envelope_sha256=args.envelope_sha256)
        else:
            body = verify_tree(args.root, envelope_sha256=args.envelope_sha256)
    except InstallError as exc:
        print(f"install error: {exc}", file=sys.stderr)
        return 1
    summary = {k: body[k] for k in ("envelope", "package")} | {
        "handoff": {k: v for k, v in body["handoff"].items() if k != "member_sha256"},
        "smoke_fixture": {k: v for k, v in body["smoke_fixture"].items() if k != "member_sha256"},
        "config": body["config"]}
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
