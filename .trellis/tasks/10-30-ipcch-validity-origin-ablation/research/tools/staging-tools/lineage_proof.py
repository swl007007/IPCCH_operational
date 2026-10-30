"""Lineage proof (Supervisor request): the CH-final job image 2b18cf72 is ``FROM fd921dd7`` + three modules + /app/overlay +
one ENV, and the origin-ablation context is ``FROM fd921dd7`` + three modules + /app/overlay + one ENV with the CH-final
features module byte-identical, so the two images differ only in ipcch_validity_pooled.py, dataset_input.py, the
/app/overlay metadata and IPCCH_SOURCE_COMMIT; every other file and every installed dependency is the base image's.

Evidence is read only from pinned local receipts: the CH build context (hashes checked against its context record whose
sha256 is pinned by the CH build summary/packet), the CH build receipts (SUCCESS, in-image selfcheck and overlay_check
passed as uid 65534 without network, digest/tag readback), and the new context record. No cloud call.

  lineage_proof.py --out FILE
"""
import argparse
import hashlib
import json
import os
import re
import sys

W = "/home/swl007007/projects/food-crisis-research"
CH = f"{W}/staging/ipcch-ch-validity-20261028"
CH_BUILD = f"{W}/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp3/build"
NEW = f"{W}/staging/ipcch-origin-ablation-20261030"
CH_RECORD_SHA = "2b391f4e460b026737738b86af1bf3193ed47ed4269bc99c4536044df2cca1f4"
CH_DIGEST = "sha256:2b18cf721cb09af0d1633a20087874155e8af49aa822979c0554507bcb68ccc3"
BASE = "us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/training-ipcch-validity@sha256:fd921dd7add8933024c4765e1c93c382f4f8b4f0ffb2dddc24778daac83ca939"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def context(ctx, record):
    rec = json.load(open(record))
    present = {os.path.relpath(os.path.join(r, n), ctx) for r, _, ns in os.walk(ctx) for n in ns}
    bad = sorted(p for p, s in rec["files"].items() if sha(os.path.join(ctx, p)) != s)
    lines = [l.strip() for l in open(f"{ctx}/Dockerfile") if l.strip() and not l.startswith("#")]
    instr = [l.split()[0] for l in lines]
    copies = {l.split()[2]: l.split()[1] for l in lines if l.startswith("COPY ")}
    froms = [l.split()[1] for l in lines if l.startswith("FROM ")]
    env = [l for l in lines if l.startswith("ENV ")]
    manifest = json.load(open(f"{ctx}/overlay/overlay-manifest.json"))
    return {"record_files_verified": not bad and present == set(rec["files"]), "mismatched": bad,
            "instructions": instr, "from": froms, "copies": copies, "env": env, "manifest": manifest, "record": rec}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ch_rec = f"{CH}/image-overlay-ch.context-record.json"
    summary = json.load(open(f"{CH_BUILD}/03-build-summary.json"))
    ch, new = context(f"{CH}/image-overlay-ch", ch_rec), context(f"{NEW}/image-overlay-origin", f"{NEW}/image-overlay-origin.context-record.json")
    ch_m, new_m = ch["manifest"], new["manifest"]
    allowed_instr = ["FROM", "COPY", "COPY", "COPY", "COPY", "ENV"]
    module_dst = lambda c: {dst: src for dst, src in c["copies"].items() if dst.startswith("/app/research_cloud/")}
    new_mods, ch_mods = new["record"]["module_sha256"], ch["record"]["module_sha256"]
    changed = sorted(p for p in new_mods if new_mods[p] != ch_mods.get(p))
    checks = {
        "ch_record_sha_pinned": sha(ch_rec) == CH_RECORD_SHA == summary["context_record_sha256"],
        "ch_context_files_equal_record": ch["record_files_verified"],
        "new_context_files_equal_record": new["record_files_verified"],
        "ch_build_success_and_in_image_checks": summary["status"] == "SUCCESS" and all(summary["checks"].values())
                                                 and summary["digest"] == CH_DIGEST
                                                 and open(f"{CH_BUILD}/02-digest.txt").read().strip() == CH_DIGEST,
        "same_base_by_digest": ch["from"] == new["from"] == [BASE] and ch_m["base_image"] == new_m["base_image"] == BASE,
        "only_from_copy_env_instructions": ch["instructions"] == new["instructions"] == allowed_instr,
        "same_overlaid_paths": set(module_dst(ch)) == set(module_dst(new)) == {f"/app/{p}" for p in new_mods}
                               and ch["copies"].get("/app/overlay") == new["copies"].get("/app/overlay") == "overlay",
        "features_module_identical": new_mods["research_cloud/training/ipcch_validity_features.py"]
                                     == ch_mods["research_cloud/training/ipcch_validity_features.py"],
        "changed_modules_exactly_pooled_and_dataset_input": changed == ["research_cloud/training/dataset_input.py",
                                                                         "research_cloud/training/ipcch_validity_pooled.py"],
        "same_base_context_manifest": ch_m["base_context_manifest_sha256"] == new_m["base_context_manifest_sha256"],
        "same_expected_runtime": ch_m["expected_runtime"] == new_m["expected_runtime"],
        "same_declared_base_hashes_of_overlaid_files": all(ch_m["overlaid_files"][p]["base_sha256"] == new_m["overlaid_files"][p]["base_sha256"]
                                                           for p in new_mods),
        "env_only_source_commit": all(re.fullmatch(r"ENV IPCCH_SOURCE_COMMIT=\S+", e) for e in ch["env"] + new["env"]),
        "no_dependency_install": not any(i == "RUN" for i in ch["instructions"] + new["instructions"]),
        "same_build_steps": open(f"{CH}/image-overlay-ch/cloudbuild.yaml").read().replace(ch_m["image_tag"].rsplit(":", 1)[1], "TAG")
                            == open(f"{NEW}/image-overlay-origin/cloudbuild.yaml").read().replace(new_m["image_tag"].rsplit(":", 1)[1], "TAG"),
    }
    rec = {"kind": "image_lineage_proof", "ch_final_image": f"{BASE.split('@')[0]}@{CH_DIGEST}", "base_image": BASE,
           "ch_final_build": summary["build_id"], "checks": checks, "passed": all(checks.values()),
           "differences_new_vs_ch_final": {"modules": {p: {"ch_final": ch_mods[p], "new": new_mods[p]} for p in changed},
                                           "overlay_metadata": "/app/overlay/{overlay-manifest.json, overlay-diff.patch, overlay_check.py}",
                                           "env": [ch["env"], new["env"]]},
           "identical": {"base_image_layers_and_installed_dependencies": "inherited FROM the same digest, no RUN in either",
                         "research_cloud/training/ipcch_validity_features.py": new_mods["research_cloud/training/ipcch_validity_features.py"],
                         "every_other_/app_file": "the base image's (the CH in-image overlay_check asserted derived-vs-BASE == its three "
                                                  "modules; the new in-image overlay_check asserts the same for its three)"},
           "expected_runtime": new_m["expected_runtime"],
           "why_not_FROM_ch_final": "FROM 2b18cf72 would inherit the CH /app/overlay and leave the overlay_check base (fd921dd7) "
                                    "inconsistent; building both from fd921dd7 keeps one auditable BASE and gives the same tree "
                                    "except the two changed modules"}
    json.dump(rec, open(a.out, "w"), indent=1)
    print(json.dumps({"passed": rec["passed"], "failed": [k for k, v in checks.items() if not v],
                      "changed": changed}, indent=1))
    sys.exit(0 if rec["passed"] else 1)


if __name__ == "__main__":
    main()
