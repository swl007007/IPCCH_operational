"""Prepare the IPCCH CP2 acceptance publication packet without modifying the candidate originals (task 10-29; R45, R51).

Acceptance is an explicit research-side act: the acceptor and date are inputs. This tool

1. checks the source handoff bundle (``handoff_manifest.json`` sha256 must equal ``--expect-manifest-sha256``) and its
   draft ``acceptance_entries.json`` (exactly the runtime files at their manifest sha256);
2. creates a NEW bundle directory (must not exist): every manifest-listed file and ``handoff_manifest.json`` are
   hard-linked (copied across devices) byte-for-byte, and a finalized ``acceptance_entries.json`` (the draft entries
   with ``acceptor``/``accepted_at`` filled) is written fresh, so the original draft file is untouched;
3. writes an ACCEPTED envelope (create-only, ``--envelope-version``) binding the package manifest, the unchanged
   handoff manifest and the finalized entries digest;
4. verifies the result exactly as real mode will (``verify_combination(mode="real")`` + ``verify_handoff``).

The package directory and the source bundle are only read.

    python tools/ipcch_finalize_acceptance.py --package PKG --bundle OUT_R5 --expect-manifest-sha256 SHA \\
        --out-bundle OUT_R5_ACCEPTED_V1 --envelope ENVELOPE_V2.json --envelope-version 2 \\
        --acceptor "<name>" --accepted-at YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloud.ipcch import binding as bd  # noqa: E402


def _link(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def finalize(package: str, bundle: str, expect_manifest_sha256: str, out_bundle: str, envelope_path: str,
             envelope_version: int, acceptor: str, accepted_at: str) -> dict:
    manifest_path = os.path.join(bundle, bd.HANDOFF_MANIFEST)
    if bd.sha256_file(manifest_path) != expect_manifest_sha256:
        raise bd.BindingError(f"{manifest_path} is not the expected handoff manifest {expect_manifest_sha256}")
    if os.path.exists(out_bundle) or os.path.exists(envelope_path):
        raise bd.BindingError("output bundle and envelope must not exist (versions are never overwritten)")
    manifest = json.load(open(manifest_path))
    draft = json.load(open(os.path.join(bundle, bd.ACCEPTANCE_ENTRIES)))
    runtime = {rel: v["sha256"] for rel, v in manifest["files"].items() if not rel.startswith("audit/")}
    if sorted(e["name"] for e in draft) != sorted(runtime) or any(e["sha256"] != runtime[e["name"]] for e in draft):
        raise bd.BindingError("draft acceptance entries do not list exactly the runtime files at their manifest sha256")
    os.makedirs(out_bundle)
    for rel in [*manifest["files"], bd.HANDOFF_MANIFEST]:
        _link(os.path.join(bundle, rel), os.path.join(out_bundle, rel))
    finalized = [{**e, "acceptor": acceptor, "accepted_at": accepted_at} for e in draft]
    with open(os.path.join(out_bundle, bd.ACCEPTANCE_ENTRIES), "x") as f:
        json.dump(finalized, f, indent=1)
        f.write("\n")
    env = bd.build_envelope(package, out_bundle, envelope_version=envelope_version,
                            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            acceptor=acceptor, accepted_at=accepted_at)
    env_sha = bd.write_envelope(env, envelope_path)
    binding = bd.verify_combination(envelope_path, package, mode="real", expected_envelope_sha256=env_sha)
    ident = bd.verify_handoff(binding, out_bundle)
    return {"out_bundle": out_bundle, "envelope": envelope_path, "envelope_sha256": env_sha,
            "envelope_id": env["envelope_id"], "status": env["status"], "acceptor": acceptor, "accepted_at": accepted_at,
            "package_manifest_sha256": binding.package_manifest_sha256, "feature_order_sha256": binding.feature_order_sha256,
            "handoff_manifest_sha256": ident["manifest_sha256"], "roster_sha256": ident["roster_sha256"],
            "roster_size": ident["roster_size"], "acceptance_entries_sha256": ident["acceptance_entries_sha256"],
            "source_draft_entries_sha256": bd.sha256_file(os.path.join(bundle, bd.ACCEPTANCE_ENTRIES)),
            "entries": len(finalized)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("--package", "--bundle", "--expect-manifest-sha256", "--out-bundle", "--envelope", "--acceptor",
                 "--accepted-at"):
        p.add_argument(name, required=True)
    p.add_argument("--envelope-version", type=int, required=True)
    a = p.parse_args(argv)
    print(json.dumps(finalize(a.package, a.bundle, a.expect_manifest_sha256, a.out_bundle, a.envelope,
                              a.envelope_version, a.acceptor, a.accepted_at), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
