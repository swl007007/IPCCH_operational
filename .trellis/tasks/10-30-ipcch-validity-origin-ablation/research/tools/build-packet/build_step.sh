#!/bin/bash
# Origin-ablation build packet step 2 for task 10-30 (PAID; run once, only after supervisor release): one Cloud Build of the reviewed
# three-module origin-ablation overlay context. Verifies all 9 context files against context.context-record.json (sha256 pinned below) and that no
# other file exists; requires the task tag to be absent (read; NOT_FOUND); submits once (async; gcloud stages ONE source
# tarball create under gs://food-crisis-modeling-enso-research-build/source/); polls read-only every 30 s to a terminal
# state; accepts only SUCCESS with one pushed digest for the tag; reads the image back by digest and by tag. No retry,
# no rebuild, no tag move. Receipts under the task 10-30 research/cp2/build/ (operational task directory).
set -euo pipefail
W=/home/swl007007/projects/food-crisis-research
CTX=$W/staging/ipcch-origin-ablation-20261030/image-overlay-origin
REC=$W/staging/ipcch-origin-ablation-20261030/image-overlay-origin.context-record.json
E="/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/10-30-ipcch-validity-origin-ablation/research/cp2/build"
G=(--project=food-crisis-modeling-enso --billing-project=food-crisis-modeling-enso)
IMG=us-central1-docker.pkg.dev/food-crisis-modeling-enso/research/training-ipcch-validity
TAG=gosifv3-chvalidity-originfit-20261030
mkdir -p "$E"
[ ! -e "$E/02-build-submit.json" ] || { echo "a build submit receipt exists; never resubmit"; exit 1; }
echo "c98e85577ce655e3f5243306d9ee6c85a400dec3513044fe219140b0f18f0266  $REC" | sha256sum -c
python3 - "$CTX" "$REC" <<'P'
import hashlib, json, os, sys
ctx, rec = sys.argv[1], json.load(open(sys.argv[2]))
files = rec["files"]
present = {os.path.relpath(os.path.join(r, n), ctx) for r, _, ns in os.walk(ctx) for n in ns}
bad = [p for p, s in files.items() if hashlib.sha256(open(os.path.join(ctx, p), "rb").read()).hexdigest() != s]
if bad or present != set(files) or len(files) != 9:
    sys.exit(f"context differs from its record: {bad} extra {sorted(present - set(files))} missing {sorted(set(files) - present)}")
print(f"context verified: {len(files)} files; modules {rec['module_sha256']}; tag {rec['image_tag']}")
P
if gcloud artifacts docker images describe "$IMG:$TAG" "${G[@]}" --format=json > "$E/02-tag-precheck.json" 2> "$E/02-tag-precheck.stderr"; then
  echo "tag $TAG already exists; stop"; exit 1
fi
grep -qiE "not.?found|NOT_FOUND" "$E/02-tag-precheck.stderr" || { echo "tag precheck failed without NOT_FOUND; stop"; exit 1; }
gcloud builds submit "$CTX" --config "$CTX/cloudbuild.yaml" --region=us-central1 \
  --gcs-source-staging-dir=gs://food-crisis-modeling-enso-research-build/source --timeout=1800s --async --format=json \
  "${G[@]}" > "$E/02-build-submit.json" 2> "$E/02-build-submit.stderr"
ID=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['id'])" "$E/02-build-submit.json")
echo "build $ID submitted"
while :; do
  gcloud builds describe "$ID" --region=us-central1 --format=json "${G[@]}" > "$E/02-build-describe.json"
  S=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" "$E/02-build-describe.json")
  echo "$(date -u +%H:%M:%SZ) $S"
  case "$S" in SUCCESS|FAILURE|INTERNAL_ERROR|TIMEOUT|CANCELLED|EXPIRED) break ;; esac
  sleep 30
done
[ "$S" = SUCCESS ] || { echo "build $ID ended $S; no rebuild without release"; exit 1; }
DIGEST=$(python3 - "$E/02-build-describe.json" "$IMG:$TAG" <<'P'
import json, sys
b = json.load(open(sys.argv[1]))
imgs = {i["digest"] for i in b.get("results", {}).get("images", []) if i.get("name") in (sys.argv[2], sys.argv[2].split(":")[0])}
if len(imgs) != 1:
    sys.exit(f"expected one pushed digest for the task tag, got {imgs}")
print(imgs.pop())
P
)
gcloud artifacts docker images describe "$IMG@$DIGEST" "${G[@]}" --format=json > "$E/02-ar-readback.json"
gcloud artifacts docker images describe "$IMG:$TAG" "${G[@]}" --format=json > "$E/02-ar-tag-readback.json"
python3 - "$E" "$DIGEST" <<'P'
import json, sys
e, d = sys.argv[1], sys.argv[2]
a, t = (json.load(open(f"{e}/{n}"))["image_summary"]["digest"] for n in ("02-ar-readback.json", "02-ar-tag-readback.json"))
if a != d or t != d:
    sys.exit(f"readback digests {a} / {t} differ from the build digest {d}")
P
echo "$DIGEST" > "$E/02-digest.txt"
echo "built $IMG@$DIGEST (tag $TAG)"
