# Livepeer Delegator Outflows — By Delegator Size Band (Arbitrum)

This report answers:
- Which delegator size cohorts drive outflows (by **count** vs by **LPT**)?
- Are size bands growing (via **new delegators per year**) or shrinking?

## Inputs

- Universe: `data/arbitrum_delegator_addresses.json` (4,887 addresses)
- State aggregates: `../../artifacts/livepeer-bm-scan-arbitrum-v2/delegators_state.pkl`
- Scan window: blocks `5856381` → `422367841` (updated `2026-01-17T17:52:21.074415+00:00`)

## Outflows by size band (band = max bonded stake per wallet)

- Total delegators in universe (first bond observed): `4,887`
- Wallets that ever withdrew stake (`WithdrawStake`): `2,322` (total withdrawn: `23,808,745.439 LPT`)
- Wallets that ever unbonded (`Unbond`): `2,684` (total unbonded: `42,256,849.154 LPT`)

| Band (max bonded) | Delegators | Withdrawers | % of withdrawers | Withdrawn LPT | % of withdrawn |
|---|---:|---:|---:|---:|---:|
| <1 LPT | 625 | 51 | 2.20% | 47,265.259 | 0.20% |
| 1–10 LPT | 472 | 222 | 9.56% | 229,162.145 | 0.96% |
| 10–100 LPT | 1,663 | 751 | 32.34% | 263,309.111 | 1.11% |
| 100–1k LPT | 1,319 | 760 | 32.73% | 692,608.731 | 2.91% |
| 1k–10k LPT | 489 | 338 | 14.56% | 1,615,443.091 | 6.79% |
| 10k+ LPT | 319 | 200 | 8.61% | 20,960,957.103 | 88.04% |

### Interpretation (quick)

- **Withdrawn LPT** is expected to be concentrated in `10k+` (whale-size wallets).
- **Withdrawer count** tends to be concentrated in the mid-size retail bands (`10–100`, `100–1k`).

## New delegators by year (first bond timestamp)

| Year | Total | <1 | 1–10 | 10–100 | 100–1k | 1k–10k | 10k+ |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 2,213 | 471 | 214 | 776 | 485 | 147 | 120 |
| 2023 | 1,492 | 73 | 102 | 611 | 507 | 110 | 89 |
| 2024 | 685 | 26 | 81 | 176 | 215 | 128 | 59 |
| 2025 | 482 | 54 | 75 | 98 | 106 | 100 | 49 |
| 2026 | 15 | 1 | 0 | 2 | 6 | 4 | 2 |
