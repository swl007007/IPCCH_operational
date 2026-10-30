# CP0 requirement-to-evidence map

Status: CP0 draft (Executor, session 6a490ae1-ee00-43f9-bdfc-c887c9816c09). Planned evidence only; nothing below has been executed.
Spec: prd.md acceptance criteria AC1-AC40 (numbered in PRD order), R1-R66, Final convergence corrections FCC1-FCC10 = the ten bullets at prd.md:256-265 in order (FCC1=:256 ... FCC10=:265).
Status vocabulary: every row is **PLANNED** at CP0; no row has executed evidence yet. Executed evidence will be recorded per checkpoint as `EXECUTED <cp> <artifact/test id> <sha256/exit>` in a separate column added at CP3+; planned and executed are never merged into one cell.

Evidence class: **E** = executed local test/artifact required for acceptance; **R** = real research/cloud artifact (training under a reviewed packet); **D** = deferred live/full-area verification, reported as deferred and never marked passed.
Test paths under `cloud_pipeline/tests/` are proposed names; exact files are fixed at CP3 after GitNexus impact analysis.

| AC | Acceptance item (short) | Req | CP | Planned evidence | Class |
|---|---|---|---|---|---|
| AC1 | Model-matched training-error evidence; confidence formula/thresholds/missingness; max-phase proxy + bootstrap from new residuals | R31 | CP2 | research evidence files per horizon, hashes in package manifest; recomputation check script comparing formula on new evidence; unit tests of unavailable/single-month paths in delivery_outputs | R+E |
| AC2 | Real batch covers full 6,226 roster; missing rows fail; smoke covers declared subset; duplicate keys fail with keys | R32 | CP3 | `test_ipcch_feature_batch.py` roster/duplicate cases; CP5 smoke subset check | E |
| AC3 | Missing/unknown mode fails; smoke cannot write current or real stores; real rejects dummy | R36, R48 | CP3/CP5 | `test_delivery_request_v2.py` mode cases; smoke isolation test with fake store asserting no real-namespace writes | E |
| AC4 | Missing model columns fail before scoring; no inference-time fabrication | R19 | CP3 | batch validation tests (missing, duplicate names, extras ignored, reorder) | E |
| AC5 | Feature definitions/alignment/names/order/missingness agree with model contract | R65, R33, R58 | CP1/CP3 | CP1 schema pin (527 order hash); assembler unit tests per family vs research formulas on fixture rows; contract-hash equality test | R+E |
| AC6 | Dummy smoke leaves production current unchanged; isolated current replaced and preserved on failure | R16 | CP4/CP5 | publication tests on fake store; CP5 smoke run + failure injection | E |
| AC7 | Formal fitting uses real inputs only | R15 | CP1/CP2 | CP1 input manifest with hashes; training config records; no fixture path in packet | R |
| AC8 | Placeholders allow E2E smoke emitting dummy predictions; real cloud/full-area deferred | R14, R35 | CP5 | smoke run artifacts with mode=smoke; deferred list in final report | E + D |
| AC9 | Model identity/weight period/selection explicit; GPP training respects availability simulation | R11, R51, R57, R9 | CP1/CP2 | package manifest; GPP filter unit test + per-row availability counts in CP1 | R+E |
| AC10 | Nonfinite predictions fail with area/horizon/field | R18 | CP3 | inference unit test with NaN/inf injection | E |
| AC11 | Horizon failure preserves previous IPCCH current; success switches all three | R18 | CP4 | publication test with injected horizon failure | E |
| AC12 | Single-system publication; per-system provenance; partial success | R17, R47, R63 | CP4 | cross-system publication tests; run-summary status partial_success | E |
| AC13 | Inference-only without/with incompatible batch fails; exact batch consumed; generation failure stops inference, no fallback | R5, R19 | CP3/CP5 | request + batch tests; CP5 generation-failure route | E |
| AC14 | Only H2/H8/H14 weights + prepared features; no CH reference processing/rerun interface | R2, R20 | CP3 | code review + test that runtime imports no label/reference module; CLI surface inspection | E |
| AC15 | Invalid manifest rejected before any mutation | R17 | CP3 | validation tests asserting fake store untouched (write-count zero) | E |
| AC16 | Four operations have inputs/outputs/prereqs/failure; missing required climate source at O blocks | R5, R13, R43 | CP3/CP5 | operation-matrix tests; climate coverage blocking test | E |
| AC17 | Invalid/missing ACLED refresh fails, no store change, no keep fallback | R27 | CP3 | ACLED converter tests | E |
| AC18 | ACLED interval replacement without double counting; removes superseded; preserves outside | R25 | CP3 | converter interval-replacement tests | E |
| AC19 | Saved refresh becomes keep baseline; failed/dummy cannot replace; FEWS retention unchanged | R28, R29 | CP3 | store tests + FEWS regression suite | E |
| AC20 | ACLED keep keeps history, new months NaN, model-consistent features | R3 | CP3 | keep tests | E |
| AC21 | Legacy IPCCH job pre-activation cannot overwrite new current after activation (incl. mid-publication cutover) | R37 | CP4 | publication-time cutover check tests with CAS race on fake store | E |
| AC22 | FEWS regression unchanged; legacy FEWS requests accepted; inherit.ipcch rule exception | R6, R60, FCC9 | CP3/CP4 | existing FEWS suites green; new inherit tests | E |
| AC23 | Execution-month/origin/target mapping; matching availability; no oracle | R4, R7, R23 | CP1/CP3 | CP1 schema without oracle columns; date-derivation tests | R+E |
| AC24 | Smoke with FEWS operation rejected; real may compose four | R38 | CP3 | request tests | E |
| AC25 | Future M rejected; same-M rerun replaces; older-M current rejected at validation and publication; candidate exempt | R39, FCC6 | CP3/CP4 | request + publication recheck tests (UTC) | E |
| AC26 | Batch metadata: method ids, combination, M/O, mode, coverage ends, gaps; immutable unique | R40, R52 | CP3 | batch writer tests (no overwrite, unique id) | E |
| AC27 | Indicator-month persistence; later failure keeps saved months; reruns compute unsaved only | R41, R43 | CP3 | climate store tests with injected later failure | E |
| AC28 | ACLED keep with no real history rejected; first refresh covers lookback; Saturday weeks/interval/regions/mapping/month completeness | R44, R55, R56, FCC7 | CP3 | converter validation tests incl. event-free covered weeks | E |
| AC29 | Unrecorded/mismatched historical input rejected; runtime months append records | R45, FCC10 | CP3 | acceptance-manifest tests; smoke validates fixture acceptance records only | E |
| AC30 | Smoke reads fixture store + package only; candidate loads in smoke, rejected in real; checksum + accepted | R48, R51, FCC10 | CP3/CP5 | package-manifest tests; smoke read-isolation test | E |
| AC31 | GPP 404-only unpublished; other errors block; v3 all-years history; update-log filter | R49, R54, R57, FCC10 | CP1/CP3 | GPP ledger tests with fake HTTP; CP1 filter evidence keyed on simulated run date (not source month) | R+E |
| AC32 | Per-system lock rejects same-system; different systems parallel | R50, FCC2 | CP3/CP4 | lock tests incl. partial acquisition release | E |
| AC33 | Research families / snapshot / WFP / nightlight keep-refresh + warnings, no block on coverage; only 13 climate bases required | R59, R62, R64, R65, FCC8 | CP3 | per-family store tests; snapshot atomic replacement test | E |
| AC34 | FEWS inference-only references prepared_snapshot; no FEWS batch artifact | R60 | CP3 | request + FEWS route test | E |
| AC35 | Post-processing unchanged; 2027 year dummies all-zero documented | R61, R58 | CP3/CP6 | existing inference tests unchanged; assembler test for 2027 dummies; doc | E |
| AC36 | Cross-system inheritance of different-month delivery; candidate no pointer move, no activation | R63, R66 | CP4 | publication tests | E |
| AC37 | Inference-only + any IPCCH refresh rejected before mutation | R19, FCC1 | CP3 | request tests for ACLED/research_inputs/history_snapshot/WFP | E |
| AC38 | CAS conflict fails without retry/rescoring; batches/retained data remain usable | FCC3 | CP4 | concurrent CAS test on fake store | E |
| AC39 | Legacy FEWS-only publication after activation inherits new IPCCH member; conflicting inherit rejected | FCC4, FCC9 | CP4 | legacy-path publication tests | E |
| AC40 | Promote/resume reject new-contract candidates; legacy FEWS maintenance supported | FCC5 | CP4 | promote/resume tests | E |

