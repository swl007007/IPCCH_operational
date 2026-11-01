# Re-fetchable evidence cache

`batch-feature_provenance.csv` (77,799,786 bytes) is kept locally and deliberately
excluded from Git. It is not an omitted execution log. The immutable source is:

`gs://food-crisis-test-ipcch-data/ipcch-v2/real/feature_batches/ipcch-2026-11-ipcch-real-fe7282ef75e747fd-a02e27ee805d/feature_provenance.csv#1793503525109414`

SHA256: `e92b1361c64937bf45d4b27f4da7299a72b7ffe2f3d9181a889a35e662e0f66c`.

`SHA256SUMS.final` includes this cache because it was verified during acceptance.
On another checkout, re-fetch that pinned generation before checking the complete
manifest, or explicitly report this cache as absent. The retained small
`batch-manifest.json`, `acled-cutoff.json` and `witness-links.json` record its pin
and acceptance checks. Never replace it with the latest unpinned object.
