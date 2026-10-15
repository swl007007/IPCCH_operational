# Publish cloud_pipeline snapshot to IFPRI GitHub

## Goal

One-off code-only snapshot of `cloud_pipeline/` at source HEAD `be49ff4` pushed as a single initial commit to the private, empty repository `IFPRI/MTID-FSP-FOOD-CRISIS-MODEL-INPUT`, so the operations team can read and clone the maintained runtime code.

## Decisions (grill, 2026-10-15)

- Scope: code only — the 154 git-tracked files under `cloud_pipeline/`. `bootstrap/` (3.5 GB, largest file 1.7 GB), `fallback/` (769 MB) and `dist/` (1.6 GB) stay out of Git.
- History: one snapshot commit whose message names the source repository and SHA; no subtree split.
- Layout: contents of `cloud_pipeline/` at repository root.
- Auth: HTTPS remote using the existing `gh` credential (SSH key from WSL is rejected).
- README: add a short "data not in this repository" section pointing to the handover archive `cloud_pipeline-20261009b.tar.gz` and its SHA-256; no storage location hard-coded. Only the pushed copy is edited; source repo files are unchanged.
- LICENSE: unchanged (MIT, swl007007); ownership is an IFPRI policy decision outside this task.
- Internal identifiers (`manuel-remote-sensing`, image URI/digest in OPERATIONS.md): kept. Repository is private and IFPRI-internal; these are Internal Use, not Confidential, and needed for image transfer.
- Canonical: source repo remains canonical; the IFPRI repo is a one-off snapshot. No new remote on the source repo.
- Pre-push checks: `py_compile` on all Python files, secret scan, file-size check (< 50 MB per file). No pytest run (operator choice).
- Add a minimal `.gitignore` (bootstrap/, fallback/, dist/, filled project.json, operator-state/, caches) and carry over the two `cloud_pipeline` rules from the source `.gitattributes`.

## Acceptance Criteria

- [ ] Remote `main` has exactly one commit; tree = HEAD `cloud_pipeline/` blobs + README note + `.gitignore` + `.gitattributes`.
- [ ] No file in the pushed tree exceeds 50 MB; no secrets matched by the scan.
- [ ] All pushed `.py` files pass `py_compile`.
- [ ] Remote tree file list and blob hashes verified against the local export after push.
- [ ] Source SHA, file inventory and check results recorded under `research/`.
