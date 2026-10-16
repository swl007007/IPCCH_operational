"""Assemble a pinned Cloud Build context for one research image (service, training-fews, training-ipcch, and the
historical replay images replay-x320 / replay-forecast-x320).

The context holds exactly: the image's ``Dockerfile`` and ``requirements.lock.txt``; ``research_cloud`` exported with
``git archive`` from the committed control-plane HEAD (refused when ``research_cloud`` has uncommitted changes); for
training images, the scientific source - FEWS from ``git archive`` of the clean Food_Crisis_Cluster commit
``FEWS_COMMIT``, IPCCH from P6's ``source_code`` MLflow artifact (run ``P6_RUN``) - and ``context-manifest.json`` with the
commits, the base image digest from the Dockerfile and the sha256 of every other context file. Build with the
control-plane commit as ``SOURCE_COMMIT`` so the running image reports it.

It also writes ``cloudbuild.yaml``: build (``SOURCE_COMMIT`` = the commit), then ``selfcheck`` inside the built image as
the runtime user (UID 65534, no network), and only then push (``images:``), as the given build service account.

  python -m research_cloud.images.context --image training-fews --out DIR [--image-uri URI --build-sa EMAIL]
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.dirname(os.path.dirname(HERE))
SOURCES = "/home/swl007007/projects/food-crisis-research/sources"
FEWS_REPO, FEWS_COMMIT, FEWS_DIR = f"{SOURCES}/Food_Crisis_Cluster", "6c1ebf72f36651ad1c229508f3388e796e710f3c", "FEWSNETGeoXGBExperiment"
P6_RUN = "bdbafe393d694439a1c35ccec4d5816a"
P6_SOURCE = f"/home/swl007007/.local/share/ipcch-mlflow/artifacts/1/{P6_RUN}/artifacts/source_code/IPCCHGeoXGBExperiment"
IMAGES = ("service", "training-fews", "training-ipcch", "replay-x320", "replay-forecast-x320")


class ContextError(Exception):
    pass


def git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)
    return out.stdout if binary else out.stdout.decode().strip()


def extract(archive, dest):
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree(root):
    out = {}
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(dirpath, name)
            out[os.path.relpath(path, root)] = sha256(path)
    return out


def cloudbuild(image, commit, image_uri, build_sa):
    lines = ["steps:",
             "- name: gcr.io/cloud-builders/docker",
             f"  args: [build, --build-arg, SOURCE_COMMIT={commit}, -t, '{image_uri}', .]",
             "- name: gcr.io/cloud-builders/docker",
             f"  args: [run, --rm, --user, '65534:65534', --network, none, --entrypoint, python, '{image_uri}',",
             f"         -m, research_cloud.images.selfcheck, --image, {image}]",
             f"images: ['{image_uri}']",
             "options:", "  logging: CLOUD_LOGGING_ONLY"]
    if build_sa:
        lines.append(f"serviceAccount: projects/{build_sa.split('@')[1].split('.')[0]}/serviceAccounts/{build_sa}")
    return "\n".join(lines) + "\n"


def build(image, out, image_uri=None, build_sa=None):
    if image not in IMAGES:
        raise ContextError(f"unknown image {image}")
    if os.path.exists(out):
        raise ContextError(f"{out} exists")
    dirty = git(CONTROL, "status", "--porcelain", "--", "research_cloud")
    if dirty:
        raise ContextError(f"research_cloud has uncommitted changes:\n{dirty}")
    commit = git(CONTROL, "rev-parse", "HEAD")
    os.makedirs(out)
    for name in ("Dockerfile", "requirements.lock.txt"):
        shutil.copy2(os.path.join(HERE, image, name), os.path.join(out, name))
    extract(git(CONTROL, "archive", "--format=tar", commit, "research_cloud", binary=True), out)
    sources = {}
    if image == "training-fews":
        if git(FEWS_REPO, "rev-parse", "HEAD") != FEWS_COMMIT or git(FEWS_REPO, "status", "--porcelain", "--", FEWS_DIR):
            raise ContextError(f"{FEWS_REPO} is not the clean pinned commit {FEWS_COMMIT}")
        os.makedirs(os.path.join(out, "sources"))
        extract(git(FEWS_REPO, "archive", "--format=tar", FEWS_COMMIT, FEWS_DIR, binary=True), os.path.join(out, "sources"))
        sources[FEWS_DIR] = {"kind": "git", "repo": "Food_Crisis_Cluster", "commit": FEWS_COMMIT}
    elif image == "training-ipcch":
        shutil.copytree(P6_SOURCE, os.path.join(out, "sources", "IPCCHGeoXGBExperiment"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        sources["IPCCHGeoXGBExperiment"] = {"kind": "mlflow_artifact", "run_id": P6_RUN, "artifact": "source_code/IPCCHGeoXGBExperiment",
                                            "files": tree(os.path.join(out, "sources", "IPCCHGeoXGBExperiment"))}
    base = re.search(r"^FROM (\S+)", open(os.path.join(out, "Dockerfile")).read(), re.M).group(1)
    if "@sha256:" not in base:
        raise ContextError("the Dockerfile base image is not pinned by digest")
    files = tree(out)
    manifest = {"image": image, "control_plane_commit": commit, "base_image": base, "sources": sources,
                "lock_sha256": files["requirements.lock.txt"], "dockerfile_sha256": files["Dockerfile"],
                "files": files, "build_arg": {"SOURCE_COMMIT": commit}}
    with open(os.path.join(out, "context-manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    if image_uri:   # outside the hashed file list: it names where the context is built to, not what it contains
        with open(os.path.join(out, "cloudbuild.yaml"), "w") as f:
            f.write(cloudbuild(image, commit, image_uri, build_sa))
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, choices=IMAGES)
    ap.add_argument("--out", required=True)
    ap.add_argument("--image-uri")
    ap.add_argument("--build-sa")
    args = ap.parse_args(argv)
    m = build(args.image, args.out, args.image_uri, args.build_sa)
    print(json.dumps({"image": m["image"], "commit": m["control_plane_commit"][:12], "files": len(m["files"]),
                      "lock_sha256": m["lock_sha256"][:16], "context_manifest_sha256": sha256(os.path.join(args.out, "context-manifest.json"))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
