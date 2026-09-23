# Repair v3 packaged export (remediation for audit job e22fff87ebea5d813683811c)

Status: remediation of a major close-audit finding on archived task `country-uncertainty-phase-revision`; executes under the user's standing instruction to follow the approved spec through audited close ("按照落盘的spec执行 ... 保持执行状态直至task close").

## Finding A01 (major, contract_violation)

`tools/run_h5_model_delivery.py export` reads Census references and source geometry from repository-only paths (`ROOT/Outcome/...`), so the export route documented in the v3 README fails inside the relocated bundle before reaching the v3 country-diagnostic branch. The v3 spec (design.md §7 export contract) requires README, reload/export behavior and packaged schemas to agree.

## Requirements

- The documented packaged export must regenerate both v3 country tables using only bundle contents: delivered polygon predictions (or a fresh rescored output), `{model}/country_population_reference.csv`, `inputs/ipcch_april_panel.csv`, frozen `{model}/country_confidence.csv` and the v3 policy.
- Create-only writes into a fresh `--output` directory; never overwrite delivered files.
- Also emit polygon model mapping (derived from predictions) and preserved GeoJSON, checked for identity agreement.
- Forecast-derived country fields keep the stale-value guard.
- The original repository build path (initial delivery construction from repository assets) keeps its behavior.
- No change to models, polygon predictions, country values or other v3 artifacts; only runtime tools, README, verification report and package inventories/archive are regenerated.

## Acceptance criteria

- [x] Relocated bundle-only export (from the extracted archive, no repository paths, PYTHONPATH cleared) succeeds and its country tables, mapping and GeoJSON equal the delivered ones (country tables exact within atol 1e-12; mapping/GeoJSON byte- or value-equal).
- [x] This relocated export check is part of `tools/verify_h5_model_delivery.py` and recorded in `reports/final_verification.json`.
- [x] README documents the working command; v3 delivery repackaged with manifest `passed` bound to the repair commit; v2 manifest still verifies; protected artifacts unchanged.
