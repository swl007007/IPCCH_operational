# Local verification

- Relocated supported cloud/runtime/operator tests: 410 passed, 1 skipped, 417 existing warnings. The skipped YAML workflow test was run separately with system Python/PyYAML: 1 passed.
- Archive/deploy setup tests: 7 passed. Remaining retained model input/population/uncertainty contract tests: 47 passed. Total executed passing tests: 465; no unresolved test failure.
- New operator CLI, setup and handover packager plus operator tests pass Ruff. Formatting changes were AST-identical.
- Real relocated baseline initialization preview: 64 file identities and six accepted model scopes validated without opening a cloud client or deserializing existing weights. The preview used a fake destination image URI with the identical accepted digest and removed Google credential/project environment variables.
- Public Markdown links resolve. Build context shell command executed successfully after converting its new script to LF; Git attributes now preserve shell LF and exact dependency-lock bytes.
- Windows Git staged whitespace check reports one harmless extra blank line at EOF in tools/refresh_h5_inputs.py. Source was kept frozen during final packaging; this is a style advisory, not a failed runtime test.
- September inventory: 20 members verified. October: 37 retained original loose members plus the archive and original manifest match recorded hashes. The original October manifest describes expanded content; missing loose expanded members remain in the already-verified portable archive. Current compact wrapper inventory is separate.
- External archive: 690 files, 5,213,890,698 bytes, each same-volume move verified by path/size/mtime/filesystem identity. No original legacy content deleted or overwritten.
- No cloud deployment/provider calls, model retraining, accepted prediction replay, close audit or spot audit. Live destination IAM/provider operation remains untested.

Final handover archive and extraction receipt are recorded separately after packaging completes.
