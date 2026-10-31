"""CP4 step 2 readback: build record + full build log -> six-slot-runtime-evidence.json (precedent shape, task 10-21 p4).

usage: extract_evidence.py BUILD_JSON BUILD_LOG CONTEXT_FILES_SHA256 OUT_JSON
Fails (exit 1) unless every step succeeded, the pushed digest is unique, install verify / runtime imports printed their
markers and the in-image six-slot evidence matches the reference in every category.
"""

import hashlib
import json
import sys
from pathlib import Path

REPO = "us-central1-docker.pkg.dev/feisty-flames-511718-d4/monthly-delivery/runtime"
SOURCE_COMMIT = "115798f"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def marker(log: str, prefix: str) -> str:
    lines = [l for l in log.splitlines() if prefix in l]
    if len(lines) != 1:
        raise SystemExit(f"expected exactly one {prefix!r} line in the build log, got {len(lines)}")
    return lines[0][lines[0].index(prefix) + len(prefix):].strip()


def main(build_json, build_log, context_sha, out):
    build = json.loads(Path(build_json).read_text())
    log = Path(build_log).read_text(errors="replace")
    steps = [{"id": s["id"], "status": s.get("status")} for s in build["steps"]]
    images = (build.get("results") or {}).get("images") or []
    digests = {i["digest"] for i in images}
    six = json.loads(marker(log, "SIX_SLOT_EVIDENCE "))
    imports = marker(log, "RUNTIME_IMPORTS ")
    identity = marker(log, "IMAGE_IDENTITY ")
    body = {
        "build": {"id": build["id"], "status": build["status"], "create_time": build.get("createTime"),
                  "finish_time": build.get("finishTime"), "steps": steps, "images": images,
                  "source": build.get("source")},
        "source_commit": SOURCE_COMMIT,
        "image_uri": f"{REPO}@{digests.pop()}" if len(digests) == 1 else None,
        "image_identity_line": identity,
        "runtime_imports_line": imports,
        "build_log_sha256": sha(build_log),
        "context_inventory_sha256": sha(context_sha),
        "in_image_evidence": six,
    }
    ok = (body["build"]["status"] == "SUCCESS" and all(s["status"] == "SUCCESS" for s in steps)
          and body["image_uri"] is not None and all(v is True for k, v in six["matches_reference"].items()
                                                    if k != "reference_sha256"))
    body["accepted_checks"] = ok
    Path(out).write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"image_uri": body["image_uri"], "status": body["build"]["status"], "steps": steps,
                      "matches_reference": six["matches_reference"], "imports": imports, "accepted_checks": ok},
                     indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
