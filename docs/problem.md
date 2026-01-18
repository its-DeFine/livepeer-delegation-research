---
title: Problem Definition
description: What we are actually solving (and the metrics we require) before we judge any delegation proposal.
---

# The Delegation Problem

This doc is the shared baseline for all proposal reviews.

## Goals (primary)

1) Increase **net-new delegators** (especially small delegators).
2) Increase **net-new delegated stake** (not just reshuffling existing LPT).
3) Improve **retention** (reduce fast churn/unbond/withdraw patterns).
4) Improve **decentralization** (avoid concentrating new stake to a small set of orchestrators).

## Constraints / realities

- Arbitrum environment: low fees help, but sybil is still cheap.
- Delegation incentives are **sybil-sensitive** when rewards scale by “# of accounts”.
- Many proposals increase “delegation count” while decreasing security if they over-concentrate stake or can be farmed.

## Canonical metrics (must be reported for any solution)

- **New delegators (first-time bonders)**: daily/weekly/monthly
- **Net stake change**: net bond − unbond − withdraw
- **Retention**: % of new delegators still bonded at 30/90/180 days
- **Concentration**: top-1/top-5 share of the solution’s bonded stake
- **Sybil risk proxies**: funding clustering, common senders, fast-exit cohorts

## Common failure mode (call it out explicitly)

If a proposal claims “we will increase small delegators” but its mechanism is “pay more per address for smaller balances”, it is **sybilable by design** unless it has a uniqueness primitive (identity, proof, or a strong economic cost to splitting).
