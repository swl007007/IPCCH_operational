# Checkpoint: FEWS training linkage, pinned images, final quote, 2026-10-16 07:04 EDT by `date`

Native HEAD is `3aec3ab`. Everything here is local; no cloud operation has happened.

- **Training corrections (aeec007, b49ccc7):**
  - raw FEWS labels are validated before the native builders;
  - horizon/target identity is checked against config, snapshot `derived_from` and rows;
  - adapter implementation identity (module bytes, commit, dirty flag, image digest) is recorded in FEWS and IPCCH records, and the MLflow `source_commit` falls back to it.
- **FEWS MLflow linkage** (`p2-training-fews-b49ccc7`): the job-writer identity logged the trial to the rehearsal server (FINISHED, `source_commit` b49ccc7, clean); a read-only identity downloaded the package and replay passed 200/200; the reader's write probe was refused.
- **Images (e24de64):**
  - service and two training images; base image pinned by digest;
  - exact locks verified in fresh venvs built only from them;
  - FEWS trial booster and IPCCH fold quartets byte-identical to the proven runtimes, also when run from the assembled build contexts;
  - `images/context.py` pins the research_cloud HEAD, the FEWS commit and the P6 source artifact. Contexts must be re-assembled at the final HEAD before Cloud Build.
- **Quote (3aec3ab):** platform USD 81.07/month + 0.85 one-time; training USD 0.78 reservations (`quote-3aec3ab/`).
- **Preservation manifests** for all roots are still being written (minirun-1 done: 32,681 files / 8.59 GB).
- **Next:** G5-G11 cloud operations in order, each with an operation receipt and ledger entry: buckets and transfer, Artifact Registry and builds, Cloud SQL and import, Secret Manager, Cloud Run service, Vertex jobs and HPT smoke, then acceptance.
