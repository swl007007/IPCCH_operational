#!/bin/bash
# Final recompute + logs + readback + UI (task 10-30; run once, only after Supervisor release). Adapted from the task 10-28
# run_final.sh (base copy in base-10-28/): origin paths, every path quoted (the receipts live in the operational task
# directory, whose path contains spaces), and one LOCAL step added before any live call: the independent TUI recompute and
# reconciliation (recompute_origin.py). Live operations: THREE job-filtered Cloud Logging reads (job_logs.py, limit 2000
# each); exactly TWO mlflow-reader secret accesses (readback_origin.py; browser_check.py hands its identity to the Node child
# over stdin) and read-only MLflow REST/UI requests; readback's dataset_input.payload performs 3 GCS object-generation
# metadata GETs per origin run (9). No write anywhere except local receipts under research/cp4/final/. One targets.json
# (sha256 recorded before the browser run) is the input of BOTH the browser harness and verify_run_rows.
set -euo pipefail
W=/home/swl007007/projects/food-crisis-research
P="$W/staging/ipcch-origin-ablation-20261030/final-packet"
T10="$W/staging/ipcch-origin-ablation-20261030/tools"
H="$W/scratch/origin-ablation-20261030/harvest"
CHH="$W/scratch/ch-validity-20261028/harvest"
B="$W/.trellis/tasks/10-28-ipcch-ch-validity-refits/research/cp5/supplement/readback"
U="$W/.trellis/tasks/archive/2026-10/10-20-ipcch-acled-retrain/research/cp4/ui"
TASK="/mnt/c/users/swl00/ifpri dropbox/weilun shi/ipcch_monthly_operational/.trellis/tasks/10-30-ipcch-validity-origin-ablation"
J="$TASK/research/cp3/jobs"
F="$TASK/research/cp4/final"
PY="$W/envs/mlflow-svc/bin/python"
export PYTHONDONTWRITEBYTECODE=1
[ ! -e "$F" ] || { echo "$F exists; the final packet runs once"; exit 1; }
for h in 00 06 12; do
  python3 -c "import json,sys; p=json.load(open(sys.argv[1])); sys.exit(0 if p.get('status')=='complete' and not p.get('owner') else 1)" \
    "$H/formal-h$h/trial-0/publication.json" || { echo "h$h: local publication journal is not complete"; exit 1; }
  python3 -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))['ok'] else 1)" \
    "$J/06-harvest-h$h.json" || { echo "h$h: harvest not ok"; exit 1; }
  # each replay receipt must be a clean pass of exactly the CURRENT harvested package (path + package.json sha256)
  python3 -B "$P/replay_check.py" "$J/07-replay-h$h.json" "$H/formal-h$h/trial-0/package" \
    || { echo "h$h: holdout package replay not bound/passed"; exit 1; }
  python3 -B "$P/replay_check.py" "$J/07-replay-annual-h$h.json" "$H/formal-h$h/trial-0/gcs-only/annual-package" \
    || { echo "h$h: annual package replay not bound/passed"; exit 1; }
done
mkdir -p "$F"
cd "$W/control-plane-origin-ablation"
# 0. closed identity chain BEFORE any live call (terminal/submit/harvest job; harvest == publication run/model/version)
python3 -B "$P/identity_chain.py" --stage pre --final "$F" --receipts "$J" --out "$F/00-identity-pre.json" > "$F/00-identity-pre.log" 2>&1 \
  || { echo "identity chain (pre) refused; no live call made"; exit 1; }
# 0b. independent recompute and reconciliation (local; no live call)
python3 -B "$T10/recompute_origin.py" --pair "0=$H/formal-h00/trial-0,$CHH/formal-h00/trial-0" --pair "6=$H/formal-h06/trial-0,$CHH/formal-h06/trial-0" \
  --pair "12=$H/formal-h12/trial-0,$CHH/formal-h12/trial-0" --out "$F/recompute" > "$F/00b-recompute.log" 2>&1 \
  || { echo "independent recompute refused; no live call made"; exit 1; }
