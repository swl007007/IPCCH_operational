# Output directory index

| Directory | Purpose |
|---|---|
| `migration_packages/october_cloud_delivery/` | Verified local payload for moving the October cloud workflow; includes inventory and destination templates |
| `migration_packages/october_cloud_delivery.tar.gz` | Compressed copy of that payload for transfer |
| `manual_delivery/202609_h5/20260923_country_confidence_v3/` | Compact final September manual handoff: verified replay archive, final CSVs, small test fixtures and original metadata |
| `model_delivery/october_cloud_delivery/oct-final-20261008a/` | Accepted October cloud delivery; unchanged |
| `fewsnet_partitioned_rf/` | Active FEWSNET inputs/model artifacts and pipeline outputs; unchanged |
| `ipcch_unified/` | Active IPCCH inputs, geometry, model inputs and pipeline outputs; unchanged |

## September relocation

The final v3 handoff moved from `model_delivery/202609_h5/20260923_country_confidence_v3/`
to `manual_delivery/202609_h5/20260923_country_confidence_v3/`. Its `inventory.json`
describes the compact folder. Original manifests in `original_metadata/` describe the
historical full delivery, not the compact directory. To restore archived members,
extract `webapp_model_bundle.tar.gz` into a separate empty directory.

Superseded `20260909_refresh_v1`, `20260909_refresh_v1_superseded_civ_mapping`, and
`20260911_training_confidence_v2` backups were removed with user approval. No replacement
full backup was created. Older plans keep their original paths as historical records.
Required raw history inputs were preserved separately in the migration payload; the
prediction archive alone does not contain full history for future cloud preparation.

See [migration instructions](../deploy/october_delivery/MIGRATION.md) and
[the quickstart](../deploy/october_delivery/QUICKSTART.en.md). Generated payloads and manual
results are local files excluded from Git; copy the archive itself when handing it over.
