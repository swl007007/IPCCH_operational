"""Origin-ablation overlay build context (task 10-30): the GOSIF task's r1 design (``build_overlay_context.py``, imported
read-only from staging/ipcch-gosif-v3-20261027/tools, unchanged) and the CH task's three-module layout, from the committed
task worktree.

FROM the original immutable numerical image (by digest; control-plane 439a488), COPY the committed modules of
task/ipcch-validity-origin-ablation: research_cloud/training/ipcch_validity_features.py (the CH-final module, unchanged),
research_cloud/training/ipcch_validity_pooled.py (fit-label policy, origin contract/gates/formal path) and
research_cloud/training/dataset_input.py (origin DatasetInput name, fit-subset tags and membership check; publication
only), plus /app/overlay/{overlay-manifest.json, base-context-manifest.json, overlay_check.py}. Module bytes must equal
``git show HEAD:<path>`` of the clean worktree and the reviewed hashes below. The in-image check is the r1 CHECK plus an
assertion that the imported adapter carries the origin-ablation symbols. New tag; no dependency install, no commit.

usage: build_overlay_context_origin.py --out DIR   (DIR must not exist)
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, "/home/swl007007/projects/food-crisis-research/staging/ipcch-gosif-v3-20261027/tools")
import build_overlay_context as r1  # noqa: E402

r1.CP = "/home/swl007007/projects/food-crisis-research/control-plane-origin-ablation"     # r1.git/r1.sha read this global
TAG = "gosifv3-chvalidity-originfit-20261030"
COMMIT = "868db9f"
MODULES = {"research_cloud/training/dataset_input.py": "2b74098aacffd7d28406d3d1a20115d6e7b420a9d07783e8cc5b1cc8af990cc4",
           "research_cloud/training/ipcch_validity_features.py": "eace18fd6b6bdfd1304cbe9c50d034fc9f5fcc770b2edc14b5a109b000d9c0a6",
           "research_cloud/training/ipcch_validity_pooled.py": "d2c07d7d0d5527a8da788edf98ad0ca1b05c182e0bef920f1683c1c301c4de0f"}
CH_IMAGE = "us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/training-ipcch-validity@sha256:2b18cf721cb09af0d1633a20087874155e8af49aa822979c0554507bcb68ccc3"
OLD_ASSERT = 'if getattr(vp, "CORRECTED_INPUT_KIND", None) != "gpp_input_replacement" or vp.HPT_ARM != m["arm"]:'
NEW_ASSERT = ('if (getattr(vp, "CORRECTED_INPUT_KIND", None) != "gpp_input_replacement" or vp.HPT_ARM != m["arm"]\n'
              '        or getattr(vp, "ORIGIN_KIND", None) != "original_label_fit_ablation" or vp.FIT_LABELS != ("all", "original_only")):')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    out = ap.parse_args().out
    if os.path.exists(out):
        sys.exit(f"{out} exists")
    if r1.CHECK.count(OLD_ASSERT) != 1:
        sys.exit("r1 CHECK changed; review needed")
    check = r1.CHECK.replace(OLD_ASSERT, NEW_ASSERT)
    base_manifest = json.load(open(f"{r1.BASE_CTX}/context-manifest.json"))
    if base_manifest["control_plane_commit"] != r1.BASE_COMMIT or base_manifest["image"] != "training-ipcch-validity":
        sys.exit("BASE context manifest is not the 439a488 validity image context")
    head = r1.git("rev-parse", "HEAD").decode().strip()
    if not head.startswith(COMMIT):
        sys.exit(f"worktree HEAD {head} is not the reviewed commit {COMMIT}")
    status = r1.git("status", "--porcelain").decode().splitlines()
    if status:
        sys.exit(f"worktree is not clean: {status[:5]}")
    head_diff = r1.git("diff", "--name-only", r1.BASE_COMMIT, head, "--", "research_cloud").decode().split()
    overlaid, diffs = {}, b""
    for path, want in sorted(MODULES.items()):
        base_mod = r1.git("show", f"{r1.BASE_COMMIT}:{path}")
        if hashlib.sha256(base_mod).hexdigest() != base_manifest["files"][path]:
            sys.exit(f"git 439a488 bytes of {path} differ from the BASE manifest")
        committed = r1.git("show", f"{head}:{path}")
        if hashlib.sha256(committed).hexdigest() != want or r1.sha(f"{r1.CP}/{path}") != want:
            sys.exit(f"{path} is not the reviewed committed module")
        overlaid[path] = {"base_sha256": hashlib.sha256(base_mod).hexdigest(), "overlay_sha256": want}
        diffs += r1.git("diff", r1.BASE_COMMIT, head, "--", path)
    composite = f"{r1.BASE_COMMIT}+overlay:" + ",".join(f"{p}@sha256:{s}" for p, s in sorted(MODULES.items()))
    os.makedirs(f"{out}/overlay")
    for path in MODULES:
        shutil.copyfile(f"{r1.CP}/{path}", f"{out}/{os.path.basename(path)}")
    shutil.copyfile(f"{r1.BASE_CTX}/context-manifest.json", f"{out}/overlay/base-context-manifest.json")
    open(f"{out}/overlay/overlay_check.py", "w").write(check)
    manifest = {
        "kind": "task_code_overlay", "task": "10-30-ipcch-validity-origin-ablation", "arm": "validity_augmented_idp_202610_acledagg_lag1_uncal_hpt",
        "revision": "origin-ablation r1: features (CH-final), pooled and dataset_input (commit 7023d10; HEAD 868db9f adds tests only) on the original numerical image",
        "previous_task_image": CH_IMAGE, "source_commit": head,
        "base_image": f"{r1.REGISTRY}@{r1.BASE_DIGEST}", "base_commit": r1.BASE_COMMIT,
        "base_context_manifest_sha256": r1.sha(f"{r1.BASE_CTX}/context-manifest.json"),
        "base_context_manifest_role": "BASE: inherited /app/context-manifest.json of the base image (unchanged)",
        "current_head": head, "head_vs_base_research_cloud_changed_files": head_diff,
        "head_vs_base_note": "HEAD changes outside the three overlaid modules (HPT control/verification tooling, tests, RUNBOOK) "
                             "are NOT in the image; the image keeps the BASE tree except the overlaid modules",
        "overlaid_files": overlaid, "overlay_diff_vs_base_sha256": hashlib.sha256(diffs).hexdigest(),
        "worktree_status_at_build": status,
        "not_in_image": ["research_cloud/tests/* (tests only)"],
        "expected_runtime": r1.RUNTIME, "source_commit_env": composite, "image_tag": f"{r1.REGISTRY}:{TAG}",
    }
    json.dump(manifest, open(f"{out}/overlay/overlay-manifest.json", "w"), indent=1, sort_keys=True)
    open(f"{out}/overlay/overlay-diff.patch", "wb").write(diffs)
    open(f"{out}/Dockerfile", "w").write(
        "# Task 10-30 origin-ablation overlay: the original immutable numerical image plus THREE reviewed modules (no dependency install).\n"
        f"FROM {r1.REGISTRY}@{r1.BASE_DIGEST}\n"
        + "".join(f"COPY {os.path.basename(p)} /app/{p}\n" for p in sorted(MODULES))
        + "COPY overlay /app/overlay\n"
        f"ENV IPCCH_SOURCE_COMMIT={composite}\n")
    uri = f"{r1.REGISTRY}:{TAG}"
    open(f"{out}/cloudbuild.yaml", "w").write(
        "steps:\n"
        "- name: gcr.io/cloud-builders/docker\n"
        f"  args: [build, -t, '{uri}', .]\n"
        "- name: gcr.io/cloud-builders/docker\n"
        f"  args: [run, --rm, --user, '65534:65534', --network, none, --entrypoint, python, '{uri}',\n"
        "         -m, research_cloud.images.selfcheck, --image, training-ipcch-validity]\n"
        "- name: gcr.io/cloud-builders/docker\n"
        f"  args: [run, --rm, --user, '65534:65534', --network, none, --entrypoint, python, '{uri}', /app/overlay/overlay_check.py]\n"
        f"images: ['{uri}']\n"
        "options:\n  logging: CLOUD_LOGGING_ONLY\n"
        f"serviceAccount: {r1.BUILD_SA}\n"
        "timeout: 1800s\n")
    files = {}
    for d, _, fs in os.walk(out):
        for f in fs:
            p = os.path.join(d, f)
            files[os.path.relpath(p, out)] = r1.sha(p)
    rec = {"context": os.path.abspath(out), "files": dict(sorted(files.items())), "composite_source_commit": composite,
           "overlay_manifest_sha256": files["overlay/overlay-manifest.json"], "module_sha256": dict(sorted(MODULES.items())),
           "image_tag": uri, "source_commit": head}
    json.dump(rec, open(f"{out}.context-record.json", "w"), indent=1)
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
