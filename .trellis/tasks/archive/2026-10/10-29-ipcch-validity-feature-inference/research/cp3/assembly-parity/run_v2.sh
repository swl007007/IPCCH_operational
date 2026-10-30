#!/bin/bash
# Assembly parity (historical compatibility evidence; NOT the CP5 M2026-10/O2026-08 execution). Each stage's rc is judged
# explicitly; the script exits with the first failing stage's rc. Logs of earlier runs are never overwritten (OUT is new).
set -euo pipefail
R=/home/swl007007/projects/food-crisis-research; OUT=${1:?usage: run_v2.sh NEW_OUTPUT_DIR}
[ -e "$OUT" ] && { echo "$OUT exists; use a new directory"; exit 64; }
mkdir -p "$OUT"
set +e
( cd $R/control-plane-h2h8h14-pkg && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. IPCCH_AE_SRC=$R/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment ~/.venvs/ipcch-validity-idp/bin/python -B "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp3/assembly-parity/stage1_research.py" "$OUT" "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp1/recipes" )
rc1=$?; echo "stage1 rc=$rc1"
[ $rc1 -eq 0 ] || { echo "STAGE1 FAILED"; exit $rc1; }
PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python -B "/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp3/assembly-parity/stage2_operational.py" "$OUT" $R/scratch/h2h8h14-final/handoff-build/out-r4 $R/staging/ipcch-update-202610/sources/acled_agg/processed/acled_agg_monthly.csv $R/scratch/h2h8h14-final/package-build/out-r1/package
rc2=$?; echo "stage2 rc=$rc2 (0 exact, 2 parity differs, other = failure)"
exit $rc2
