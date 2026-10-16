# Exact Gemini model price inputs

Read-only source/catalog check, 2026-10-16. No network/provider call. Supervisor independently checked all four catalog records below. This is quote input, not model-availability or live billing acceptance.

Original native `sources/Food_Crisis_Cluster/IPCCHMLflow/README.md:98-104` identifies `gemini-3.8-flash` on Vertex `global`, Gateway endpoint `ipcch-assistant-gemini`; the original provider billed another project. Actual migrated endpoint must use `food-crisis-modeling-enso`. Do not substitute Gemini2.5 or its prices.

Let S=`/home/swl007007/projects/food-crisis-research/scratch/p3/skus/vertex.json`. All records have effectiveTime `2026-10-15T07:00:00Z`, currency USD, usageUnit `count`, tier start0, displayQuantity1,000,000. Direct nanos prices below are per count.

| Array index | SKU | Exact description | nanos/count | USD/million count |
|---|---|---|---:|---:|
|1570|2A35-AC68-14D6|Gemini 3.8 Flash Global Text Input - Predictions|1500|1.50|
|5375|90FD-DC5F-DC55|Gemini 3.8 Flash Global Text Output - Predictions|7500|7.50|
|1060|1C52-4B3A-E3E7|Gemini 3.8 Flash Regional Text Input - Predictions|1650|1.65|
|5197|8C46-0EC8-54F9|Gemini 3.8 Flash Regional Text Output - Predictions|8250|8.25|

Even the Regional descriptions have `serviceRegions=[global]`; these catalog fields do not prove availability in a specific region. There are no descriptions containing both3.8 and thinking; absence of a distinct SKU does not imply free thinking. Verify official model limits and billing semantics before paid calls. Existing total-token guard must account for thought tokens.

The earlier `cost-inputs-supervisor.md` illustrative Gemini2.5 scenario used USD2.80 for1M input+1M output. Under this exact Global pair the same metering assumption is USD9.00 (+6.20), before resolving thinking allocation. Neither illustration is the final quote.

Small next public documentation checks: `https://cloud.google.com/vertex-ai/generative-ai/docs/models` and `https://cloud.google.com/vertex-ai/generative-ai/pricing`, for exact3.8 model/location, output/thinking limits and accounting. No runtime secret or Gateway database value was inspected.

## Supervisor public-document follow-up (no authenticated project operation)

Fetched four official pages with urllib; raw HTML and extracted text are saved at native `scratch/p3/public-model-docs/`. No model invocation, credentials or billable API was involved.

- Model catalog redirected to `https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/google-models`; HTML SHA fe4488c600d859047749f82c5ce7461388c49f4197cbe60fa156882974f820ea.
- Exact card `https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash`; HTML SHA041b2f3a9ef897deaab2aff50bf28c3c421261e795ed77d4cb9a9263210c0b78. Extracted `flash38.txt:1110-1129` names model and context1,048,576 / maximum output65,536. Lines1277-1307 list global/us/eu, Standard PayGo and GA. This establishes documented availability, not target-project successful invocation.
- Official pricing redirected to `https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing`; HTML SHA6999b3a206eadc080327fab0885f0cdbcb2a09e63e8bf384a564409a56c1182b. `pricing.txt:272-318` quotes introductory Global0.75/3.75 until2026-12-31 and standard1.50/7.50 from2027-01-01; **output explicitly includes response and reasoning**. Line516 says promotional pricing is provided through50% credits back on net spend. Use gross catalog1.50/7.50 for conservative reservation/quote, not presumed credits.
- Exact guide `https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash`; HTML SHA a9d98d194064874c9ae119e14bc6b5cd91f7ba38a82dc6eaee623390de1fc9ac. `flash38-guide.txt:1448-1514` says use thinking_level LOW/MEDIUM/HIGH, not thinking_budget, and remove candidate_count/temperature/top_p/top_k/frequency/presence parameters. The model card's parameter-default table still lists several of these. Treat this as a documented compatibility discrepancy for the actual bounded smoke; current guard forcing candidateCount1 needs checking before claiming3.8 compatibility. Do not silently change models or remove budget enforcement.

Still pending: verify actual request schema, usage including thoughts and hard/observed output behavior through the selected provider under the conservative guard.
