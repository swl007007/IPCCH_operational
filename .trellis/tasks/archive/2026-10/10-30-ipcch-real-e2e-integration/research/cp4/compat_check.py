"""CP4 step 6: real cloud compatibility check of the FEWS-only candidate scored by the NEW runtime against the current
release's delivery (fews-candidate-20261022a, scored by 487a from the same prepared snapshot and the same packages).

Required byte-identical (status "passed" only if all are): every member under scopes/ (FEWS predictions, mapping,
frozen confidence; inherited IPCCH outputs), inputs/ (assembled inference inputs from the reused snapshot), fewsnet/
and ipcch/ (packages, polygons, population references). Before comparing, the reference must be the pinned current delivery (manifest 54dd0f14…, archive f3870914…)
and both downloads must equal their own delivery manifests member by member. Members elsewhere (run/runtime identity: manifests, reports,
bundled runtime source) are listed, not judged. The JSON is passed to ``pipeline.py verify --check``.

usage: compat_check.py NEW_DOWNLOAD REFERENCE_DOWNLOAD OUT_JSON
"""

import hashlib
import json
import sys
from pathlib import Path

REQUIRED = ("scopes", "inputs", "fewsnet", "ipcch")
REFERENCE_RUN = "fews-candidate-20261022a"
# the current release's delivery as read live (live-preflight/release.json, pointer generation 1792657760445077)
REFERENCE_MANIFEST_SHA256 = "54dd0f1417f64f5848dea38abe1b77ecd8cfe859f772347a26154f043df65fc0"
REFERENCE_ARCHIVE_SHA256 = "f387091499fbe7ac31a363345cba224de816829e004bbb37f7e10d2187e936d5"
DOWNLOAD_EXTRAS = {"manifest.json", "webapp_model_bundle.tar.gz"}


def inventory(root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(block)
            out[path.relative_to(root).as_posix()] = digest.hexdigest()
    return out


def manifest_consistent(inv: dict[str, str], root: Path) -> list[str]:
    """Problems of a download against its own delivery manifest: every listed member present with its sha256, and no
    unlisted member besides the manifest and the archive."""
    listed = {f["path"]: f["sha256"] for f in json.loads((root / "manifest.json").read_text())["files"]}
    problems = [f"{p}: {inv.get(p)} != listed {h}" for p, h in listed.items() if inv.get(p) != h]
    problems += [f"{p}: unlisted" for p in sorted(set(inv) - set(listed) - DOWNLOAD_EXTRAS)]
    return problems


def main(new: Path, reference: Path, out: Path) -> dict:
    a, b = inventory(new), inventory(reference)
    # the comparison reference must be exactly the pinned current delivery, before any comparison
    if b.get("manifest.json") != REFERENCE_MANIFEST_SHA256 or b.get("webapp_model_bundle.tar.gz") != REFERENCE_ARCHIVE_SHA256:
        raise SystemExit(f"reference download is not the pinned current delivery: manifest {b.get('manifest.json')}, "
                         f"archive {b.get('webapp_model_bundle.tar.gz')}")
    for label, inv, root in (("reference", b, reference), ("new", a, new)):
        problems = manifest_consistent(inv, root)
        if problems:
            raise SystemExit(f"{label} download differs from its own manifest: {problems[:10]}")
    required = sorted(p for p in set(a) | set(b) if p.split("/")[0] in REQUIRED)
    checks = {}
    for top in REQUIRED:
        members = [p for p in required if p.split("/")[0] == top]
        checks[f"{top}_present"] = bool(members)
        checks[f"{top}_identical"] = all(a.get(p) is not None and a.get(p) == b.get(p) for p in members)
    for horizon in ("0m", "6m", "12m"):
        p = f"scopes/{horizon}/fewsnet/polygon_predictions.csv"
        checks[f"fewsnet_{horizon}_predictions_identical"] = p in a and a[p] == b.get(p)
    differing = [p for p in required if a.get(p) != b.get(p)]
    other = sorted(p for p in set(a) | set(b) if p.split("/")[0] not in REQUIRED and a.get(p) != b.get(p))
    body = {"schema": "ipcch-cp4-compat-check-v1", "reference_run": REFERENCE_RUN, "new": str(new),
            "reference_identity": {"manifest_sha256": REFERENCE_MANIFEST_SHA256, "archive_sha256": REFERENCE_ARCHIVE_SHA256,
                                   "members_match_manifest": True},
            "new_identity": {"manifest_sha256": a.get("manifest.json"),
                             "archive_sha256": a.get("webapp_model_bundle.tar.gz"), "members_match_manifest": True},
            "reference": str(reference), "status": "passed" if all(checks.values()) else "failed", "checks": checks,
            "required_members": len(required), "differing_required": differing,
            "identity_members_differing (informational)": other}
    out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return body


if __name__ == "__main__":
    result = main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print(json.dumps({k: result[k] for k in ("status", "checks", "differing_required")}, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