# 1. bounded job logs (three reads)
python3 -B "$P/job_logs.py" --out "$F/logs" > "$F/01-logs.log" 2>&1 || echo "job_logs rc=$? (verdict below)"
# 2. readback (ONE reader access): three origin runs + the three CH-final baselines against their accepted task 10-28 receipts
PYTHONPATH=. "$PY" -B "$P/readback_origin.py" --out-dir "$F/readback" \
  --item "formal:h00:$H/formal-h00/trial-0" --item "formal:h06:$H/formal-h06/trial-0" --item "formal:h12:$H/formal-h12/trial-0" \
  --item "baseline:h00:$B/formal-h00.json" --item "baseline:h06:$B/formal-h06.json" --item "baseline:h12:$B/formal-h12.json" \
  > "$F/02-readback.log" 2>&1 || { echo "readback failed; see $F/02-readback.log"; exit 1; }
# 3. targets (local): all six identities, exactly three run-metric targets
PYTHONPATH=. "$PY" -B "$P/ui_targets_origin.py" --readback "$F/readback" --out "$F/ui-targets" > "$F/03-targets.log" 2>&1
TG="$F/ui-targets/targets.json"
SHA=$(sha256sum "$TG" | cut -c1-64)
echo "$SHA  $TG" > "$F/targets.sha256"
# 4. browser harness (ONE reader access) on that targets.json
"$PY" -B "$U/harness-cap5000/browser_check.py" --targets "$TG" --out "$F/ui-render" > "$F/04-browser.log" 2>&1 || echo "browser_check rc=$? (verdict below)"
# 5. verdict on the SAME targets.json (sha re-checked)
sha256sum -c "$F/targets.sha256"
"$PY" -B "$U/verify_run_rows.py" --targets "$TG" --render "$F/ui-render" --out "$F/ui-pass.json" > "$F/05-verify.log" 2>&1 || true
# 6. identity chain again with the logs and readback receipts (log run id / readback run+model+version == the chain)
python3 -B "$P/identity_chain.py" --stage post --final "$F" --receipts "$J" --out "$F/06-identity-post.json" > "$F/06-identity-post.log" 2>&1 || true
python3 - "$F" "$SHA" <<'X'
import json, sys
f, sha = sys.argv[1], sys.argv[2]
logs = json.load(open(f"{f}/logs/logs-check.json"))
chain = json.load(open(f"{f}/06-identity-post.json"))
rb = json.load(open(f"{f}/readback/summary.json"))
ui = json.load(open(f"{f}/ui-pass.json"))
rc = json.load(open(f"{f}/recompute/recompute.json"))
targets = json.load(open(f"{f}/ui-targets/targets.json"))
models = next(t for t in targets if t["label"] == "models-table")["rows_checks"]["models_rows"]
rec = {"targets_sha256": sha, "targets": len(targets), "identities": len(models),
       "run_metric_targets": sum(1 for t in targets if t.get("run_metric_rows")), "recompute_passed": rc["passed"],
       "logs_ok": logs["ok"], "log_reads": logs["reads"], "identity_chain_ok": chain["ok"],
       "readback_all_pass": all(v["all_checks_pass"] for v in rb["items"].values()), "readback_items": len(rb["items"]),
       "ui_pass": ui.get("ui_pass"), "reader_accesses": 2}
rec["final_pass"] = (rec["identity_chain_ok"] and rec["recompute_passed"] and rec["logs_ok"] and rec["log_reads"] == 3
                     and rec["readback_all_pass"] and rec["readback_items"] == 6 and rec["identities"] == 6
                     and rec["run_metric_targets"] == 3 and rec["ui_pass"] is True)
json.dump(rec, open(f"{f}/final-verdict.json", "w"), indent=1)
print(json.dumps(rec))
sys.exit(0 if rec["final_pass"] else 1)
X
