# FEWS preservation manifests (native `inventory/preservation_manifest.py`, 3c39f64)

These are local byte manifests that feed the per-file transfer. The transfer must still re-hash every file in the cloud (fresh verification); these manifests do not replace that.

| Root | Manifest | Files | Bytes | Notes |
|---|---|---|---|---|
| `scen-b43ef6a-v1` | `scen-b43ef6a-v1.json.gz` (gzip of the JSON, raw sha256 `99c999d0…fece24`) | 55,899 | 45,341,699,278 | 20/20 run-recorded outputs (`scenario_actual/actual.json`) match. No walk errors, no symlinks. Includes `gate_pairs.csv.gz` and all scenario material. |
| `scen-b43ef6a-v1.actual-inputs-v1` | `scen-b43ef6a-v1.actual-inputs-v1.json` | 6 | 19,955,548 | Extension inputs. |
| `scen-b43ef6a-v1.failed_stage1` (aborted) | `scen-b43ef6a-v1.failed_stage1.json` | 670 | 804,609,121 | Of which 264 weights are 406,514,277 bytes. Preserved as cache evidence. |

- **`hash_source`:** "cache (path, bytes and mtime_ns equal)" only when that predicate held (20,992 `.ubj` in scen). Every other file was hashed fresh. The supervisor recheck found that the summary and the manifest hash agree, and 6 representative files matched on a fresh check.
- **Transfer baseline** (supervisor `transfer-volume-supervisor.md`):
  - All 27 FEWS roots: 136,776 files, 76,949,755,782 bytes (no errors, symlinks or overlapping roots).
  - Gross FEWS + inputs + MLflow + packages (at the 10:25 UTC snapshot): 101,479,395,485 bytes. This keeps the logical duplication and excludes later images, retention and additions.
- **Windows paths** in the run records are provenance only.
