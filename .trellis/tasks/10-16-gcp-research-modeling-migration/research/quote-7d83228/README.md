# Quote at native 7d83228 (supersedes quote-f45426e)

| Pool | Monthly | One-time | First month | Envelope |
|---|---|---|---|---|
| platform | 79.59 | 11.67 | 91.27 | 100 |
| training | 0 | 0.78 | 0.78 | 100 |

Changes since f45426e:
- **Secret Manager** is now priced at the 16 versions actually created: 13 initial, 2 corrected MLflow URI versions (version 1 kept; no old version is deleted outside an approved scope) and 1 temporary migration admin. All are assumed retained for the full month, giving 0.96 + accesses 0.06 = 1.02 (+0.36 vs the quote, +0.18 vs the G6 ledger reservation). The ledger delta is reserved as `G6-secret-versions-amend-2026-10`.
- **SQL import readback egress** is unchanged from f45426e: 3.04 one-time (SKU 238B-D94B-7243).

**Ledger at this point** (`ledger/spend.sqlite`, platform 2026-10): 10 reservations, USD 59.23, no actuals. The ledger balance (40.77) is **not** the remaining plan headroom. These quoted items are still unreserved:
- Gemini guard allocation 10;
- contingency 10;
- logging;
- the one-time scen archive direct download 5.16;
- the package acceptance downloads through the MLflow proxy (1.26 egress + 0.21 Run);
- the training jobs (training pool).

Each is reserved before its operation.
