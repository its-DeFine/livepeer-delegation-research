---
title: "Theta staking liquidity primitives (withdraw delays)"
description: "Evidence pack for Theta staking withdrawal/unstaking delays (Guardian stake ~48h; TFUEL stake ~60h) with Theta ETH-RPC chain context."
sidebar_label: "Theta: liquidity primitives"
---

# Theta staking liquidity primitives (withdraw delays)

- Generated: `2026-01-24T01:10:04.496237+00:00`
- Theta ETH-RPC: `https://eth-rpc-api.thetatoken.org/rpc`
- `eth_chainId`: `0x169` (361)

## On-chain context (EVM adaptor)

- Latest block: `32903011`
- Estimated block time: **6.85s** (over 5000 blocks)

## Protocol constant (block-based return lock)

- `ReturnLockingPeriod`: **28,800 blocks**
- Source (Theta protocol ledger): `https://raw.githubusercontent.com/thetatoken/theta-protocol-ledger/master/core/stake.go`
- Line excerpt: `ReturnLockingPeriod uint64 = 28800      // number of blocks, approximately 2 days with 6 second block time`
- Time @ 6s/block (nominal): **~48.0 hours**
- Time @ observed avg (ETH-RPC timestamps): **~54.8 hours**

## Unstaking / withdrawal delays (official docs excerpts)

Guardian stake withdrawal:
- Source: `https://docs.thetatoken.org/docs/withdrawing-your-stake-from-the-guardian-node`
- Excerpt: “Withdrawn stakes will be returned to your wallet address in approximately 48 hours.”

TFUEL staking (Elite Edge Node) withdrawal:
- Source: `https://docs.thetatoken.org/docs/elite-edge-node-staking-process`
- Excerpt: “Upon withdrawal of your TFuel, there is a ~60 hour unstaking period before your staked tokens will appear back in your Theta Wallet.”

Interpretation: Theta exposes **principal liquidity friction** via unstaking delays; this is not the same primitive as protocol-level linear reward vesting.

Raw output: see `research/theta-liquidity-primitives.json`.
