---
title: "Frax (veFXS): exit → exchange routing (on-chain)"
description: "Evidence pack: on-chain exit events and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."
---

# Frax (veFXS): exit → exchange routing (on-chain)

- Generated: `2026-01-24T22:37:59.294962+00:00`
- Ethereum RPC: `https://ethereum.publicnode.com`
- Exit contract: `0xc8418af6358ffdda74e09ca9cc3fe03ca6adc5b0`
- Exit event: `Withdraw(address,uint256,uint256)` (topic0 `0xf279e6a1f5e320cca91135676d9cb6e44ca8a08c0b88342bcdb1144f6511b568`)
- Token: `0x3432b6a60d23ca0dfca7761b7ab56459d9c964d0` (FXS)

## Exit events (observed)

- Range scanned: `23,659,638..24,307,638` (~90d)
- Exit events: **129**
- Unique recipients: **128**
- Total exited (events): **1,101,085.109 FXS**

## Tight-window routing to labeled exchanges (top recipients)

- Window: **30 days** (~216,000 blocks)
- Exchange label set size: **37** addresses (`data/labels.json`)
- Top recipients analyzed: **50**

- Exit events considered (top recipients): **51**
- Exit amount considered: **1,073,411.321 FXS**
- Direct matched within window (events): **0**
- Direct matched amount (lower bound): **0.000 FXS**
- Second hop matched within window (events): **4**
- Second hop matched amount (lower bound): **75,711.591 FXS**
- Third hop matched within window (events): **0**
- Third hop matched amount (lower bound): **0.000 FXS**
- Total matched (events): **4**
- Total matched amount (lower bound): **75,711.591 FXS**

## First hop destinations (top recipients; within window)

This categorizes the *first meaningful* outgoing token transfer after each exit (>= max(min_first_hop_token, min_first_hop_fraction*exit)) as a proxy for where the exit goes. It can miss split flows or transfers below threshold.

- unknown_contract: **26** events; **702,485.552 FXS** exited
- no_first_hop_meeting_threshold: **17** events; **181,888.179 FXS** exited
- unknown_eoa: **8** events; **189,037.591 FXS** exited

Top exchange endpoints (by matched count):

- Binance 14: **4**

## Notes / limitations

- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.
- Hop routing is a lower bound: it only detects intermediates that sweep into labeled exchange endpoints within the same window.
- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.

Raw output: see `research/frax-vefxs-exit-routing.json`.
