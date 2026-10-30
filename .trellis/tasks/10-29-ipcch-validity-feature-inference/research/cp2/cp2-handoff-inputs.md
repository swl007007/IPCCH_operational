# CP2 — handoff fixed assets, initial histories and R45 acceptance entries (r4)

Builder: `R/control-plane-h2h8h14-pkg/research_cloud/packages/ipcch_handoff_inputs.py` (package branch). It calls the SAME
pinned research loaders that built the final matrices (`vf.load_sources`, `load_idp_local`, `country_table`) on the
pinned inputs of `research/cp1/recipes/manifest-local-h02.json` (identical across H2/H8/H14 except the per-horizon
`freeze`, not used here), the final arm's `history_observations.csv.gz` (content identical across horizons) and the ACLED
work tables. Output (local, large data stays in scratch): `R/scratch/h2h8h14-final/handoff-build/out-r4`, 52 files,
2.20 GB. Copied here: `handoff-inputs/handoff_manifest.json` (sha256 2c7dd2c0…), `acceptance_entries.json` (27d6f744…,
51 entries, acceptor/accepted_at EMPTY for the explicit acceptance act), `coordinate_spread.csv`, build logs.

Contents: exactly 6,226 roster admin_codes (static29; roster.csv sha256 9ff2c420212bc8ec…); static29, AE descriptors,
area_identity (iso3/iso2/lat/lon), season_windows (149,424) + derived season_calendar, the 7 ACLED tables (byte copies);
climate monthly/seasonal ensemble histories for 13 bases (value/n_sources/ens_sd from the delivered tables); GPP_mean
(corrected v3 interim, R54), nightlight_mean, WFP_Price, food_price_index_WB, nino34_anom, 4 bbg composites (interim, as the
training grid holds them, per-area contiguous span incl. NaN months); idp_national, idp_local (idp_ffill6); history
snapshot (44,969 original reports; report_month = nominal month used by training selection, availability_month = raw-panel
storage month, preparation_cutoff = last raw-panel month). ACLED weekly store: no initial history (R44).

Roster report: area 1315 is the only out-of-roster admin in every family, dropped and counted. Roster areas absent from a
family (NaN features, never required): GPP_mean 136, WFP_Price 1,212, food_price_index_WB 1,597, idp_local 1,451,
history_snapshot 2; all other families cover the full roster.

Decisions recorded:
- lat/lon: the raw panel repeats one coordinate per area up to float formatting; per-area spread asserted <= 1e-9
  (max 5.0e-11, `coordinate_spread.csv`); the latest raw-panel month's value is the constant (r1 FAILED on my stricter
  exact-equality check: `build-r1-FAILED-latlon-noise.log`).
- season_calendar: the GEE calendar asset is unreadable; a per-admin s1/s2 calendar (sos/eos month-day, cross_year,
  valid) is derived from the delivered windows, required constant per admin-season, and must reproduce every delivered
  window with the seasonal script's exact_date rule: 12,452 admin-seasons, 149,424/149,424 windows reproduced. It supplies
  windows for season years after 2026.
- audit/ files are review evidence, not runtime inputs, and have no acceptance entry.

Not yet done: operational loader that verifies these files against acceptance records (R45) and initialises the retained
stores (CP3 assembly/stores work); explicit acceptance of the entries.