## Requirement coverage R1-R66 (all PLANNED)

| Req | Requirement (short) | CP | Planned check | Linked AC |
|---|---|---|---|---|
| R1 | Integrate shared monthly/seasonal algorithms | CP3 | port inventory in cp0-climate-acled-sources.md; ported-module unit tests on fixture rasters/tables; method ids recorded | AC8,AC16 |
| R2 | GPP v3; reference periods training-only; inference takes weights+features | CP1/CP3 | runtime import/CLI surface check: no label/reference modules; v3 endpoint contract test | AC14 |
| R3 | IPCCH ACLED regional aggregates; keep semantics; FEWS ACLED unchanged | CP3 | keep tests (no forward fill); FEWS ACLED regression suite | AC19,AC20 |
| R4 | Train H2/H8/H14 final stage, targets 2026-01..10, cutoffs 2025-11/2025-05/2024-11 | CP1/CP2 | CP1 packet with context table; CP2 MLflow run ids + record files showing cutoffs/targets | AC23 |
| R5 | Four composable operations; generation saves batch; failure stops dependent inference | CP3/CP5 | operation-matrix tests; CP5 three routes + generation failure route | AC13,AC16 |
| R6 | Preserve FEWS NET behavior | CP3/CP4 | existing FEWS suites green unchanged; byte comparison of FEWS outputs on fixture | AC22 |
| R7 | No future-realized oracle features | CP1/CP2 | 527 schema diff vs H6/H12 539 showing 12 oracle columns removed; alignment audit per family | AC23 |
| R8 | Incremental climate; historical months not rewritten | CP3 | store tests: saved month immutable on later provider arrival | AC8,AC27 |
| R9 | GPP retain/unpublished missing/fill-only-unpublished; no batch rewrite | CP3 | GPP ledger + fill tests; batch immutability test | AC9,AC31 |
| R10 | Hyperparameters H0->H2, H6->H8, H12->H14; no HPT | CP1/CP2 | CP1 pinned hyperparameter table with source hashes; CP2 run params equality check | AC9 |
| R11 | Fixed three-model combination referenced explicitly; required for generation-only | CP3 | request/batch tests: combination mismatch rejected; generation-only records combination | AC9,AC13 |
| R12 | Final-stage weights directly; no refit; no performance gate | CP2 | CP2 lineage: delivered weights == trained run artifacts (sha256) | AC9 |
| R13 | Missing required climate source at O blocks; per-area missingness continues | CP3 | coverage blocking tests; per-area NaN counted in summary | AC16 |
| R14 | Runnable dummy placeholders; local small-area smoke; mode=smoke outputs | CP5 | smoke artifacts inspected; fixture store manifest | AC8 |
| R15 | Real inputs only for fitting | CP1/CP2 | input manifest hashes; no fixture paths in packet | AC7 |
| R16 | Dummy isolated; same publication path; isolated current replacement rehearsal | CP4/CP5 | fake-store replacement + failure preservation tests; smoke rehearsal | AC6 |
| R17 | Independent systems; partial success; invalid manifest rejected whole | CP3/CP4 | partial-success test; invalid-manifest zero-mutation test | AC12,AC15 |
| R18 | Three-horizon atomic release; nonfinite fails | CP3/CP4 | horizon failure + NaN/inf tests | AC10,AC11 |
| R19 | Inference-only batch validation rules | CP3 | batch validation test set (combination, cutoff, schema, dummy/real, reorder, duplicates, unparseable/inf, extras, conflicts) | AC4,AC13,AC37 |
| R20 | No retrospective rerun/rollback interface | CP3/CP6 | CLI/request surface review | AC14 |
| R21 | Historical GPP availability evidence or conservative unavailability (training only) | CP1 | filter implementation + per-row availability counts | AC9,AC31 |
| R22 | Manual submission; no scheduler | CP6 | surface review: no schedule added | — |
| R23 | Single M; O=M-2; targets M/M+6/M+12; public lead vs model horizon | CP3 | date derivation tests (M=2026-10 example); metadata fields test | AC23 |
| R24 | ACLED refresh from manual regional CSV referenced in manifest | CP3 | converter reads reference-format header fixture | AC17,AC28 |
| R25 | Declared-interval replacement | CP3 | interval replacement tests | AC18 |
| R26 | Declared start/end; rows within interval | CP3 | validation tests | AC28 |
| R27 | Refresh failure: no store change, no keep fallback | CP3 | failure tests | AC17 |
| R28 | Keep uses most recent saved real history; dummy never updates | CP3 | store tests | AC19 |
| R29 | Saved refresh retained despite downstream failure | CP3 | failure-after-save test | AC19 |
| R30 | Training in food-crisis-research with existing MLflow workflow; no duplicate trainer | CP1/CP2 | packet uses existing entrypoint; operational repo diff has no trainer | AC9 |
| R31 | Confidence + max-phase evidence recomputed with new weights | CP2/CP3 | evidence files, hashes; diagnostics tests incl. insufficient-history | AC1 |
| R32 | Fixed 6,226 roster/geometry; full coverage; duplicates fail | CP1/CP3 | roster hash in package; batch tests | AC2 |
| R33 | Completed growing seasons only | CP1/CP3 | season-eligibility tests identical to research rule | AC5 |
| R34 | Multi-source ensemble with available sources; single-source rule | CP3 | ensemble tests: >=2 finite sources → equal-weight mean and population SD (ddof=0) matching shared SPI/SPEI code; exactly 1 source → mean=value, n_sources=1, SD missing (not 0); unavailable provider excluded, never zero-filled, n_sources recorded; zero available providers for a required base at O blocks real generation; auth/download/compute failures raise processing failure (block) and are not classified as unavailability | AC16 |
| R35 | No QA/merge gate; minimal assembly | CP6 | surface review | AC8 |
| R36 | Explicit smoke/real mode; smoke labels; real rejects dummy | CP3/CP5 | request + labelling tests | AC3 |
| R37 | New version; legacy FEWS kept; post-activation legacy IPCCH rejection; publication-time check | CP3/CP4 | routing + cutover tests | AC21,AC22 |
| R38 | Smoke IPCCH-only | CP3 | request test | AC24 |
| R39 | Future M rejected; older-M current rejected at validation and publication | CP3/CP4 | UTC month tests + publication recheck | AC25 |
| R40 | Delivered script methods; method ids recorded; no equivalence gate | CP3 | batch metadata test | AC26 |
| R41 | Indicator-month persistence | CP3 | persistence test | AC27 |
| R42 | Smoke uses real delivered combination | CP5 | smoke loads CP2 package (hash match) | AC8 |
| R43 | Lookback months attempted; gaps recorded; block only at O | CP3 | lookback gap tests | AC27 |
| R44 | ACLED init = ordinary refresh covering lookback; keep without history rejected | CP3 | tests | AC28 |
| R45 | Acceptance manifest | CP3 | acceptance tests | AC29 |
| R46 | Activation one-way; no deactivation | CP6 | surface review | — |
| R47 | File names/columns preserved; per-system provenance added | CP4 | delivery layout golden test vs existing outputs | AC12 |
| R48 | Smoke fully read-isolated | CP5 | read-tracing fake store test | AC30 |
| R49 | GPP 404-only unpublished | CP3 | fake HTTP tests | AC31 |
| R50 | Per-system lock | CP3/CP4 | lock tests | AC32 |
| R51 | Package manifest; real=accepted; smoke may use candidate | CP2/CP3 | manifest + loader tests | AC30 |
| R52 | Immutable unique batches | CP3 | batch tests | AC26 |
| R53 | Short ACLED refresh accepted after init with warning | CP3 | warning tests | AC28 |
| R54 | IPCCH GPP history = training panel v3 all years | CP2 | delivered history hash == training panel column extract | AC31 |
| R55 | ACLED converter conventions + delivered tables | CP2/CP3 | table hashes in package; converter parity test vs research build_acled_agg on fixture | AC28 |
| R56 | ACLED coverage completeness; declared regions | CP3 | event-free covered week test | AC28 |
| R57 | GPP update-log filter in training | CP1 | filter test with log dates; counts per context | AC31 |
| R58 | Year dummies retained; 2027 all-zero documented | CP1/CP6 | schema contains year_2014..2026; assembler 2027 test; doc | AC35 |
| R59 | Research-prepared families keep/refresh | CP2/CP3 | initial history delivered + store tests | AC33 |
| R60 | FEWS operations map to prepare/prepared_snapshot | CP3 | route tests | AC34 |
| R61 | Post-processing unchanged | CP3 | existing inference tests unchanged | AC35 |
| R62 | Reported-phase snapshot keep/refresh atomic | CP2/CP3 | snapshot tests incl. FCC8 removal of prior records absent from replacement; older-than-O warning | AC33 |
| R63 | Single pointer; cross-system different-month inheritance | CP4 | inheritance tests | AC36 |
| R64 | WFP/nightlight R40/R54 pattern | CP3 | store/converter tests | AC33 |
| R65 | Alignment; only 13 climate bases required | CP1/CP3 | alignment audit; blocking classification tests | AC5,AC33 |
| R66 | Candidate publication without pointer move; not promotable | CP4 | candidate + promote rejection tests | AC36,AC40 |

