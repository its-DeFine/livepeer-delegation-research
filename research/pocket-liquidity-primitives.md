---
title: "Pocket (Shannon) liquidity primitives (on-chain)"
description: "On-chain snapshot of Pocket Network (poktroll) unbonding delays + mint allocation parameters, as a Livepeer-comparable DePIN reference point."
sidebar_label: "Pocket: liquidity primitives"
---

# Pocket (Shannon) liquidity primitives (on-chain)

- Generated: `2026-01-24T00:44:07.070201+00:00`
- REST: `https://shannon-grove-api.mainnet.poktroll.com`

This evidence pack captures Pocket Shannon (poktroll) parameters relevant to **reward/principal liquidity** and **reward distribution**.

## Unbonding + session sizing

- `num_blocks_per_session`: **60**
- `supplier_unbonding_period_sessions`: **504** (≈ **30,240 blocks**)
- `application_unbonding_period_sessions`: **1**
- `gateway_unbonding_period_sessions`: **1**

Best-effort time estimates from on-chain block timestamps:

- Estimated block time: **61.03s** (from 1000 blocks)
- Estimated session duration: **~1.0 hours**
- Estimated supplier unbonding duration: **~21.4 days**

Interpretation: this is primarily **principal liquidity friction** (unstake → wait → withdraw). The exposed params do not indicate protocol-level linear reward vesting.

## Mint allocation (reward distribution)

- Mint allocation percentages (of inflation):
  - `application`: **0**
  - `dao`: **0.1**
  - `proposer`: **0**
  - `source_owner`: **0.1**
  - `supplier`: **0.8**

- Mint-equals-burn claim distribution (if applicable):
  - `application`: **0**
  - `dao`: **0.05**
  - `proposer`: **0.14**
  - `source_owner`: **0.03**
  - `supplier`: **0.78**

- `global_inflation_per_claim`: `1e-06`
- `dao_reward_address`: `pokt1dr5jtqaaz4wk8wevl33e7vkxsjlphljnjhyq2l`

## Minimum stake (role thresholds)

- Supplier min stake: **59,500.000000 POKT** (`59500000000` upokt)
- Application min stake: **1,000.000000 POKT** (`1000000000` upokt)
- Gateway min stake: **5,000.000000 POKT** (`5000000000` upokt)

Raw output: see `research/pocket-liquidity-primitives.json`.
