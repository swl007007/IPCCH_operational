# FEWS training linkage and the corrected snapshot

- **Linked trial.** `linked-trial.json` (MLflow run `bce1f31748ae44abb47487c866943c0c`) used the pre-fix snapshot `fews-features-h4-2019-02`, whose `derived_from.builder_code` has no `adapter` block. Its data bytes and cohorts were verified exactly against the original (`p2-training-fews-713e350/comparison.json`), so there is no contamination claim. It is not relabelled as corrected.
- **Corrected snapshot.** The corrected identity-bound snapshot is `scratch/training/fews-features-h4-2019-02-ff90981` (`corrected-snapshot-manifest.json`). It was built from committed code in the lock venv, and `derived_from.builder_code.adapter` records the module hashes and a clean control-plane commit. Launched at ff90981; `adapter_identity` read HEAD 6d4a9b6 at completion, and the training modules are byte-identical between the two commits. Rows, X and feature-order bytes equal the pre-fix snapshot.
- **Cloud use.** The image and cloud smoke use the corrected snapshot.
- **Linked-run check.** The supervisor verified the linked run's stored status and tags read-only: FINISHED, source_commit b49ccc7, clean, image_digest empty (local run).
