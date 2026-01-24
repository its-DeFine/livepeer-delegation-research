---
title: "DePIN liquidity primitives snapshot (on-chain)"
description: "On-chain snapshot of reward/principal liquidity primitives across Livepeer, The Graph, Akash, Pocket, and Filecoin."
---

# DePIN liquidity primitives snapshot (on-chain)

- Generated: `2026-01-24T01:03:38.048671+00:00`

This is an evidence pack used to ground the DePIN tokenomics comparison around **time-gated liquidity** (unbonding/thawing) and **reward vesting** primitives.

## Livepeer (Arbitrum): unbonding period (rounds)

- RPC: `https://arb1.arbitrum.io/rpc`
- BondingManager (proxy): `0x35Bcf3c30594191d53231E4FF333E8A770453e40`
- `unbondingPeriod()`: **7 rounds**

Interpretation: this is **principal liquidity friction** (exit delay). It does not, by itself, enforce linear reward vesting.

## The Graph (Ethereum): thawing period (blocks)

- RPC: `https://ethereum.publicnode.com`
- Block number: `24301243`
- Staking contract: `0xF55041E37E12cD407ad00CE2910B8269B01263b9`
- `thawingPeriod()`: **201,600 blocks** (~28.0 days @ 12s/block)

Interpretation: this is also **principal liquidity friction** (unstake → wait → withdraw).

## Akash (Cosmos): staking params (`unbonding_time`)

- REST: `https://rest.cosmos.directory/akash/cosmos/staking/v1beta1/params`
- `unbonding_time`: **1814400s** (~21.0 days)
- `bond_denom`: `uakt`
- `max_validators`: `100`

Interpretation: Cosmos-style staking typically enforces principal unbonding delays, but does not default to months-long linear reward vesting.

## Pocket (Shannon / poktroll): supplier unbonding period (sessions)

- REST: `https://shannon-grove-api.mainnet.poktroll.com`
- Shared params: `/pokt-network/poktroll/shared/params`
- `num_blocks_per_session`: **60**
- `supplier_unbonding_period_sessions`: **504**
- Supplier unbonding (blocks): **30,240**
- Estimated block time: **61.03s** (over 1000 blocks)
- Estimated session duration: **~1.02 hours**
- Estimated supplier unbonding duration: **~21.4 days**

Interpretation: Pocket’s unbonding sessions act as **principal liquidity friction** (unstake → wait → withdraw), similar in class to Cosmos-style unbonding.

## Filecoin: burn sink + locked pledge + miner vesting schedule head

- RPC: `https://api.node.glif.io`
- Head height: `5697007`

Network-level lock/burn quantities (FIL):

- Burnt funds (actor `f099`): **41,587,585.664998 FIL**
- Total pledge collateral locked (Power actor `f04`): **100,160,062.667519 FIL**
- Provider locked collateral (Market actor `f05`): **544,424.761728 FIL**

Sample miner vesting state (FIL):

- Miner actor: `f01729333`
- `LockedFunds`: **242.282358 FIL**
- `InitialPledge`: **5,069.828175 FIL**
- `VestingFunds.Head`: epoch `5697290` amount **1.298287 FIL**
- `VestingFunds.Tail` CID: `bafy2bzacec5t3f7srz5nliywlcn3itvin7dnnhtlhsgltyb5umiokvf2hsyse` (indicates additional vesting entries beyond the head)

Interpretation: Filecoin exposes explicit **locked funds** + a **vesting schedule** component at the miner actor level, which is closer to a true “reward vesting” primitive than an unbonding/thaw delay alone.

Raw output: see `research/depin-liquidity-primitives-snapshot.json`.
