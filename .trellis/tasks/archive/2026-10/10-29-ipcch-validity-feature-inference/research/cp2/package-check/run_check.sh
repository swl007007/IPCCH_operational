#!/bin/bash
# stage 0: verify_combination on the built package and on a relocated copy; stage 1 probes; stage 2 runtime check
set -u
B=/home/swl007007/projects/food-crisis-research/scratch/h2h8h14-final/package-build; C="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/.trellis/tasks/10-29-ipcch-validity-feature-inference/research/cp2/package-check"; R=/home/swl007007/projects/food-crisis-research
cd /home/swl007007/projects/food-crisis-research/control-plane-h2h8h14-pkg
mkdir -p $B/check-r1 && cp -a $B/out-r1/package $B/check-r1/relocated-package
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. ~/.venvs/ipcch-validity-idp/bin/python -B -c "
import json,sys
from research_cloud.packages.operational_ipcch import verify_combination
r={p: verify_combination(p) for p in sys.argv[1:]}
print(json.dumps(r)); sys.exit(1 if any(r.values()) else 0)" $B/out-r1/package $B/check-r1/relocated-package; echo "stage0 verify rc=$?"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. IPCCH_AE_SRC=$R/sources/Food_Crisis_Cluster/IPCCHAlphaEarthExperiment ~/.venvs/ipcch-validity-idp/bin/python -B "$C/probe_real.py" $B/check-r1 "$C/../../cp1/recipes" $R/scratch/h2h8h14-final/harvest; echo "stage1 probes rc=$?"
PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python -B "$C/runtime_check_real.py" $B/check-r1/relocated-package $B/check-r1; echo "stage2 runtime rc=$?"
