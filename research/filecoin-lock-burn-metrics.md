---
title: "Filecoin lock + burn metrics (DePIN benchmark)"
description: "On-chain snapshot of Filecoin’s lock/burn primitives, contrasted with Livepeer’s on-chain extraction proxies."
sidebar_label: "Filecoin vs Livepeer"
---

# Filecoin lock + burn metrics (DePIN benchmark)

This evidence pack adds a DePIN reference point (Filecoin) to the Livepeer extraction discussion.

## Filecoin: on-chain lock + burn primitives (snapshot)

- Generated: `2026-01-22T14:59:53.088960+00:00`
- Filecoin RPC: `https://api.node.glif.io`
- Head height: `5692919`

Key on-chain quantities (FIL):

- Burnt funds (actor `f099`): **41,583,628.457 FIL**
- Total pledge collateral locked (Power actor `f04`): **100,281,675.748 FIL**
- This-epoch pledge collateral (Power actor `f04`): **100,281,675.748 FIL**
- Provider locked collateral (Market actor `f05`): **547,085.058 FIL**
- Client locked collateral (Market actor `f05`): **0.000 FIL**
- Client storage fees (Market actor `f05`): **10.933 FIL**

Reward context (FIL):

- This-epoch block reward (Reward actor `f02`): **24.128 FIL / epoch**
- Daily reward estimate (epoch reward × 2880/day): **69,487.588 FIL / day**
- Total storage power rewards minted (Reward actor `f02`): **393,271,272.962 FIL**

Interpretation:

- Filecoin has large protocol-level **locked capital** (pledge collateral) and an explicit **burn sink** (burnt funds).
- These mechanics raise the cost of “farm-and-dump” behavior by constraining liquidity and adding penalties/burn pathways.

## Contrast: Livepeer extraction proxies (from our evidence packs)

Livepeer differs structurally: inflation rewards can become liquid and be routed off-chain quickly (see timing traces).

- Rewards claimed (total): **17514284.209827435042847246 LPT** (`/research/rewards-withdraw-timeseries`)
- `WithdrawStake` amount (total; includes principal): **29513599.897804303796839955 LPT** (`/research/rewards-withdraw-timeseries`)
- Tight-window traces matched to labeled exchanges: **68** (across 10 senders) (`/research/extraction-timing-traces`)
- Top-50 proxy rewards withdrawn (sum): **5329277.600117 LPT** (`/research/extraction-fingerprints`)

What this suggests (high level):

- Filecoin’s design has strong **on-chain friction** against immediate reward sell-through (locked collateral + burn sink).
- Livepeer currently has weaker on-chain friction against immediate reward cashout; this is why we propose **reward-only escrow/vesting/forfeit** primitives for Livepeer.

## Notes + limitations

- This report does **not** attempt to infer “selling” for FIL; exchange deposits are not labeled here.
- Filecoin reward vesting specifics are protocol rules; we focus on actor-reported locked/burn balances to keep the report RPC-only.
- Cross-chain comparisons are qualitative: the goal is to compare primitives (lock/burn/penalty), not to claim identical market behavior.

Raw output: see `research/filecoin-lock-burn-metrics.json`.
