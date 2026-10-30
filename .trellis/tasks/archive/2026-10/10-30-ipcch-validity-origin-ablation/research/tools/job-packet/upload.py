"""Origin-ablation job packet step (create-only GCS writes; run only after release): the input objects of task 10-30.
Adapted from the task 10-28 CH ``upload.py``: the transport (``upload_args``/``put``, readback, reconcile) is unchanged; only the objects differ.

Order, one process, no retry and no overwrite (google-cloud-storage client with the operator's ADC):
  1. precheck (reads): none of the 9 target objects exists; local bytes equal ``objects.json`` (sha256/md5/crc32c/size);
  2. the three DATA objects create-only (``if_generation_match=0``, ``retry=None``): byte-equal copies of the CH-final
     run's three retained prediction files, each read back (size, MD5, CRC32C equal); generations recorded;
  3. local ``make_packet.py manifests --pred-generations G0 G6 G12`` writes the three formal cloud manifests (the CH-final
     run's generation-pinned roles, ``baseline_predictions`` replaced); their pins are re-checked against the recipes'
     inherited inputs with the CH-final comparison input inside that command;
  4. the three manifests then the three configs, each create-only with the same readback.
Checksums (r2): an object above the SDK multipart limit (8 MiB, the corrected interim) is a resumable upload with
``checksum=None`` and ``crc32c_checksum_value`` = the precomputed CRC32C sent in the object metadata, because the SDK's
client-side resumable checksum path calls ``Blob.delete()`` on a mismatch (google-cloud-storage 3.17.1 blob.py:2486-2489)
and this packet never deletes. Objects up to 8 MiB are multipart uploads with ``checksum="crc32c"`` (CRC32C in the object
metadata part, server-validated; that SDK path has no delete). In both cases acceptance is the explicit readback: size,
MD5 and CRC32C of the created generation must equal the local bytes; a mismatch stops (the object is left as evidence).
An upload error is reconciled by one metadata read (never re-sent) and stops; a precondition failure means the object
already exists: stop and report. Receipt ``--out`` (new path), written after every object.

  cd $W/control-plane-origin-ablation && IPCCH_ORIGIN_UPLOAD_CONFIRM=r1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. $W/envs/mlflow-svc/bin/python -B upload.py --objects-sha256 SHA --out RECEIPT.json
"""
import argparse, base64, hashlib, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = "food-crisis-modeling-enso"
BUCKET = f"{PROJECT}-research-inputs"
STORE = "training-jobs/ipcch-validity-origin-ablation/r1/inputs"
STORE_ORDER = ("manifest-formal-h00.json", "manifest-formal-h06.json", "manifest-formal-h12.json",
               "config-formal-h00.json", "config-formal-h06.json", "config-formal-h12.json")


def digests(path):
    import google_crc32c
    s, m, c, n = hashlib.sha256(), hashlib.md5(), google_crc32c.Checksum(), 0
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            s.update(b); m.update(b); c.update(b); n += len(b)
    return {"bytes": n, "sha256": s.hexdigest(), "md5": base64.b64encode(m.digest()).decode(), "crc32c": base64.b64encode(c.digest()).decode()}


def upload_args(loc, content_type, multipart_max):
    """Create-only, no retry; never the SDK's resumable client-checksum path (its mismatch handler deletes)."""
    args = {"content_type": content_type, "if_generation_match": 0, "retry": None, "timeout": 900}
    if loc["bytes"] > multipart_max:
        args.update(checksum=None, crc32c_checksum_value=loc["crc32c"])
    else:
        args.update(checksum="crc32c")
    return args


