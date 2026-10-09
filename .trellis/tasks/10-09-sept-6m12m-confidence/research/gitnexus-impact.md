# GitNexus impact (pre-edit, 2026-10-09)

Index re-analyzed at commit d7aaadf before the query (`node .gitnexus/run.cjs analyze`).

`impact({target: "_evidence_identity", direction: "upstream"})` -> risk LOW, epistemic exact.
- d=1 (CALLS): `area_evidence`, `residual_evidence` (both `cloud_pipeline/cloud/orchestrator/delivery_outputs.py`).
- processes affected: 0; modules: Orchestrator (2 direct hits).
- Reached at runtime through `scope_diagnostics` from `deliver._write_scopes` and `delivery_bundle.regenerate_diagnostics` (offline rescore).
