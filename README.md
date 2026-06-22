# IPCCH Operational

This repository produces monthly model-compatible IPCCH input tables. A later
prediction step will use exported model weights and the model pipeline together
with that monthly input to generate predictions.

Start here:

1. `docs/00_handover_overview.md`
2. `docs/01_environment_setup.md`
3. `docs/02_ee_gcs_account_setup.md`
4. `docs/03_workflow_runbook.md`
5. `docs/04_output_inventory.md`
6. `docs/05_weilun_handover_gap_list.md`
7. `docs/08_sediqa_raw_data_download_notes.md`

Local filled config files such as `config/paths.ini` and `config/ee_gcs.ini` are operator-specific. Share templates, not secrets.
