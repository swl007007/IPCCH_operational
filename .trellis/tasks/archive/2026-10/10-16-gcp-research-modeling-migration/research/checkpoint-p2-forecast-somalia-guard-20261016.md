# Checkpoint P2c: forecasting and Somalia-oracle packages, assistant spend guard (written 2026-10-16 03:45:24 EDT by `date`)

All evidence here is local Linux/WSL. No cloud resource was created and no provider was called.

## Packages and replay

| Family group | Versions | Replay round | Result |
|---|---|---|---|
| Forecasting batch/launch (compact global/somalia + 2026 extensions, origin-safe climate/weather, launch) | 56 | supervisor round `p2-packages/replay-forecast-602558c-supervisor/` (packages from native `602558c`), adopted | 56/56 pass, 6,656 rows, max err 2.22e-16, 0 routing mismatches, 0 phase changes, 0 stale |
| Somalia-oracle v2 q3 / v3 validity / v4 calibrated-D | 23 / 24 / 8 | `p2-packages/replay-somalia-e8d5160/` | 55/55 pass, 10,360 rows, max err 2.78e-16, 0 routing mismatches, 0 phase changes, 0 stale |

- **Adoption of the supervisor's forecast receipts:**
  - The forecast packages were not rebuilt after that round.
  - The executor's `summarize` was run over the supervisor's per-package reports. Every receipt's `package_json_sha256` equals the current package (`summary-executor.json`).
  - The supervisor's own `summary.json` is kept unchanged beside it.
- **The original saved `q3_final` NaNs (360) are preserved,** not filled; this was reconciled independently by the supervisor (S18).
- **Somalia v4:** the supervisor's independent probe on the augmented H0 version (largest override count, 49) passed 709 rows (`scratch/replay/supervisor-somalia-v4.json`).
- **Package bytes:** forecasting 2.66 GB and somalia 1.98 GB under native `packages/`, plus the earlier 1.89 GB.

### Somalia v4 specifics (native `e8d5160`, `7e1c391`)