Final convergence corrections (prd.md:256-265) → AC: FCC1 :256 inference-only + any IPCCH refresh → AC37; FCC2 :257 lock keys/partial acquisition → AC32; FCC3 :258 CAS conflict no retry → AC38; FCC4 :259 every current path inherits exact current members → AC39, AC22; FCC5 :260 promote/resume reject candidates → AC40; FCC6 :261 older-M only for current, candidate keeps future check → AC25; FCC7 :262 first ACLED refresh lookback + covered event-free weeks → AC28; FCC8 :263 history_snapshot full atomic replacement incl. removal of absent records → AC33; FCC9 :264 legacy v1 inherit.ipcch = current member; R63 checks for new-contract member → AC22, AC39; FCC10 :265 smoke validates fixture acceptance only; GPP pre-log rule keyed on simulated run date → AC29, AC30, AC31.

## Deferred (class D) — reported, never marked passed

- Live GEE/cloud exports, full-area (6,226) real generation and resource validation (R14).
- Real retained-store initialization from delivered baseline climate assets (placeholders until delivered).
- Actual production publication / activation and live legacy-cutover behaviour (tested only on fake stores).
- Production rollback (source recovery and fake-store tests are not production rollback validation).


## Execution index — Supervisor update 2026-10-30

The tables above preserve the original CP0 planned checks; they are not a claim that execution has not started. Final per-row evidence mapping remains a CP6 deliverable. Current checkpoint evidence is deliberately separate:

