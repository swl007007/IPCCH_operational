# Task 10-30 reproducible tool sources (task-owned evidence copy)

Byte copies of the pinned staging sources used by the released packets (origin: staging/ipcch-origin-ablation-20261030 in
the research workspace; MANIFEST.tsv maps every file to its origin with sha256). Excluded on purpose: the three runtime
modules of the overlay context (identical bytes committed in control-plane-origin-ablation 7023d10/868db9f: pooled d2c07d7d,
features eace18fd, dataset_input 2b74098a; shas in image-overlay-origin.context-record.json), the draft render (the final
render is kept), bytecode, and all data (predictions/harvests stay in scratch and GCS).
- staging-tools/: recipe maker, no-fit verifier, overlay context builder, lineage proof, independent recompute (+ tests)
- build-packet/, image-overlay-context/: released build packet r1 and its context (minus modules)
- job-packet/: released formal-job packet r1 (configs, manifests, specs, plans, render-final, helpers, diffs, SHA256SUMS)
- final-packet/: released final read-only packet r1 and the cleanup tool (+ refusal tests, real-artifact exercises, base-10-28 diffs)
- recipes-final-r2/: gate-checked candidate recipes and local manifests; checks/: lineage, no-fit verifier and test receipts
