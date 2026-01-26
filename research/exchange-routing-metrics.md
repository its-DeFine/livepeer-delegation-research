---
title: "Exchange routing metrics (best-effort, on-chain)"
description: "Standardized, lower-bound exchange-routing shares across Livepeer and comparable protocols."
sidebar_label: "Exchange routing metrics"
---

# Exchange routing metrics (best-effort, on-chain)

- Generated: `2026-01-26T15:25:21.006569+00:00`
- Exchange label set size (EVM): **105** (`data/labels.json`)

These metrics formalize the “X% goes to exchanges” claim as:
- **numerator**: amount routed to a curated set of labeled exchange endpoints,
- **denominator**: a clearly-defined post-exit flow basis (varies by report),
- treated as a **LOWER BOUND** (labels + hop/window limits miss many paths).

## Summary

| Protocol | Flow basis | Window / range | Hops | Routed to exchanges (lower bound) | Total basis | Share |
|---|---|---|---:|---:|---:|---:|
| Livepeer (LPT) | selected L1 EOA outgoing (2nd hop) | blocks 14600000→24279306 | 1 | 5509570.311 LPT | 10803734.108 LPT | 51.00% |
| Livepeer (LPT) | L1 receipts from traced bridge-outs | ≤72.0h→≤72.0h | ≤2 | 3837434.491 LPT | 7747306.224 LPT | 49.53% |
| The Graph (GRT) | withdrawals (top delegators) | 30d window | ≤3 | 1278394.414 GRT | 10491820.509 GRT | 12.18% |
| Curve (CRV) | veCRV withdraws (top recipients) | 30d window | ≤3 | 475975.996 CRV | 9149435.266 CRV | 5.20% |
| Frax (FXS) | veFXS withdraws (top recipients) | 30d window | ≤3 | 75711.591 FXS | 1057345.321 FXS | 7.16% |
| Aave (AAVE) | stkAAVE redeem (top recipients) | 30d window | ≤3 | 22268.405 AAVE | 472247.006 AAVE | 4.72% |

## First hop destinations (where available)

These breakdowns answer a different question than “eventual exchange deposit”:
- **Where does the *first* large post-exit transfer go?**

They are useful to quantify “self-custody / unknown EOA” vs known endpoints, but they are **not apples-to-apples** across reports.

| Protocol | Basis | Unknown EOA | Unknown contract | No first hop meeting threshold |
|---|---|---:|---:|---:|
| Livepeer (LPT) | 2nd hop from selected L1 EOAs | 49.00% |  |  |
| The Graph (GRT) | 1st hop after withdrawal (thresholded) | 92.68% | 1.86% | 5.46% |
| Curve (CRV) | 1st hop after veCRV withdraw (thresholded) | 41.17% | 11.90% | 46.93% |
| Frax (FXS) | 1st hop after veFXS withdraw (thresholded) | 17.88% | 66.32% | 15.80% |
| Aave (AAVE) | 1st hop after stkAAVE redeem (thresholded) | 11.78% | 25.20% | 63.02% |

## Notes (how to interpret)

- These shares are **not directly comparable** unless you account for the denominator differences (selection rules, hop limits, and windows).
- Best use: track *directionally* whether “post-exit flows” are consistent with eventual exchange deposits.

## Context (exit friction + lock/burn primitives)

Exit friction (principal liquidity delays; not reward vesting):

| Protocol | Primitive | Delay (estimate) |
|---|---|---:|
| Livepeer | `unbondingPeriod()` | 7 rounds |
| The Graph | `thawingPeriod()` | ~28.0 days |
| Pocket | supplier unbonding | ~21.4 days |
| Akash | `unbonding_time` | ~21.0 days |
| Theta | `ReturnLockingPeriod` | ~2.3 days |

Filecoin lock/burn intensity (on-chain friction; not exchange routing):

- Burnt funds: **41583628.457 FIL** (~598 days of rewards @ 69487.588 FIL/day)
- Pledge collateral locked: **100281675.748 FIL** (~1443 days of rewards)

## Sources

- Livepeer L1 second hop JSON: `research/l1-bridge-recipient-second-hop.json`
- Livepeer timing traces JSON: `research/extraction-timing-traces.json`
- The Graph withdrawal routing JSON: `research/thegraph-delegation-withdrawal-routing.json`
- Curve veCRV exit routing JSON: `research/curve-vecrv-exit-routing.json`
- Frax veFXS exit routing JSON: `research/frax-vefxs-exit-routing.json`
- Aave stkAAVE redeem exit routing JSON: `research/aave-stkaave-redeem-exit-routing.json`
- Filecoin lock/burn JSON: `research/filecoin-lock-burn-metrics.json`
- DePIN exit-friction snapshot JSON: `research/depin-liquidity-primitives-snapshot.json`
- Theta liquidity primitives JSON: `research/theta-liquidity-primitives.json`

Raw output: see `research/exchange-routing-metrics.json`.
