"""Publish the 223 historical packages through MLflow: one run per package in experiment ``historical-packages``.

Downloads must work with MLflow Basic auth only (``mlflow.artifacts.download_artifacts`` through the service's
artifact proxy), so each package must sit under a real run's ``artifact_uri``, where MLflow's artifact authorization
resolves the experiment from the proxy path. For every package (idempotent; an existing run is found by its
``package.name`` tag):

1. a run is created (temporary migration admin) with tags: package name, current ``package.json`` sha256, content
   sha256, family, status, the replay image by digest, the original ``gs://…/packages/<name>/`` prefix and the source
   links - registry ``name|version`` and source run ids from the registry ledger (only when the ledger's package.json
   sha256 equals the current one), else the FEWS run / pop-v1 run root recorded in the package itself;
2. every file of ``package.json`` plus ``package.json`` itself is copied **server-side** (GCS rewrite, same bucket,
   create-only ``if_generation_match=0``) from ``packages/<name>/<rel>`` to ``mlflow-artifacts/<run artifact
   path>/package/<rel>``; the copy's md5/crc32c must equal the source object's and the transfer receipt's local
   hashes. Receipts are JSONL;
3. the run is tagged with the copied file count and ended FINISHED.
Every invocation re-reads each source (must still be the transferred generation and hashes; the copy is made from that
generation) and each destination; receipts are never trusted on their own. ``--verify`` is the read-only final
reconciliation used for acceptance: one FINISHED run per package with the expected tags, every source and destination
re-read against the transfer receipts, and exactly the expected number of runs in the experiment.
Historical copied runs, registered model versions and the original ``packages/`` objects are only read.

  python -m research_cloud.deploy.publish_packages --url URL --packages DIR --receipts R.jsonl
      --transfer-receipts packages.jsonl --registry-ledger registry_ledger.json --image-map MAP.json
      --expect-packages 223 --expect-files 15477 --out REPORT.json [--workers 8] [--only NAME ...]
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import threading
import time

BUCKET = "food-crisis-modeling-enso-research-artifacts"
EXPERIMENT = "historical-packages"
PROJECT = "food-crisis-modeling-enso"


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def source_links(name, meta, registry):
    links = {}
    rows = [r for r in registry if r.get("package") and os.path.basename(r["package"]["package"]) == name]
    if rows:
        current = meta["_package_json_sha256"]
        ok = [r for r in rows if r["package"]["package_json_sha256"] == current]
        links["registry.link_status"] = "linked" if len(ok) == len(rows) else f"stale-ledger-sha ({len(rows) - len(ok)})"
        links["registry.versions"] = json.dumps(sorted(f"{r['registered_model']}|{r['version']}" for r in ok))
        links["source.run_ids"] = json.dumps(sorted({r["source_run_id"] for r in ok if r.get("source_run_id")}))
    else:
        links["registry.link_status"] = "not in the MLflow registry"
        ident, src = meta.get("identity") or {}, meta.get("source") or {}
        if isinstance(ident, dict) and ident.get("run"):
            links["source.run"] = str(ident["run"])
        if isinstance(src, dict) and src.get("run_root"):
            links["source.run_root"] = str(src["run_root"])[:500]
    return links


def copy_one(bucket, transfer, name, run_id, prefix, rel, write=True):
    """Copy (or, with write=False, only check) one package file. Every call re-reads the current source and
    destination: the source must still be the transferred object (generation, md5, crc32c of its receipt) and the
    copy is made from exactly that generation, create-only; the destination must then hold the receipt's md5/crc32c.
    Receipts are never trusted on their own."""
    from google.api_core.exceptions import PreconditionFailed
    src_name, dst_name = f"packages/{name}/{rel}", f"{prefix}/{rel}"
    row = {"package": name, "run_id": run_id, "src": src_name, "dst": dst_name}
    rec = transfer.get(src_name)
    src = bucket.get_blob(src_name)
    if rec is None or src is None or src.generation != rec["generation"] or src.md5_hash != rec["local_md5"] \
            or src.crc32c != rec["local_crc32c"]:
        return {**row, "status": "refused: source object is not the transferred generation/hashes"}
    dst = bucket.get_blob(dst_name)
    state = "present (re-verified)"
    if dst is None:
        if not write:
            return {**row, "source_generation": src.generation, "status": "missing"}
        try:
            bucket.copy_blob(src, bucket, dst_name, source_generation=rec["generation"], if_generation_match=0)
        except PreconditionFailed:
            pass
        dst, state = bucket.get_blob(dst_name), "copied"
    ok = dst is not None and dst.md5_hash == rec["local_md5"] and dst.crc32c == rec["local_crc32c"]
    return {**row, "source_generation": src.generation, "bytes": dst.size if dst else None,
            "md5": dst.md5_hash if dst else None, "crc32c": dst.crc32c if dst else None,
            "generation": dst.generation if dst else None, "status": f"verified ({state})" if ok else "conflict"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--url", "--packages", "--receipts", "--transfer-receipts", "--registry-ledger", "--image-map", "--out"):
        ap.add_argument(k, required=True)
    ap.add_argument("--expect-packages", type=int, required=True)
    ap.add_argument("--expect-files", type=int, required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", action="append", default=[], help="pilot: only these packages (coverage checks skipped)")
    ap.add_argument("--verify", action="store_true", help="read-only final reconciliation: no run/tag/object writes")
    args = ap.parse_args(argv)
    from google.cloud import storage
    from mlflow.tracking import MlflowClient

    from research_cloud.deploy import provision_secrets as ps
    from research_cloud.deploy.mlflow_identities import cred
    from research_cloud.images.rootfs_replay import IMAGE_FOR_ENV, package_env

    user, pw = cred(ps.Api(), "mlflow-temp-admin")
    os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"] = user, pw
    client = MlflowClient(tracking_uri=args.url)
    bucket = storage.Client(project=PROJECT, client_options={"quota_project_id": PROJECT}).bucket(BUCKET)
    registry = json.load(open(args.registry_ledger))["rows"]
    images = json.load(open(args.image_map))
    transfer = {}
    for line in open(args.transfer_receipts):
        r = json.loads(line)
        if r["status"].startswith("verified"):
            transfer[r["object"]] = r
    names = sorted(os.listdir(args.packages))
    if args.only:
        names = [n for n in names if n in args.only]
    elif len(names) != args.expect_packages:
        raise SystemExit(f"coverage: {len(names)} packages, expected {args.expect_packages}")
    exp = client.get_experiment_by_name(EXPERIMENT)
    exp_id = exp.experiment_id if exp else client.create_experiment(EXPERIMENT)
    lock, out = threading.Lock(), open(args.receipts, "a")
    report = {"experiment_id": exp_id, "packages": {}}
    total_files = 0
    for name in names:
        pdir = os.path.join(args.packages, name)
        meta = json.load(open(os.path.join(pdir, "package.json")))
        meta["_package_json_sha256"] = sha256_file(os.path.join(pdir, "package.json"))
        found = client.search_runs([exp_id], filter_string=f"tags.`package.name` = '{name}'", max_results=2)
        if len(found) > 1:
            raise SystemExit(f"{name}: more than one package run")
        image = images[IMAGE_FOR_ENV[package_env(pdir)]]
        tags = {"package.name": name, "package.json_sha256": meta["_package_json_sha256"],
                "package.content_sha256": meta.get("content_sha256", ""), "package.family": meta["family"],
                "package.status": meta["status"], "package.replay_image": image,
                "package.gcs_original": f"gs://{BUCKET}/packages/{name}/", **source_links(name, meta, registry)}
        if found:
            run = found[0]
            if run.data.tags.get("package.json_sha256") != meta["_package_json_sha256"]:
                raise SystemExit(f"{name}: existing run binds another package.json; refusing")
        elif args.verify:
            raise SystemExit(f"{name}: no package run")
        else:
            run = client.create_run(exp_id, run_name=name, tags=tags)
        prefix = "mlflow-artifacts/" + run.info.artifact_uri.split("mlflow-artifacts:/", 1)[1].strip("/") + "/package"
        files = sorted(meta["files"]) + ["package.json"]
        total_files += len(files)

        def copy(rel):
            return copy_one(bucket, transfer, name, run.info.run_id, prefix, rel, write=not args.verify)

        with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
            results = [r for r in pool.map(copy, files) if r]
        with lock:
            for r in results:
                r["time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                out.write(json.dumps(r) + "\n")
            out.flush()
        bad = [r for r in results if not r["status"].startswith("verified")]
        if args.verify:
            tag_diff = sorted(k for k, v in {**tags, "package.files": str(len(files))}.items() if run.data.tags.get(k) != v)
            report["packages"][name] = {"run_id": run.info.run_id, "files": len(files), "bad": len(bad),
                                        "tag_mismatch": tag_diff, "finished": run.info.status == "FINISHED"}
            report.setdefault("problems", []).extend(
                [f"{name}: {len(bad)} files"] * bool(bad) + [f"{name}: tags {tag_diff}"] * bool(tag_diff)
                + [f"{name}: run {run.info.status}"] * (run.info.status != "FINISHED"))
            print(json.dumps({"package": name, "verified_files": len(files) - len(bad), "bad": len(bad)}), flush=True)
            continue
        if bad:
            raise SystemExit(f"{name}: {len(bad)} copies not verified; run left open")
        for k, v in tags.items():
            if run.data.tags.get(k) != v:
                client.set_tag(run.info.run_id, k, v)
        client.set_tag(run.info.run_id, "package.files", str(len(files)))
        if run.info.status != "FINISHED":
            client.set_terminated(run.info.run_id, "FINISHED")
        report["packages"][name] = {"run_id": run.info.run_id, "files": len(files), "image": image,
                                    "registry": tags.get("registry.link_status")}
        print(json.dumps({"package": name, "run_id": run.info.run_id, "copied_now": len(results)}), flush=True)
    if not args.only and total_files != args.expect_files:
        raise SystemExit(f"coverage: {total_files} files, expected {args.expect_files}")
    report["files"] = total_files
    if args.verify:
        runs = client.search_runs([exp_id], max_results=1000)
        report["runs_in_experiment"] = len(runs)
        if not args.only and len(runs) != args.expect_packages:
            report.setdefault("problems", []).append(f"experiment holds {len(runs)} runs, expected {args.expect_packages}")
        report["verified"] = not report.get("problems")
    json.dump(report, open(args.out, "w"), indent=1)
    print(json.dumps({"packages": len(report["packages"]), "files": total_files, "experiment_id": exp_id,
                      "verified": report.get("verified")}))
    return 1 if args.verify and not report["verified"] else 0


if __name__ == "__main__":
    sys.exit(main())
