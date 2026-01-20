---
title: Executive Statement
description: What the delegation data implies Livepeer should optimize for (bracket growth, utility, and decentralization).
---

# Executive Statement

This is the short version of what the on-chain data implies Livepeer should optimize for.

## What we believe is true (from evidence)

1) **New delegator inflows are collapsing overall** on Arbitrum (first-time bonders drop year-over-year).
2) **Small delegators are plentiful by count but negligible by stake**, so “more small accounts” is not a meaningful security lever by itself.
3) **Security-relevant growth is bracket growth**: attracting and retaining more independent participants in the **`1k–10k`** and **`10k+`** bands (and improving delegate/orchestrator decentralization).
4) Therefore, the core strategy is **LPT utility + liquidity + UX**, not pure “reward boosts” that can be sybil’d.

## The numbers that drive this conclusion

From the latest snapshot (`/research/delegation-board`):
- Active delegators: **~3,222 wallets**
- Bonded stake: **~17.92M LPT**
- `10k+` wallets: **~194 wallets (~6%)** holding **~16.53M LPT (~92%)**
- `1k–10k` wallets: **~277 wallets (~9%)** holding **~1.12M LPT (~6%)**

Net change (example window `2024-10-end → latest`):
- `10k+`: **+37 wallets**, **+~5.99M LPT**
- `1k–10k`: **+15 wallets**, **+~120k LPT**
- Mid-retail bands (`10–100`, `100–1k`) **lost** wallets and stake in the same window.

## What this means for “delegator incentives”

If the goal is **bonded stake + decentralization**, then:
- prioritize mechanisms that increase **token utility** (so 1k–10k and 10k+ can enter/exit without huge friction),
- pair any incentives with **retention hooks** (time/vesting/forfeit),
- avoid “pay more per small address” designs unless there’s a credible **uniqueness primitive** (or a real cost to splitting).

## Read next

<CardGroup cols={2}>
  <Card title="Analytics (board + time series)" href="/docs/analytics">
    One page of links to the key dashboards and evidence.
  </Card>
  <Card title="General directions (what to do next)" href="/docs/directions">
    A stakeholder-friendly set of next-step directions, with what to measure.
  </Card>
</CardGroup>