| Checkpoint | State | Executed evidence | Remaining acceptance boundary |
|---|---|---|---|
| CP0 | accepted | cp0-supervisor-review.md; execution-protocol.md | none for CP0 |
| CP1 | accepted | cp1/supervisor-review.md; pinned recipes and research commit9aa9e54 | none for CP1 |
| CP2 | in progress | cp2/supervisor-review.md; cp2/cp2-package.md; cp2/package-check/runtime_check_real_r2.json; cp2/cp2-handoff-inputs.md and r5 delta | final immutable asset binding and explicit acceptance; runtime fixed-asset integration |
| CP3 | in progress | cp3-supervisor-review.md; cp3/cp3c2-acled.md; cp3/cp3c3-climate-core.md; cp3/cp3d-assembly-initial.md;99-test receipt plus independent targeted repair checks | complete parity verdict, batch/inference/generation entrypoints and integrated FEWS preflight |
| CP4 | pending | none accepted | publication, locks/CAS, compatibility/cutover/candidate tests |
| CP5 | pending | none accepted | local two-country smoke with actual three-model combination |
| CP6 | pending | none accepted | complete R/AC/FCC executed evidence map, regressions, operator handoff, clean commits |

CP2 raw-score probes and CP3 historical feature compatibility checks do not substitute for CP5. Offline Earth Engine graph tests do not establish live private-asset access or raster numerical replay. Deferred checks listed above remain deferred.
