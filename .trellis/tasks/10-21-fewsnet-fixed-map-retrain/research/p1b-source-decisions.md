# Supervisor source decisions after P1b, 2026-10-22

This resolves the source-method questions in `p1b/p1b-checkpoint.md`. It does not yet authorize fitting: finish September EVI integration and bind the final dataset/audit/source snapshot first. `supervisor-p1b-input-verification.json` verifies the initial frozen panel's label edits, hashes and horizon eligibility.

## Nightlight: restore the trained sum definition

Accepted as an integration bug fix within the unchanged FEWS feature definition. The supervisor inspected the original scaffold notebook, SHA256 `49ea1acc16bc8babb956faeaaa09596412b9be4917197b28ce542b92586b81c8`: cell 1 reads `nightlight_sum_extraction_results.csv` into the misleadingly named `df_nightlight_mean`; cell 19 melts those values. The combining notebook, SHA256 `0583c74c54190236f692c9cfa0c32f52228d1a4e8085517d12104e51a1f8edad`, cell 3 renames that column to `nightlight`. This directly supports sum and is stronger evidence than distribution ratios alone.

Correct the new release's overlay to use `avg_rad__sum`; retain the 123-feature contract, old source files and accepted outputs. Record the new assembly runtime/mapping explicitly and test known old snapshot compatibility. Do not present the prior mean-based output as newly recomputed or silently change its provenance.

## FLDAS April: replace carried inputs with observed April values

Accepted for the 5131 areas with reliable April observations, retaining the existing carried values for the remaining 587 with disclosure. The original notebook cell 24 explicitly forward-fills FLDAS after the monthly scaffold join; cell 25 maps the bands to Rainf/Tair. The supervisor independently checked both fields: all 5718 April values equal March exactly. Receipt: `supervisor-fldas-carry-evidence.json`.

This combination supports classification as carried input, not a revision of complete April observations. The original raw extraction CSV referenced by notebook cell 5 was unavailable at its recorded local path; no direct check of that raw file's April coverage is claimed. Preserve the keyed replacements and this evidence limitation.

## WFP: preserve historical definitions and disclose unsupported gaps

Accept retaining complete historical values and leaving earlier gaps missing where the earlier construction cannot be reproduced reliably from the available source evidence. Pre-2025 values show materially different scales; current MoM values must not be inserted into an unverified historical definition solely because the column names match.

The verified September overlay establishes the compatible MoM path from February 2025 onward (`bootstrap_vs_training.json` and the archived raw-upload contract). A few January values near 100 do not by themselves establish the same definition. Describe the earlier definition as incompatible or unverified, not a fully reconstructed historical formula. If direct source evidence establishes additional compatible earlier keys, include them and regenerate the input freeze before fitting. No rewrite/harmonization of complete old values is authorized by this decision.

## GOSIF and September EVI

Preserve v2 history; use v3 for the 2025 additions only. Guard planning/acquisition against silently refetching pre-2025 history from v3 and retain accurate mixed-version source metadata. Existing prepared references remain immutable.

The supervisor queried the September MOD13A3 asset metadata: `updateTime=2026-10-21T08:07:17.666923Z`, supporting the non-label source cutoff; see `supervisor-evi-provider-metadata.json`. Export task `TEE3NHA7YUJMWU7LHH2KTKOS` was RUNNING at 06:04:51Z. Final successful extraction, panel integration and compatible prepared snapshot remain pending. Release-time selection is still remote off / FEWS on / IPCCH off.