**Override inputs.** Test rows exposed to their job's test families use the run's saved recomputed-history feature rows (`features/final_override_features.csv.gz`) and baseline/support (`selection/history_overrides.csv.gz`, role `test_prediction`).
- Both are recorded plan members (sha `ca0ed470…` 48,260 B; `00847010…` 538 B; also in the run manifest's `written`).
- They are locality-checked and sha-verified before being read, copied into `deps/source/`, and listed in `package.json` `source.override_dependencies`.

**One-to-one correspondence.** Within each version's served (job, area, target) set the two files must correspond one-to-one. Duplicates, one-sided keys and keys absent from the feature matrix are refused.

**Precision.** The X row keeps the float32-saved feature value. A separate `residual_baseline` input carries the float64 context baseline that the residual branch adds. Support (`context_base_ok`) must agree with the recomputed finite/source-ord test.

**Calibration.** Calibration availability is frozen per original job. **Tests:** `test_packages_somalia.py` has 8 tests, including correspondence (missing, duplicate, wrong-role) and baseline precision/support.

**Rebuild history.** The previous v2/v3 package directories came from two overlapping executor rounds (`/tmp/round_fc.sh` and `/tmp/round_som.sh`, both with `rm -rf`). Both rounds were stopped. All 55 were rebuilt sequentially by one process (`/tmp/round_som2.sh`, log `scratch/replay/round-som2.log`) at the committed code, and then replayed.

## Registry ledger (`ledger/registry_ledger.json`, regenerated)

- 242 versions, key set equal to the snapshot.
- **147 packaged_replay_passed:** GeoXGB P6 8, yearly 12, AlphaEarth 16, forecasting 56, Somalia 55.
- **23 weights_retained_package_pending:** Somalia v1 `somalia_oracle_information` 15, and window-probe reused comparators 8.
- **72 missing_weights_tracking_only.**

The window-probe comparators cannot alias the existing P6 packages. Their `regional_ungated` arm needs 77 local P6 units that no current package carries (`remaining-packages-supervisor.md`). The `ledger_resolutions.json` link to P6 units identifies weights only; packaging is pending.

## Assistant spend guard (native `40f43d4` + `44350b6`, local tests only)

Following `gateway-budget-supervisor.md`, the native Gateway REJECT policies are supporting signals only. `research_cloud/service/guard.py` adds the small PostgreSQL-backed guard that design.md allows; no Redis and no separate gateway.

- **Egress:** `mlflow.gateway.providers.utils._aiohttp_post` is wrapped (one `session.post` with a total timeout and no retries, as reviewed by the supervisor). Only the pinned Vertex Gemini `generateContent` / `streamGenerateContent` URL is admitted; everything else gets 403. `MLFLOW_GATEWAY_ALLOWED_PROVIDERS=vertex_ai` is required at install, which excludes LiteLLM, the one provider that bypasses the choke point.
- **Payload contract:**
  - Allowed parts: text, functionCall and functionResponse.
  - Tools: function declarations only.
  - generationConfig: a fixed key set.
  - Refused: inline/file data, cached content, grounding/search/code tools, and non-text modalities or mime types.
  - candidateCount is forced to 1 and maxOutputTokens is clamped.
- **Reservation (supervisor-proposed simplification; no token estimate):** each call reserves the model's full accepted input context at the highest applicable text input rate, plus the clamped maxOutputTokens × `output_reservation_factor` at the output rate. Google documents that maxOutputTokens includes thinking; the factor covers user-reported thinking overshoot (an evidenced assumption, not a guarantee). CountTokens is not used, because Google calls it an estimate.
- **Quantified for the existing selected model** (Gemini 3.8 Flash, `global`; unchanged):
  - Inputs:
    - Vertex model page: 1,048,576 input / 65,536 output tokens.
    - Cloud Billing catalog list price: $1.50/M input, $7.50/M output (catalog `scratch/p3/skus/vertex.json`; not a quote).
  - With a cap of 8,192 output tokens and factor 2, a call reserves about $1.70 ($1.573 input + $0.123 output).
  - Under the USD 10 assistant allocation, admission stops at about $6.60 charged with 2 calls in flight, or about $8.30 with 1.
  - The Gemini API page lists introductory pricing; Vertex list prices may differ and must be confirmed before provisioning.
- **Admission:** a transaction-scoped advisory lock covers sum and insert. A call is admitted only if this Pacific-time month's charged total plus the reservation is within the allocation, and in-flight calls are under `max_in_flight`. Charged total means settled actual cost plus open or uncertain rows at max(reserved, observed).
- **Settlement:** from raw `usageMetadata`, with thinking and tool-prompt tokens counted. `totalTokenCount` must be present and equal prompt + candidates + thoughts + tool-use prompt exactly (Vertex semantics).
  - An unexplained difference stays `uncertain`. This was a supervisor finding on `40f43d4`: a total of 10,000 against 15 itemized tokens had been accepted. It was fixed, with a regression test.
  - Missing, malformed or negative usage, or a stream without a finish, also stays `uncertain`, charged at its reservation.
- **Timeout alignment:** a `reserved` row stops counting as in flight only after `request_timeout_s` + grace. The guard enforces that deadline on stream and JSON reads. Install requires `MLFLOW_GATEWAY_ROUTE_TIMEOUT_SECONDS` ≤ `request_timeout_s`. Expired rows still count toward spend.
- **Fail-closed:** any guard, config or ledger error refuses the call with 503.
  - `hook.py` loads through a `.pth` in every service interpreter; any failure exits the interpreter (code 78).
  - The assistant patch is vendored from `Food_Crisis_Cluster@6c1ebf72` with a raising `apply()` and `patch_markers()`.
- **Tests:** `test_service_guard.py` has 13 tests (12 before the total-reconciliation regression). They cover config validation, the payload contract, bounds, the reservation amount and usage parsing. Against the disposable PostgreSQL they also cover:
  - allocation and uncertain charging;
  - concurrency expiry versus spend;
  - stream settlement with thinking tokens;
  - no-finish or malformed usage;
  - refusals before any upstream call (URL, modality, size, DB down);
  - a hung stream cut at the deadline.

  The supervisor independently ran the 12 on `40f43d4` (12/12). The executor ran the 13 after the fix (13/13). No skips, no provider calls.
- **Not yet verified:**
  - the launcher;
  - the service start-up in a fresh interpreter;
  - HTTP authentication/permission behavior;
  - a live Vertex call;
  - actual thinking-token billing;
  - regional Vertex prices.

## Next

1. Service launcher (`start.py`): fail-closed start-up checks, a deterministic assistant config, and the `mlflow server --app-name basic-auth` uvicorn path with 1 worker. Then a local HTTP access rehearsal against the disposable PostgreSQL: owner, reader, job writer, assistant and anonymous access, plus assistant allow/deny with a fake upstream.
2. Somalia v1 (15), window-probe comparators (8, with the 77 P6 local units), pop-v1 (`remaining-packages-supervisor.md`).
3. SQL import rehearsal, training adapter, cost estimate, URI map.
