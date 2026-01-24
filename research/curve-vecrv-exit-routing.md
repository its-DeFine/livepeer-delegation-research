---
title: "Curve (veCRV): exit → exchange routing (on-chain)"
description: "Evidence pack: on-chain exit events and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."
---

# Curve (veCRV): exit → exchange routing (on-chain)

- Generated: `2026-01-24T22:27:02.928099+00:00`
- Ethereum RPC: `https://ethereum.publicnode.com`
- Exit contract: `0x5f3b5dfeb7b28cdbd7faba78963ee202a494e2a2`
- Exit event: `Withdraw(address,uint256,uint256)` (topic0 `0xf279e6a1f5e320cca91135676d9cb6e44ca8a08c0b88342bcdb1144f6511b568`)
- Token: `0xd533a949740bb3306d119cc777fa900ba034cd52` (CRV)

## Exit events (observed)

- Range scanned: `23,659,582..24,307,582` (~90d)
- Exit events: **371**
- Unique recipients: **367**
- Total exited (events): **9,569,501.111 CRV**

## Tight-window routing to labeled exchanges (top recipients)

- Window: **30 days** (~216,000 blocks)
- Exchange label set size: **37** addresses (`data/labels.json`)
- Top recipients analyzed: **50**

- Exit events considered (top recipients): **50**
- Exit amount considered: **9,132,045.199 CRV**
- Direct matched within window (events): **0**
- Direct matched amount (lower bound): **0.000 CRV**
- Second hop matched within window (events): **4**
- Second hop matched amount (lower bound): **475,975.996 CRV**
- Third hop matched within window (events): **0**
- Third hop matched amount (lower bound): **0.000 CRV**
- Total matched (events): **4**
- Total matched amount (lower bound): **475,975.996 CRV**

## First hop destinations (top recipients; within window)

This categorizes the *first meaningful* outgoing token transfer after each exit (>= max(min_first_hop_token, min_first_hop_fraction*exit)) as a proxy for where the exit goes. It can miss split flows or transfers below threshold.

- no_first_hop_meeting_threshold: **21** events; **4,262,270.499 CRV** exited
- unknown_contract: **17** events; **1,102,670.672 CRV** exited
- unknown_eoa: **12** events; **3,767,104.028 CRV** exited

Top exchange endpoints (by matched count):

- Coinbase 10: **2**
- Binance 14: **2**

## Notes / limitations

- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.
- Hop routing is a lower bound: it only detects intermediates that sweep into labeled exchange endpoints within the same window.
- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.

Raw output: see `research/curve-vecrv-exit-routing.json`.
