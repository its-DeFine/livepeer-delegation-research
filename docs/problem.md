---
title: Problem Definition
description: What we are actually solving (and the metrics we require) before we judge any delegation proposal.
---

# The Delegation Problem

This doc is the shared baseline for all proposal reviews.

## Goals (primary)

1) Increase **net-new delegated stake** (not just reshuffling existing LPT).
2) Increase the number of **independent stake decision-makers** in meaningful stake brackets — especially **`1k–10k`** and **`10k+`**.
3) Improve **retention** (reduce fast churn/unbond/withdraw patterns).
4) Improve **decentralization** (avoid concentrating new stake to a small set of orchestrators/delegates).

Note: “small delegators” matter for community participation, but current on-chain distributions show they are **economically negligible by stake**, so a strategy that only optimizes for “more small addresses” will not move security metrics.

## Constraints / realities

- Arbitrum environment: low fees help, but sybil is still cheap.
- Delegation incentives are **sybil-sensitive** when rewards scale by “# of accounts”.
- Many proposals increase “delegation count” while decreasing security if they over-concentrate stake or can be farmed.

## Canonical metrics (must be reported for any solution)

- **New delegators (first-time bonders)**: daily/weekly/monthly
- **Net stake change**: net bond − unbond − withdraw
- **Bracket distribution**: active wallet counts + bonded LPT in `1k–10k` and `10k+` (and how that changes)
- **Retention**: % of new delegators still bonded at 30/90/180 days
- **Concentration**:
  - delegators (top-N share of bonded stake)
  - delegates/orchestrators (top-N share, Nakamoto 33/50)
- **Sybil risk proxies**: funding clustering, common senders, fast-exit cohorts

## Common failure mode (call it out explicitly)

If a proposal claims “we will increase small delegators” but its mechanism is “pay more per address for smaller balances”, it is **sybilable by design** unless it has a uniqueness primitive (identity, proof, or a strong economic cost to splitting).
