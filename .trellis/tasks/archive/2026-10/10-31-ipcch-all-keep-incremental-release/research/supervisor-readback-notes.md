# Supervisor readback notes — 2026-11-01 UTC

Source-only scouts confirmed the inspected IPCCH product files are unchanged from
115798f. These notes are acceptance guidance, not live DA1/DA2 evidence.

## Minimal incremental joins

- Durable `ipcch_exports/<run_id>/tasks/<description>.json` carries actual asset,
  task, request and operation identities. Its final state is `completed` (EE's
  external task state is `COMPLETED`). Join to batch
  `generation.climate_production.receipts` by task and destination, not only by
  predicted destination names. Sources: ee_transport.py:239-246,320-349;
  table_producers.py:486-511.
- Published source outcomes put consumed IDs into retained
  `HEAD.record.produced_tables[source]`; monthly append also records `month`.
  Sources: climate_tables.py:333-336; climate.py:188-193,301-302.
- Join HEAD `(version,sha256,HEAD generation)` to batch `retained_inputs` and
  immutable content/acceptance refs; compare old keys/values and new month keys.
  The generation is the HEAD generation, not its CSV generation.
  Sources: stores.py:99-130; generation.py:119-127,388-419.
- Join batch ref to run inference and release/delivery system provenance; compare
  published fill-audit bytes with the pinned batch provenance sidecar.
  Sources: run_v2.py:88-101; delivery_member.py:209-229; release_v2.py:23-29.
- HEAD.record retains only the latest append; lineage does not retain every old
  produced_tables record. Current preflight expects one month per table and no
  season work; if that changes, retain intermediate HEAD generations.

## Live DA2 observations

- PATCH32: retain the actual normalized 32-ID set and uniqueness, not only rows=32;
  inspect fallback metadata. Exact set: table_producers.py:66-68,389-397.
  A missing patch row in the full roster remains NaN; finite primary ET0 is never
  overwritten. A natural primary-null/patch-finite filling witness, if present,
  supports live alignment; otherwise label the particular witness pending.
- VI producer and consumer apply no extra 0.0001 scaling. Establish current and
  same-slot baseline units using actual values/source identity, then verify a
  small actual overlap-weighted anomaly example. Receipt validation alone does
  not establish compatible units. Sources: table_producers.py:148-180;
  climate_tables.py:242-265,456-486.
- Drought completeness is collection count versus calendar days, not finite
  pixels. Preserve declared days, column presence, null counts and actual masked
  rows. Complete + all-null column is different from an omitted complete column.
  Sources: table_producers.py:186-199,252-266; climate_tables.py:151-178.
- DataFrame NaN cannot distinguish a row property omitted by EE from explicit
  null. Need raw property-key presence for that claim; CSV blank/header evidence
  has its own meaning. Naturally absent field-shape witnesses remain pending
  under D2. Source: ee_transport.py:395-426.

No cloud reads, tests or product edits were performed by the scouts. Generic
readback passing alone does not establish these joins or live field witnesses.
