# CP3a — FEWS NET partition asset line endings (D6), executed evidence

Change: one `.gitattributes` rule `cloud_pipeline/fewsnet_partitioned_rf_pipeline/assets/partitions/cluster_mapping_k40_nc17_general_refined_contig3.csv text eol=crlf`, then the single path re-materialized from its unchanged blob (`rm` + `git checkout --`). No Python, pin, verification code or scientific content changed.

| check | result |
|---|---|
| blob | d0e2f51be8ff09ef8bbf266e36fd2bba45225f4d before and after (`git hash-object`), i/lf |
| working-tree bytes WSL | before 4d94772f… (LF); after **4723cae57c07229973559f1fe62fb13bae818c2b2de71e171ce3b2eaf5c2152b** = `config.PARTITION_ASSET_SHA256` = `partition_manifest.json` sha256 (approved source bytes) |
| Windows Git | `git.exe status --short` on the partitions dir: no output (rc 0); `ls-files --eol`: i/lf w/crlf attr/text eol=crlf |
| checksum gate kept | `PartitionMap.load(LF copy, expected=4723cae5…)` → ValueError "partition asset SHA-256 mismatch … got 4d94772…"; approved working-tree bytes → accepted |
| suite | `cd cloud_pipeline && ~/.venvs/fewsnet-test-lock-20261022/bin/python -m pytest tests/fewsnet_partitioned_rf -q -p no:cacheprovider` → 53 passed, exit 0 (incl. test_full_history_fit.py, previously a collection error) — `cp3a-fews-partition-tests.log` |
