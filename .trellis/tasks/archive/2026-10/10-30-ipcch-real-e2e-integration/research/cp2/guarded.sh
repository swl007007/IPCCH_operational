#!/usr/bin/env bash
# Run ONE command under a memory-limited transient user service (outside init.scope; task 10-30 CP2 incident rule).
# usage: guarded.sh <label> <log-dir> <command...>   -> <log-dir>/<label>.log (full stdout+stderr) and <label>.exit
# <label>.exit is the CHILD's exit code, written by a marker line inside the service; a missing marker (stopped, killed,
# OOM, runtime limit) is recorded as INTERRUPTED with the launcher rc - systemd-run's own rc can be 0 after a stop.
set -uo pipefail
label="$1"; logdir="$2"; shift 2
cp="/mnt/c/Users/swl00/IFPRI Dropbox/Weilun Shi/IPCCH_monthly_operational/cloud_pipeline"
unit="ipcch-cp2-${label//[^A-Za-z0-9_-]/_}-$(date +%s%N)"
mkdir -p "$logdir"
{
  echo "# unit=$unit start=$(date -Is) limits: MemoryMax=4G MemorySwapMax=0 RuntimeMaxSec=600 prlimit-as=3221225472"
  echo "# command: $*"
} > "$logdir/$label.log"
systemd-run --user --unit="$unit" --wait --pipe --collect --working-directory="$cp" \
  -p MemoryMax=4G -p MemorySwapMax=0 -p RuntimeMaxSec=600 \
  --setenv=PYTHONDONTWRITEBYTECODE=1 --setenv=OPENBLAS_NUM_THREADS=1 --setenv=OMP_NUM_THREADS=1 \
  /bin/bash -c '/usr/bin/prlimit --as=3221225472 -- /usr/bin/time -v "$@"; echo "# CHILD-EXIT=$?"' guarded "$@" \
  >> "$logdir/$label.log" 2>&1
launcher=$?
child=$(grep -a '^# CHILD-EXIT=' "$logdir/$label.log" | tail -1 | cut -d= -f2)
echo "# end=$(date -Is) launcher_rc=$launcher child_exit=${child:-MISSING}" >> "$logdir/$label.log"
if [ -n "$child" ]; then echo "$child" > "$logdir/$label.exit"; else echo "INTERRUPTED launcher_rc=$launcher" > "$logdir/$label.exit"; fi
echo "$label exit=$(cat "$logdir/$label.exit")"
