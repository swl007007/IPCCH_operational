# Plan
1. Commit prd/plan; `trellis-audit start v3-export-repair --remediation-for e22fff87ebea5d813683811c`; verify run.
2. `tools/run_h5_model_delivery.py`: extract `polygon_mapping(system, predictions)`; add `export_bundle(root, out, predictions_root)` using only delivered assets; CLI `export --output DIR [--predictions DIR]` routes to it, `export` without `--output` keeps the repository build.
3. `tools/verify_h5_model_delivery.py`: in the relocation temp dir also copy delivered polygon/country/reference/confidence/geojson + policies, run bundle export on the rescored output, compare with delivered tables.
4. Update V: remove create-only derived outputs (final_verification, final_integrity, bundle_manifest, manifest, archive), refresh runtime/tools, fix README command, rerun verify_h5_country_v3 (unchanged, must pass), verify_h5_model_delivery, then extract-archive bundle-only export smoke test, package.
5. Commit, `detect_changes`, `trellis-audit close`; monitor repair audit and the linked re-audit.
