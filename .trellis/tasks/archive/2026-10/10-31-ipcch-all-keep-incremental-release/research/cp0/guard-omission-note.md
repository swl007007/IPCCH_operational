# CP0 guard omission (recorded honestly; reads not duplicated)

Two CP0 local readbacks ran through `cloudop.py`, so they are logged in `cloud-operations.jsonl` with argv, times and exit, but they ran OUTSIDE `guarded.sh`:
- `readback_v2.py pre real pre-real.json`, which reads the current pointer and record (a few KB);
- `store_inventory.py gs://food-crisis-test-ipcch-data/ipcch-v2/real inventory-pre-run-real.json`, which reads 56 HEADs plus small ledger, acceptance and binding contents.

Both exited 0. They were read-only, so no memory limit, CHILD-EXIT or RSS evidence exists for them. Per the Supervisor's instruction, these completed cloud reads are NOT re-run only to fix logging.

From here on, every local readback, parsing, test or lineage/DA2 table-content step runs under the archived `research/cp2/guarded.sh`: 4 GiB cgroup, 3 GiB AS, no swap, 600 s, CHILD-EXIT.

**cloudop timeout semantics.** `cloudop.py` appends its ledger record only after `subprocess.run` returns. If a command times out, the wrapper raises before logging. In that case the Executor records argv, start and end, and an UNKNOWN outcome, manually and immediately. It never infers "no mutation" and never resubmits.
