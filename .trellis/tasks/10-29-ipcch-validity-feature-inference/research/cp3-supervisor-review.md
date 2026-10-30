# CP3 supervisor checkpoints — ongoing

## Stores and request unit checks

Reviewed stores/retained at 9270192. Required fixes: unique immutable content names so failed HEAD updates do not poison future commits; content and generation from one stable snapshot to avoid lost updates; enforce HEAD content stays within its own table namespace; validate required acceptance fields; refuse explicit failed/contradictory GPP probes.

Reviewed fix 557515f: the above mechanisms are corrected. Independently ran from cloud_pipeline with the operational exact-lock interpreter:
`PYTHONDONTWRITEBYTECODE=1 ~/.venvs/fewsnet-test-lock-20261022/bin/python -m pytest tests/cloud/test_ipcch_stores.py tests/cloud/test_delivery_request_v2.py -q -p no:cacheprovider`
Result: 24 passed in 0.95s, exit 0. This is scoped unit evidence, not final CP3 acceptance or full request integration verification.

## ACLED c65e43d

Read-only scout inspected converter/tests/parity evidence; Supervisor checked the relevant implementation lines. Confirmed issue: validate_export parses non-padded week strings but persisted original text; refresh compares stored week strings to ISO interval boundaries. An accepted `2026-5-2` row survives a refresh replacing `2026-05-02`, double counting. Scout reproduced 7+5 ->12 (non-lock environment); exact-lock regression requested from Executor, along with canonicalization before duplicate checks/persistence (or strict rejection). Existing parity covers 18 columns and 1,250,808 rows but cannot prove this input boundary.

Other scout observations: runtime uses delivered fixed mapping rather than rematching geometry; interval completeness uses overlapping Saturday weeks, including event-free coverage; d_m/7 allocation and no initial HEAD on coverage rejection have tests. Delivery-table override/nearest construction and full runtime integration remain to verify.

Follow-up: reviewed b3035ad canonicalization before duplicate detection/persistence and strict declared-date/month handling. Independently ran exact-lock `pytest tests/cloud/test_ipcch_acled.py -q -p no:cacheprovider`: 8 passed in 0.97s, exit 0. Executor also records two regression tests failing against c65e43d and unchanged full-history parity. Date double-counting finding resolved; full CP3 remains incomplete.

Request integration follow-up: standalone v2 validator defers FEWS delivery validation to its adapter and does not enumerate nested delivery refs. Required before any collection/mutation: adapter validates the full FEWS block and all model/asset/diagnostic refs, including a mixed IPCCH+invalid-FEWS zero-write test (R17). Executor acknowledged; pending integrated verification.

## Climate scope clarification

Executor found nine shared scripts are GEE Code Editor JS with private calendar/baseline assets; SPI/SPEI uses portable numpy/scipy after GEE input download. Supervisor ruling: ensemble persistence core and SPI/SPEI math proceed, but a SourceProvider protocol plus request-spec stubs alone does not satisfy R1/R40/R43. Executable real provider adapters invoking the delivered algorithms remain in this goal. Reuse existing execution or retained/transpiled JS where practical; no blanket requirement to rewrite everything into Python. Offline differential and boundary tests are required; actual live GEE extraction is deferred by the execution protocol, not an excuse to omit implementation.

User cloud-read preauthorization covers necessary private-asset metadata/access verification, including han-sandbox-505315. No renewed human approval is required. Actual EE compute/export requires a concrete Supervisor-reviewed packet before execution; no IAM changes. If assets are inaccessible, retain configurable references, explicit runtime failure and offline-tested adapters, and report the observed live limitation. Baseline placeholders are authorized; algorithm placeholders are not final deliverables.
