#!/usr/bin/env bash
# Relocated offline replay of a downloaded confidence-rerun bundle (same pattern as the October final replay).
# Usage: oct_confidence_replay.sh <download dir with manifest.json + webapp_model_bundle.tar.gz> <fresh replay dir>
# Extracts the archive into an empty directory outside the repository, checks members against the delivery
# manifest, then runs the bundled runtime (PYTHONPATH=runtime) with the frozen Python 3.12.3 environment, an
# empty CLOUDSDK_CONFIG and no repository on the path: delivery_bundle rescore + validate_delivery.
set -euo pipefail
download="$(cd "$1" && pwd)"
replay="$2"
python="${REPLAY_PYTHON:-$HOME/.venvs/ipcch-h5-202609/bin/python}"
mkdir "$replay"   # must be fresh
replay="$(cd "$replay" && pwd)"
mkdir "$replay/root"
tar -xzf "$download/webapp_model_bundle.tar.gz" -C "$replay/root"
cd "$replay/root"
"$python" -B - "$download/manifest.json" > "$replay/member_check.json" <<'EOF'
import hashlib, json, pathlib, sys
root_manifest = pathlib.Path(sys.argv[1]).read_bytes()
manifest = json.loads(root_manifest)
expected = {f["path"]: f["sha256"] for f in manifest["files"] if f["portable"]}
found = {p.as_posix() for p in pathlib.Path(".").rglob("*") if p.is_file()} - {"manifest.json"}
mismatch = sorted(p for p in expected.keys() & found
                  if hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() != expected[p])
result = {"members_expected": len(expected), "missing": sorted(expected.keys() - found),
          "unexpected": sorted(found - expected.keys()), "hash_mismatch": mismatch,
          "archive_manifest_equals_root_manifest": pathlib.Path("manifest.json").read_bytes() == root_manifest,
          "validation_recorded_at_packaging": manifest["validation"]["status"]}
result["passed"] = (not result["missing"] and not result["unexpected"] and not mismatch
                    and result["archive_manifest_equals_root_manifest"]
                    and result["validation_recorded_at_packaging"] == "passed")
print(json.dumps(result))
EOF
cat "$replay/member_check.json"
cfg="$(mktemp -d)"
set +e
env -i HOME="$HOME" PATH=/usr/bin:/bin CLOUDSDK_CONFIG="$cfg" PYTHONPATH=runtime \
  /usr/bin/time -v "$python" -B -m cloud.orchestrator.delivery_bundle rescore --root . --output "$replay/rescored" \
  > "$replay/rescore.log" 2>&1
echo "RESCORE_EXIT=$?" >> "$replay/rescore.log"
env -i HOME="$HOME" PATH=/usr/bin:/bin CLOUDSDK_CONFIG="$cfg" PYTHONPATH=runtime "$python" -B -c \
  'import json, pathlib; from cloud.orchestrator.delivery_bundle import validate_delivery; print(json.dumps(validate_delivery(pathlib.Path("."))))' \
  > "$replay/current_validation.json" 2> "$replay/current_validation.err"
echo "VALIDATION_EXIT=$?" >> "$replay/current_validation.err"
set -e
tail -3 "$replay/rescore.log"; grep -E '"all_equal"|Elapsed|Maximum resident' "$replay/rescore.log"
cat "$replay/current_validation.err"; head -c 300 "$replay/current_validation.json"; echo
