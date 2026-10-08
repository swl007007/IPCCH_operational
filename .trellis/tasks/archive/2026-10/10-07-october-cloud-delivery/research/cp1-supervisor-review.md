# CP1 supervisor review (in progress)

Baseline: `1fa71a3`. Review is against approved design and the CP0 disposition. CP1 accepted after the corrections and independent verification below; this is not full delivery or model acceptance.

## Independent converter parity

Using `/tmp/ipcch-oct-cp1/bin/python`, loaded the original converter source with `git show 1fa71a3:tools/refresh_h5_inputs.py` into a temporary Python module, and compared its aggregate DataFrames with the edited converter using `pd.testing.assert_frame_equal(..., check_exact=True)`. Inputs were the unchanged v3 source exports in `Outcome/model_delivery/202609_h5/20260923_country_confidence_v3/sources/`; default cutoff remained 2026-04. Results:

- FEWS WFP: exact equality, 569 supported country-months.
- IPCCH WFP: exact equality, 560 supported country-months.
- ACLED: exact equality, 5,787 aggregated admin3-month rows.

This verifies existing default aggregate values; it does not test October assembly, new independent overlay choices, remote preparation or model scoring.

## First review feedback to executor

The initial fill implementation prematurely labelled absent base values as model-imputed, despite saved FEWS imputation applying to final lag/window features. Requested separation of base provenance from actual final-feature imputation, with package/feature-specific audit and regression coverage. Also requested nonfinite-input handling, nonnegative integer lags, per-polygon dependency completeness and explicit source checksum. Executor is addressing these before checkpoint delivery; acceptance requires reading the final diff and checks.

## Independent read-only checkpoint review

Two bounded reviewers inspected the completed CP1 slice and ran the 41 raw/fill and 35 manifest tests. All passed, but four uncovered cases require correction before acceptance:

1. `carry_forward_base_series`: a wholly missing feature or empty observations creates incompatible as-of join key dtypes and raises `MergeError` before the intended final-feature fallback decision. The reviewed fill-file SHA256 was `54abdf6426982a8608801cc101edba087b77d7374dc45eb838dcf2399d6b4dfd`.
2. Unavailable diagnostics reject explicit `evidence: null`, contrary to design §4.
3. Top-level horizons accept floats and mixed types can leak `TypeError`; require integer horizons and a contract error.
4. `prepared_at: 2026-10-03Z` passes despite not containing a time; preparation cutoff must be a real RFC3339 UTC timestamp.

All four were returned to the bound executor through Herdr. The existing horizon test failure is recorded separately in PROGRESS: baseline `1fa71a3` reproduces it, because source h5 support postdates the 0/6/12-only assertion. It must not be silently counted as a passing full suite or repaired by changing scientific scope.

## Correction verification

Supervisor read the final fixes: explicit integer as-of keys handle empty/all-null observations; unavailable diagnostics require explicit null evidence; system/horizon lists enforce exact element types; preparation timestamps require full date/time/UTC syntax plus calendar parsing. Independently executed:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/ipcch-oct-cp1/bin/python -m pytest tests/test_refresh_h5_inputs.py tests/cloud/test_causal_fill.py tests/cloud/test_delivery_manifest.py tests/cloud/test_manifest_contract.py tests/cloud/test_run_state.py tests/cloud/test_release_writer.py tests/cloud/test_release_conflict.py tests/cloud/test_release_manifest_contract.py tests/cloud/test_release_consumer.py -q -p no:cacheprovider
```

Result: **137 passed in 3.65s**. Executor's larger suite: 375 passed, one live-GCP skip and the independently baseline-reproduced horizon failure. `git diff --check` passed. Existing converter AST changes are only `wfp_aggregates`, `conflict_aggregates`, `replace_sources`; seven other pre-existing functions remain identical. CP1 is accepted for its limited input-contract scope; actual scoring integration, model acceptance and cloud execution are still pending.
