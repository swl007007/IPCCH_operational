# September manual delivery

Final September v3 CSVs are in `fewsnet/` and `ipcch/`. The independently replayable offline package is `webapp_model_bundle.tar.gz`.

To inspect or use the full package, extract it into a new empty directory and follow its bundled README:

```bash
mkdir september-bundle
tar -xzf webapp_model_bundle.tar.gz -C september-bundle
```

Its offline replay has already been verified. This reorganization preserved the accepted archive/results and did not repeat inference. `inventory.json` records hashes and sizes of retained local files. `original_metadata/` preserves the historical full-delivery metadata; it describes the original expanded tree rather than this compact folder. `inputs/` and `reports/` retain the small comparison evidence.

This entrypoint is the accepted manual delivery, not a raw-data assembly workflow. Ongoing monthly cloud preparation, migration and its one-time historical baseline live in the separate `cloud_pipeline/` handover. Original raw assembly scripts are preserved in the external legacy archive and are not required to consume or replay this package.
