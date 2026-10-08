#!/bin/bash
# Offline relocated replay of a cloud delivery (task evidence). Usage: oct-replay-cloud.sh <run-dir-name>
set -euo pipefail
RUN="$1"; DST=/tmp/oct-cloud-$RUN; mkdir "$DST"; cd /tmp
PY=/tmp/ipcch-oct-cp2/bin/python

# 1. Download manifest + archive at their current generations; streamed SHA-256 recorded.
$PY - "$RUN" "$DST" <<'PYEOF' | tee "$DST/download.json"
import hashlib, json, sys
from google.cloud import storage
run, dst = sys.argv[1:3]
bucket = storage.Client(project="manuel-remote-sensing").bucket("manuel-remote-sensing-oct-delivery-debug")
record = {}
for name in ("manifest.json", "webapp_model_bundle.tar.gz"):
    blob = bucket.get_blob(f"deliveries/{run}/{name}")
    path = f"{dst}/{name}"
    bucket.blob(blob.name, generation=blob.generation).download_to_filename(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    record[name] = {"uri": f"gs://{bucket.name}/{blob.name}", "generation": str(blob.generation),
                    "sha256": digest.hexdigest()}
print(json.dumps(record))
PYEOF

# 2. Extract; every portable member listed in the archive's own manifest must match its recorded sha256,
#    and nothing outside that list (plus the manifest itself) may be present.
mkdir "$DST/relocated"; tar -C "$DST/relocated" -xzf "$DST/webapp_model_bundle.tar.gz"
$PY - "$DST" <<'PYEOF' | tee "$DST/member_check.json"
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]) / "relocated"
inventory = json.loads((root / "manifest.json").read_text())
expected = {e["path"]: e["sha256"] for e in inventory["files"] if e["portable"]}
present = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {"manifest.json"}
def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
mismatch = [p for p, d in expected.items() if p in present and sha(root / p) != d]
result = {"members_expected": len(expected), "missing": sorted(set(expected) - present)[:10],
          "unexpected": sorted(present - set(expected))[:10], "hash_mismatch": mismatch[:10],
          "archive_manifest_equals_root_manifest":
              (root / "manifest.json").read_bytes() == (Path(sys.argv[1]) / "manifest.json").read_bytes(),
          "validation_recorded_at_packaging": inventory["validation"]["status"]}
result["passed"] = not (result["missing"] or result["unexpected"] or mismatch) and result["archive_manifest_equals_root_manifest"]
print(json.dumps(result))
sys.exit(0 if result["passed"] else 3)
PYEOF

# 3. Offline rescore with the bundled runtime only (no repository, no cloud credentials, HOME preserved).
EMPTY=$(mktemp -d /tmp/oct-empty-gcloud.XXXX)
cd "$DST/relocated"
set +e
env -u GOOGLE_APPLICATION_CREDENTIALS -u GOOGLE_CLOUD_PROJECT CLOUDSDK_CONFIG="$EMPTY" PYTHONPATH="$DST/relocated/runtime" \
  /usr/bin/time -v ~/.venvs/ipcch-h5-202609/bin/python -B -m cloud.orchestrator.delivery_bundle rescore --root . \
  --output "$DST/rescored" > "$DST/rescore.log" 2>&1
RESCORE_EXIT=$?
set -e
echo "RESCORE_EXIT=$RESCORE_EXIT" >> "$DST/rescore.log"

# 4. Current (snapshot) validator on the extracted delivery; JSON kept even on failure, exit recorded.
cd /tmp
set +e
PYTHONPATH=/tmp/oct-test-ctx $PY - "$DST" > "$DST/current_validation.json" 2> "$DST/current_validation.err" <<'PYEOF'
import json, sys
from cloud.orchestrator import delivery_bundle as bundle
validation = bundle.validate_delivery(sys.argv[1] + "/relocated")
print(json.dumps({"status": validation["status"], "failures": validation["failures"], "checks": validation["checks"]}))
sys.exit(0 if validation["status"] == "passed" else 4)
PYEOF
VALIDATION_EXIT=$?
set -e
echo "VALIDATION_EXIT=$VALIDATION_EXIT" >> "$DST/current_validation.err"
grep -E "RESCORE_EXIT|Maximum resident|Elapsed" "$DST/rescore.log"
echo "VALIDATION_EXIT=$VALIDATION_EXIT"; head -c 1500 "$DST/current_validation.json"; echo
exit $(( RESCORE_EXIT != 0 || VALIDATION_EXIT != 0 ))
