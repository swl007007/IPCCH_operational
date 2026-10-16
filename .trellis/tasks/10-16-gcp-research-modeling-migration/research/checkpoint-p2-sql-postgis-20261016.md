# Checkpoint: SQL/PostGIS rehearsal and capacity complete, 2026-10-16 06:08 EDT by `date`

Native HEAD is `f93bfa1`. Everything here is local or disposable PG; no cloud import or provisioning has happened.

- **CSV import (run3):** 53/53 verified; 26/53 tables have key profiles, all agreeing; 27 have none and are disclosed. The FEWS irregular row is preserved. See `p2-sql-postgis-f93bfa1/`.
- **PostGIS:** 3 bundles verified with typed attributes and byte-equal WKB. Receipts bind export.json and inventory sha256. Invalid geometries are recorded, not repaired (source 253, FEWS 1). The rehearsal metadata table was deliberately reset before the identity-bound reload, and the superseded receipts are kept locally. 6 PG-backed tests pass.
- **Capacity:**
  - research + mlflow + mlflow_auth = 11,791,111,593 bytes (10.98 GiB);
  - WAL 1.02 GB at max_wal_size 1 GB; temp 4.67 GB cumulative (not a peak);
  - client readback temp excluded;
  - sizing ≈ 13.65 GiB with allowances, so the quote carries 30 GiB.
- **Training:** the saved-artifact feature comparison (e4a20e2) confirms the keys are byte-identical (bc94d674…) and X differs in 12,576 cells with max |Δ| 1.7e-16.
- **FEWS scen:** 8 amended packages (1a7e207) replay at 8/8 with the hash-bound accepted-exception receipt; the receipts are in `p2-packages/replay-fews-scen-1a7e207/`.
- **Next:** finish the scen preservation manifest, then remaining FEWS groups, FEWS training adapter, images, quote/cost ledger, and G5-G11.
