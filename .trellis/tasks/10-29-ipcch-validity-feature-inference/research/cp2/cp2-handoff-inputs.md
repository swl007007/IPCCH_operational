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

## r5 (Supervisor acceptance-withheld fixes) — pkg branch dac4a0a
Output `R/scratch/h2h8h14-final/handoff-build/out-r5`: 58 files, 2,271,631,220 bytes; handoff_manifest.json sha256 e6e3ebc6…f5c97b4, acceptance_entries.json 3621c350…c372 (57 entries, acceptor/accepted_at EMPTY). Copies in `handoff-inputs-r5/`.
- r4 -> r5: 51 files byte-identical (incl. history/idp_national.csv: no national IDP re-export), 1 changed (fixed/area_identity.csv: added iso3_reference), 6 added (fixed/geometry/* byte copies of the training geometry ipcch_admin_geometry_repaired.*, fixed/population_reference.csv).
- Country identity: `iso3` remains the TRAINING lineage (blank for 31 CI areas, as the model inputs had); `iso3_reference` = ISO 3166-1 alpha-3 of iso2 from a pinned pycountry 26.2.16 table (`iso3166_alpha2_alpha3_pycountry_26.2.16.csv`, sha 40a46573…): CI -> CIV for 31 areas, 0 conflicts with training iso3. Feature effect if CIV were used: none today (national IDP history has no CIV reports); not substituted into model inputs pending explicit review.
- Population reference (design.md:27): every observed raw-panel estimated_population (admin_code, reference_period, population_estimate), roster-filtered (3 rows of 1315 dropped); runtime selects latest <= O with the existing no-future builder.
- Roster policy (manifest `roster_policy`): derived tables filtered to the roster; byte-preserved fixed sources NOT filtered — unit_admin1_weights.csv, unit_iso3.csv and the geometry .dbf carry admin 1315 (measured; each covers the full roster); other ACLED/geometry files are not admin-keyed. Computed outputs must cover exactly the roster (test `test_outputs_cover_exactly_the_roster_although_fixed_tables_carry_an_extra_admin`).
- Imported metadata exception (separate from R34 new-output rules): delivered seasonal single-source rows with ens_sd = 0 kept as delivered — cdd 44, rainy_days 44, prcp_z 15 (103).
- Wording corrected: not all fixed inputs are roster-filtered.
