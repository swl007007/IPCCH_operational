# Quote at native f45426e (supersedes quote-6d4a9b6 and the b24dfd1 prose amendment)

Regenerated with `research_cloud.cost.quote` from the saved SKU catalogs (`scratch/p3/skus`, catalog effective 2026-10-15T07:00:00Z). Prices are gross list prices.

| Pool | Monthly | One-time | First month | Envelope |
|---|---|---|---|---|
| platform | 79.23 | 11.67 | 90.91 | 100 |
| training | 0 | 0.78 | 0.78 | 100 |

Changes since quote-6d4a9b6:
- **b24dfd1:** five images (adds replay-x320 and replay-forecast-x320). The AR storage line becomes 11 GiB-month, workstation pulls 11 GiB, and Cloud Build 120 min.
- **f45426e:** a new line, Cloud SQL internet egress for the research-input import's verification readback. 16 GiB one-time at USD 0.19/GiB, SKU `238B-D94B-7243` (`sql.json[2798]`, Network Internet Data Transfer Out from Americas to Americas) = USD 3.04. It was missing from the quote and was found and reserved in the ledger (`G8-sql-import-readback-egress`) before the import ran.

A quote is not a spending cap. The operator ledger holds the per-operation reservations (`ledger/spend.sqlite`). Its reservations are not identical to the quote lines; for example, Cloud SQL is reserved for a full month.
