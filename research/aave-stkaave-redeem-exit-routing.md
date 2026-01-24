---
title: "Aave (stkAAVE Redeem): exit → exchange routing (on-chain)"
description: "Evidence pack: on-chain exit events and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."
---

# Aave (stkAAVE Redeem): exit → exchange routing (on-chain)

- Generated: `2026-01-24T22:55:04.715745+00:00`
- Ethereum RPC: `https://ethereum.publicnode.com`
- Exit contract: `0x4da27a545c0c5b758a6ba100e3a049001de870f5`
- Exit event: `Redeem(address,address,uint256,uint256)` (topic0 `0x3f693fff038bb8a046aa76d9516190ac7444f7d69cf952c4cbdc086fdef2d6fc`)
- Token: `0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9` (AAVE)

## Exit events (observed)

- Range scanned: `23,659,693..24,307,693` (~90d)
- Exit events: **930**
- Unique recipients: **842**
- Total exited (events): **519,261.812 AAVE**

## Tight-window routing to labeled exchanges (top recipients)

- Window: **30 days** (~216,000 blocks)
- Exchange label set size: **37** addresses (`data/labels.json`)
- Top recipients analyzed: **50**

- Exit events considered (top recipients): **79**
- Exit amount considered: **474,029.194 AAVE**
- Direct matched within window (events): **0**
- Direct matched amount (lower bound): **0.000 AAVE**
- Second hop matched within window (events): **9**
- Second hop matched amount (lower bound): **22,268.405 AAVE**
- Third hop matched within window (events): **0**
- Third hop matched amount (lower bound): **0.000 AAVE**
- Total matched (events): **9**
- Total matched amount (lower bound): **22,268.405 AAVE**

## First hop destinations (top recipients; within window)

This categorizes the *first meaningful* outgoing token transfer after each exit (>= max(min_first_hop_token, min_first_hop_fraction*exit)) as a proxy for where the exit goes. It can miss split flows or transfers below threshold.

- unknown_eoa: **37** events; **59,232.058 AAVE** exited
- unknown_contract: **25** events; **118,921.238 AAVE** exited
- no_first_hop_meeting_threshold: **17** events; **295,875.899 AAVE** exited

Top exchange endpoints (by matched count):

- Binance 14: **7**
- Coinbase 10: **1**
- Gate.io 1: **1**

## Notes / limitations

- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.
- Hop routing is a lower bound: it only detects intermediates that sweep into labeled exchange endpoints within the same window.
- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.

Raw output: see `research/aave-stkaave-redeem-exit-routing.json`.
