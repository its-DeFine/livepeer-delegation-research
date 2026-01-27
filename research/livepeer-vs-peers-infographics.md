---
title: Livepeer vs peers (infographics, static)
description: Static, Markdown-only infographics summarizing Livepeer vs peer protocols using the evidence packs in this repo (Mintlify/GitHub-friendly).
sidebar_label: Livepeer vs peers (infographics)
---

# Livepeer vs peers (infographics, static)

This page is a **Markdown-only** “one-pager” version of the comparison, intended to render well in:

- GitHub (plain Markdown)
- Mintlify (plain Markdown)

For the interactive Docusaurus comparison page, see: `/research/livepeer-vs-peers`.

## Exchange routing → labeled CEX (lower bound)

Exchange label set size: **105** (`data/labels.json`)

30d window (best-effort):

```text
Livepeer (LPT) — L1 second-hop follow-up  51.00% |█████████████████████████░░░░░░░░░░░░░░░░░|
Livepeer (LPT) — L2→L1 timing traces     49.53% |████████████████████████░░░░░░░░░░░░░░░░░░|
The Graph (GRT) — delegation withdraw    12.18% |██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
Frax (FXS) — veFXS withdraw               7.16% |████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
Curve (CRV) — veCRV withdraw              5.20% |███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
Aave (AAVE) — stkAAVE redeem              4.72% |███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
```

Notes:
- “Exchange routing” is a **lower bound** (labels + hop/window limits miss many paths).
- It’s not “% that is sold”, it’s “% that touches a labeled exchange endpoint within the scan limits”.

Source: `research/exchange-routing-metrics.md`

## Livepeer: stake concentration + exits (size bands)

Active stake concentration (snapshot):

```text
10k+ wallets share of active delegators    6.02% |███░░░░░░░░░░░░░░░░░░░░░░░░░░|
10k+ wallets share of active bonded LPT   92.26% |████████████████████████████░|
```

Withdrawals are whale-dominated (historical outflows universe):

```text
10k+ wallets share of delegators           6.53% |███░░░░░░░░░░░░░░░░░░░░░░░░░░|
10k+ wallets share of withdrawers          8.61% |████░░░░░░░░░░░░░░░░░░░░░░░░░|
10k+ wallets share of withdrawn LPT       88.04% |██████████████████████████░░░|
```

Sources:
- `research/delegator-stake-distribution.md`
- `research/delegator-outflows-by-size-band.md`

## Livepeer: buy-side proxy funnel (best-effort)

Proxy: labeled CEX outflows on Ethereum → recipients → whether they later bond on Arbitrum.

```text
21,388  unlabeled recipients (any size)
   ↓  (≥ 10,000 LPT inbound; top 200)
200     selected recipients (113.53M LPT inbound)
   ↓  (in Arbitrum delegator set)
5       matched delegators (2.07M LPT inbound)
   ↓  (bonded within 30 days)
4       bonded (1.79M LPT inbound)
```

Source: `research/buy-pressure-proxies.md`

## Livepeer: wallet rotation via TransferBond (best-effort)

Last ~365d on Arbitrum BondingManager:

```text
122 events total
33,803.59 LPT moved
receipt validation: 122/122 matched Unbond+Rebond (same tx)
fanout max = 1 (no 1→many splitting via TransferBond observed)
```

Source: `research/livepeer-transferbond-rotation.md`

