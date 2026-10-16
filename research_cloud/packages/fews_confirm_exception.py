"""Accepted-exception record for FEWS NET ``confirm-onset-v1`` (user ruling 2026-10-16; prd.md, design.md).

The full gated S0/S3 system cannot be replayed: its 7 distinct local continuation boosters (9 gate entries) were never
written (``keep_boosters=False``) and were not found by exact content; they route 2,446 of 11,436 system rows. The
user accepted this as a narrow incomplete historical exception: preserve every extant material, label full-system
replay unavailable, and provide the retained pooled/global models' download and replay under their own identity - no
substitution of global predictions for the missing rows and no new training.

This builds a weightless record directory (no package, nothing to replay) that states exactly that and binds by
sha256: the discovery receipt and its machine-readable targets; the preserved run archive (frozen preservation
manifest and the GCS transfer receipts); and the two pooled packages (their package.json and replay receipts), which
are left unchanged. The existing packages, receipts and archive are only read.

  python -m research_cloud.packages.fews_confirm_exception --out DIR [inputs, see main()]
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build(out, receipt, targets, preservation, transfer_receipts, packages, replay_receipts):
    os.makedirs(out, exist_ok=False)
    shutil.copyfile(receipt, os.path.join(out, "confirm-onset-missing-local-boosters-receipt.md"))
    shutil.copyfile(targets, os.path.join(out, "confirm_onset_local_targets.json"))
    t = json.load(open(targets))
    m = json.load(open(preservation))
    rec = [json.loads(line) for line in open(transfer_receipts) if line.strip()]
    if len(rec) != m["totals"]["files"] or any(not r["status"].startswith("verified") for r in rec):
        raise SystemExit("the run archive is not completely transferred and verified; refusing")
    pooled = {}
    for name, report in zip(packages, replay_receipts):
        pj = os.path.join(name, "package.json")
        meta = json.load(open(pj))
        rep = json.load(open(report))
        sha = sha256_file(pj)
        if meta.get("status") != "complete" or rep.get("package_json_sha256") != sha or rep.get("passed") is not True:
            raise SystemExit(f"{name}: pooled package not complete or its replay receipt does not bind/pass; refusing")
        pooled[os.path.basename(name)] = {"package_json_sha256": sha, "arm": meta.get("arm"), "status": meta["status"],
                                          "replay_receipt": os.path.basename(report), "replay_receipt_sha256": sha256_file(report),
                                          "replay_rows": rep.get("rows")}
    record = {
        "run": "FEWSNET/confirm-onset-v1",
        "status": "full_system_replay_unavailable_accepted_exception",
        "ruling": "user, 2026-10-16: accept as a narrow incomplete historical exception; preserve all extant material; "
                  "label full-system replay unavailable; provide the pooled/global models' download and replay under "
                  "their own identity; no substitution, no new training (prd.md / design.md, registered commit 473467b)",
        "missing": {"unique_local_boosters": 7, "gate_entries": 9, "system_rows_total": 11436,
                    "system_rows_local_routed_unreplayable": 2446,
                    "producer_cause": "run_confirm.py:393 save_fold(..., keep_boosters=False)",
                    "search": "exact sha256 over 36,305 .ubj in /mnt/c/Users/swl00/geoxgb_runs and /home/swl007007; "
                              "0 of 7 found; bounded scope, not a claim of global absence"},
        "discovery_receipt": {"file": "confirm-onset-missing-local-boosters-receipt.md", "sha256": sha256_file(receipt)},
        "local_targets": {"file": "confirm_onset_local_targets.json", "sha256": sha256_file(targets),
                          "entries": len(t) if isinstance(t, list) else len(t.get("entries", t))},
        "preserved_archive": {"gcs_prefix": "gs://food-crisis-modeling-enso-research-inputs/fews-runs/confirm-onset-v1/",
                              "files": m["totals"]["files"], "bytes": m["totals"]["bytes"],
                              "preservation_manifest_sha256": sha256_file(preservation),
                              "transfer_receipts_sha256": sha256_file(transfer_receipts)},
        "extant_global_models": {"note": "the retained pooled/global path, packaged and replayed under its own identity; "
                                         "not a substitute for the system's local-routed rows", "packages": pooled},
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with open(os.path.join(out, "exception.json"), "w") as f:
        json.dump(record, f, indent=1)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--out", "--receipt", "--targets", "--preservation", "--transfer-receipts"):
        ap.add_argument(k, required=True)
    ap.add_argument("--package", action="append", required=True)
    ap.add_argument("--replay-receipt", action="append", required=True)
    args = ap.parse_args(argv)
    if len(args.package) != len(args.replay_receipt):
        raise SystemExit("one replay receipt per package")
    r = build(args.out, args.receipt, args.targets, args.preservation, args.transfer_receipts, args.package,
              args.replay_receipt)
    print(json.dumps({"status": r["status"], "pooled": list(r["extant_global_models"]["packages"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
