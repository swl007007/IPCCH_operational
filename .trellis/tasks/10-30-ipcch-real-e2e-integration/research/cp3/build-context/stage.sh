#!/usr/bin/env bash
# CP3 actual build-context staging (no Docker, no cloud): fresh smoke fixture + deploy/build_context.sh with the accepted sources.
set -euo pipefail
export TMPDIR="/home/swl007007/ipcch-operator/food-crisis-test/v2-build/stage-20261031T015828Z" PYTHON="/home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python"
"/home/swl007007/.venvs/fewsnet-test-lock-20261022/bin/python" -m tests.cloud.make_smoke_fixture "/home/swl007007/ipcch-operator/food-crisis-test/v2-build/stage-20261031T015828Z/smoke-fixture-src"
ctx=$(bash deploy/build_context.sh --envelope "/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/envelope/ipcch-combination-envelope-v2-accepted.json" \
  --envelope-sha256 03b938427391aa15d3786377151e922bfdb97cc161f312b72ebed9f596c89596 \
  --package "/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/package-build/out-r1/package" --handoff "/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/handoff-build/out-r5-accepted-v1" \
  --smoke-fixture-root "/home/swl007007/ipcch-operator/food-crisis-test/v2-build/stage-20261031T015828Z/smoke-fixture-src" --config deploy/ipcch_v2_deployment.food-crisis-test.json)
echo "BUILD_CONTEXT=$ctx"
