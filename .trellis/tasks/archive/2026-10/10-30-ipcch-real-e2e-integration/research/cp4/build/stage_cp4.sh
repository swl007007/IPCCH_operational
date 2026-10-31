#!/usr/bin/env bash
# CP4 step 1 (local only; no Docker, no cloud): build context of the v2 runtime image from commit 115798f.
set -euo pipefail
REPO="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational"
T="$REPO/.trellis/tasks/10-30-ipcch-real-e2e-integration/research/cp4/build"
PY=/home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python
H=/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final
EVIDENCE=/home/swl007007/projects/food-crisis-research/staging/fewsnet-fixed-map-retrain-20261022/image-evidence/evidence
B="/home/swl007007/ipcch-operator/food-crisis-test/v2-build/cp4-115798f-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$B/src"
git -C "$REPO" archive 115798f cloud_pipeline | tar -x -C "$B/src"
export TMPDIR="$B" PYTHON="$PY"
cd "$B/src/cloud_pipeline"
"$PY" -m tests.cloud.make_smoke_fixture "$B/smoke-fixture-src"
ctx=$(bash deploy/build_context.sh --envelope "$H/envelope/ipcch-combination-envelope-v2-accepted.json" \
  --envelope-sha256 03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596 \
  --package "$H/package-build/out-r1/package" --handoff "$H/handoff-build/out-r5-accepted-v1" \
  --smoke-fixture-root "$B/smoke-fixture-src" --config deploy/ipcch_v2_deployment.food-crisis-test.json)
cp -R "$EVIDENCE" "$ctx/evidence"
cp "$T/cloudbuild.yaml" "$ctx/cloudbuild.yaml"
# source identity: every exported product file equals the commit (git archive) and equals the working tree's frozen hashes
(cd "$B/src" && find cloud_pipeline -type f ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum) > "$T/source-115798f.sha256"
(cd "$ctx" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$T/context-files.sha256"
du -sb "$ctx" | cut -f1 > "$T/context-size.txt"
find "$ctx" -type f | wc -l > "$T/context-file-count.txt"
cp "$ctx/ipcch/INSTALL.json" "$T/INSTALL.json"
echo "$ctx" > "$T/context-path.txt"
echo "BUILD_CONTEXT=$ctx"
