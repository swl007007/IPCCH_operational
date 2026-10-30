# CP0 checkpoint — Executor record (awaiting Supervisor review)

- Spec: prd.md / design.md / implement.md at commit ace3e1211c4eedcfded82dc91ecf0654b5c36afb; execution-protocol.md (untracked, Supervisor-authored, incl. cloud preauthorization update).
- Branch/SHA: feat/ipcch-validity-feature-inference @ ace3e12, in sync with origin; working tree before CP0 had only the untracked protocol.
- Executor identity: Claude Code, model claude-opus-5-5[1m] (Opus 5.5 1M), session 6a490ae1-ee00-43f9-bdfc-c887c9816c09 (CLAUDE_CODE_SESSION_ID and Herdr agent_session agree), Herdr pane w1A:p2 / tab w1A:t2, cwd = repository root. Supervisor Codex pane w1A:p1. (Background-task temp paths carry an older process directory id bfb1fb18…; the live session id is 6a490ae1.)
- Backups: tag backup/ipcch-pre-refactor-20261030 peels to 422f921 (local and origin); origin/feat/october-cloud-delivery = 422f921; bundle /home/swl007007/backups/ipcch-operational-pre-refactor-20261030/repository.bundle `sha256sum -c SHA256SUMS` OK and `git bundle verify` exit 0.
- Environments: operational tests → ~/.venvs/fewsnet-test-lock-20261022 (57/57 exact lock pins + pytest 9.1.1); research → image lock (separate; see cp1-plan.md §1).
- Commands run: read-only git/sha256/herdr/env inspections; `pytest --collect-only` by a scout (612 collected, 1 pre-existing collection error D6). No product edits, no training, no cloud/MLflow/network operations, no native task start, no Trellis Audit, no commits.
- Process deviation (disclosed): three read-only scouts were dispatched with the trellis-research role before the coordination correction; they wrote only to research/ and were stopped early with bounded findings. Afterwards: no further trellis-research/implementation subagents.

## Changed files (all task-local, uncommitted)

| file | purpose |
|---|---|
| implement.jsonl, check.jsonl | populated context manifests (15/16 entries) |
| research/cp0-requirement-evidence-map.md | AC1-AC40, R1-R66, FCC1-FCC10 (prd.md:256-265) → planned evidence; all PLANNED |
| research/cp0-runtime-seams.md | cloud_pipeline seams (scout) |
| research/cp0-research-training-inventory.md | research training inventory (scout; overlay match evidence added by Executor) |
| research/cp0-climate-acled-sources.md | climate/ACLED/research-family sources (scout) |
| research/cp1-plan.md | concrete CP1 plan: isolation/capture manifest, research changes C1-C7, NaN contract, measurements, packet shape, discrepancies D1-D7 |
| research/cp0-checkpoint.md | this record |
| PROGRESS.md (repo) | appended CP0 ledger entry |

## Retained risks / open items for Supervisor

S1 ACLED override precedence (R55 text vs research converter) needs a ruling before the converter port. C6 evidence key multiplicity to be measured at CP1. D6 FEWS partition CRLF resolution planned (attribute-only), closed only by executed evidence. Live MLflow/GCS state not yet read (now preauthorized read-only; deferred to CP1).

## Next action

Supervisor reviews CP0. On acceptance: commit CP0 artifacts (protocol + manifests + research), then native `task.py start`, then CP1 per cp1-plan.md.