def remote(blob):
    return {"generation": blob.generation, "size": blob.size, "md5": blob.md5_hash, "crc32c": blob.crc32c,
            "content_type": blob.content_type, "time_created": str(blob.time_created)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--objects-sha256", required=True)
    a = ap.parse_args()
    if os.environ.get("IPCCH_ORIGIN_UPLOAD_CONFIRM") != "r1" or os.path.exists(a.out):
        raise SystemExit("needs IPCCH_ORIGIN_UPLOAD_CONFIRM=r1 and a new receipt path")
    raw = open(os.path.join(HERE, "objects.json"), "rb").read()
    if hashlib.sha256(raw).hexdigest() != a.objects_sha256:
        raise SystemExit("objects.json differs from the released packet")
    plan = json.loads(raw)
    obj = os.path.join(HERE, "objects")
    if any(os.path.exists(os.path.join(obj, f"manifest-formal-h{h:02d}.json")) for h in (0, 6, 12)):
        raise SystemExit("local manifests already exist; they are generated only after the data uploads")
    targets = {role: d["object"] for role, d in plan["data"].items()}
    targets.update({rel: f"{STORE}/{rel}" for rel in STORE_ORDER})

    from google.cloud import storage
    from google.api_core.exceptions import PreconditionFailed
    client = storage.Client(project=PROJECT, client_options={"quota_project_id": PROJECT})
    bucket = client.bucket(BUCKET)
    rec = {"bucket": BUCKET, "objects": [], "transport": "google-cloud-storage client (ADC), create-only if_generation_match=0, "
           "retry=None, server-validated CRC32C (no SDK delete path), size/MD5/CRC32C readback"}

    def save():
        json.dump(rec, open(a.out, "w"), indent=1, default=str)

    existing = {k: bucket.get_blob(v) for k, v in targets.items()}
    rec["precheck_existing"] = {k: (remote(b) if b else None) for k, b in existing.items()}
    if any(existing.values()):
        rec["ok"] = False
        save()
        raise SystemExit(f"objects already exist: {[k for k, b in existing.items() if b]}; nothing uploaded")
    save()

    def put(key, path, name, content_type, want=None):
        loc = digests(path)
        it = {"key": key, "uri": f"gs://{BUCKET}/{name}", "local": loc}
        rec["objects"].append(it)
        if want is not None and any(loc[k] != want[k] for k in ("bytes", "sha256", "md5", "crc32c")):
            it["upload"], rec["ok"] = "local bytes differ from objects.json; not uploaded", False
            save()
            raise SystemExit(f"{key}: local bytes differ from the released pins")
        from google.cloud.storage.blob import _MAX_MULTIPART_SIZE
        blob = bucket.blob(name, chunk_size=64 * 1024 * 1024)
        args = upload_args(loc, content_type, _MAX_MULTIPART_SIZE)
        it["upload_mode"] = {k: v for k, v in args.items() if k != "content_type"}
        try:
            blob.upload_from_filename(path, **args)
            it["upload"] = "created"
        except PreconditionFailed as e:
            it["upload"], rec["ok"] = f"precondition failed (exists; not overwritten): {e}", False
            save()
            raise SystemExit(f"{key}: already exists")
        except Exception as e:
            it["upload"] = f"error {type(e).__name__}: {e}"
            got = bucket.get_blob(name)
            it["reconcile"] = remote(got) if got else None
            rec["ok"] = False
            save()
            raise SystemExit(f"{key}: upload outcome uncertain; reconciled once, stopping")
        got = bucket.get_blob(name)
        it["remote"] = remote(got)
        it["equal"] = got.size == loc["bytes"] and got.md5_hash == loc["md5"] and got.crc32c == loc["crc32c"]
        save()
        if not it["equal"]:
            rec["ok"] = False
            save()
            raise SystemExit(f"{key}: readback differs from the local bytes")
        return got.generation

    gens = {}
    for role in ("baseline_predictions_h00", "baseline_predictions_h06", "baseline_predictions_h12"):
        d = plan["data"][role]
        gens[role] = put(role, d["local"], d["object"], d["content_type"], d)
    r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "make_packet.py"), "manifests",
                        "--pred-generations", *(str(gens[f"baseline_predictions_h{h:02d}"]) for h in (0, 6, 12))],
                       capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    rec["manifests"] = {"rc": r.returncode, "stdout": r.stdout[-1500:], "stderr": r.stderr[-1500:]}
    save()
    if r.returncode:
        rec["ok"] = False
        save()
        raise SystemExit("manifest generation failed")
    for rel in STORE_ORDER:
        want = None
        if rel.startswith("config-"):
            h = int(rel[len("config-formal-h"):-len(".json")])
            want = {"sha256": plan["configs"][str(h)]["sha256"]}
            if digests(os.path.join(obj, rel))["sha256"] != want["sha256"]:
                rec["ok"] = False
                save()
                raise SystemExit(f"{rel}: config differs from objects.json")
        put(rel, os.path.join(obj, rel), f"{STORE}/{rel}", "application/json")
    rec["generations"] = {it["key"]: it["remote"]["generation"] for it in rec["objects"]}
    rec["ok"] = True
    save()
    print(json.dumps({"ok": True, "generations": rec["generations"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
