---
title: "Frax (veFXS): exit → exchange routing (on-chain)"
description: "Evidence pack: on-chain exit events and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."
---

# Frax (veFXS): exit → exchange routing (on-chain)

- Generated: `2026-01-26T14:54:53.393123+00:00`
- Ethereum RPC: `https://ethereum.publicnode.com`
- Exit contract: `0xc8418af6358ffdda74e09ca9cc3fe03ca6adc5b0`
- Exit event: `Withdraw(address,uint256,uint256)` (topic0 `0xf279e6a1f5e320cca91135676d9cb6e44ca8a08c0b88342bcdb1144f6511b568`)
- Token: `0x3432b6a60d23ca0dfca7761b7ab56459d9c964d0` (FXS)

## Exit events (observed)

- Range scanned: `23,671,699..24,319,699` (~90d)
- Exit events: **128**
- Unique recipients: **127**
- Total exited (events): **1,083,978.109 FXS**

## Tight-window routing to labeled exchanges (top recipients)

- Window: **3 days** (~21,600 blocks)
- Exchange label set size: **105** addresses (`data/labels.json`)
- Top recipients analyzed: **50**

- Exit events considered (top recipients): **51**
- Exit amount considered: **1,057,345.321 FXS**
- Direct matched within window (events): **0**
- Direct matched amount (lower bound): **0.000 FXS**
- Second hop matched within window (events): **4**
- Second hop matched amount (lower bound): **75,711.591 FXS**
- Third hop matched within window (events): **0**
- Third hop matched amount (lower bound): **0.000 FXS**
- Total matched (events): **4**
- Total matched amount (lower bound): **75,711.591 FXS**

## Arbitrum follow-up (L1 bridge deposit → exchange routing; best-effort)

- Arbitrum RPC: `https://arb1.arbitrum.io/rpc`
- L1 gateway router: `0x72ce9c846789fdb6fc1f34ac4ad25dd9ef7031ef`
- L1 token gateway: `0xa3a7b6f88361f48403514059f1f16c8e78d60eec`
- L2 token address: `0xd9f9d2ee2d3efe420699079f16d9e924afffdea4`
- Follow-up window after deposit: **7 days**
- Exit events with detected Arbitrum deposit: **0**
- Exit amount (events) with deposit: **0.000 FXS**
- Bridged token amount (outboundTransfer sum): **0.000 FXS**
- Of those, matched to labeled exchange on Arbitrum (events): **0**
- Matched exit amount (events): **0.000 FXS**
- Matched token amount to exchanges on Arbitrum: **0.000 FXS**

## Post-exit roles (heuristic; top recipients)

These roles are a *best-effort* way to explain what “unknown EOAs / contracts” are doing after exit. They do **not** replace strict exchange routing.

- unknown_contract: **21** events; **659,466.085 FXS** (62.37%)
- hold_no_first_hop: **13** events; **105,235.506 FXS** (9.95%)
- dex_router_interaction: **9** events; **103,606.139 FXS** (9.80%)
- exchange_strict: **4** events; **75,711.591 FXS** (7.16%)
- unknown_eoa: **4** events; **113,326.000 FXS** (10.72%)

Top intermediates on paths that end at labeled exchanges (by count):

- 0xb9af2530513f4db691c2abbb23d4257fc7414040: **1** (example downstream: Binance 14)
- 0x2f2e15f6c036b69505e8777f5c6f156046f99b56: **1** (example downstream: Binance 14)
- 0xdf9aadc9e85008944443968254d7359f9ec84b1a: **1** (example downstream: Binance 14)
- 0xcd6f58a2923487299679b594fe200a25c99627e4: **1** (example downstream: Binance 14)

## First hop destinations (top recipients; within window)

This categorizes the *first meaningful* outgoing token transfer after each exit (>= max(min_first_hop_token, min_first_hop_fraction*exit)) as a proxy for where the exit goes. It can miss split flows or transfers below threshold.

- unknown_contract: **22** events; **663,716.085 FXS** exited
- no_first_hop_meeting_threshold: **21** events; **204,591.645 FXS** exited
- unknown_eoa: **8** events; **189,037.591 FXS** exited

Top exchange endpoints (by matched count):

- Binance 14: **4**

## Notes / limitations

- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.
- Hop routing is a lower bound: it only detects intermediates that sweep into labeled exchange endpoints within the same window.
- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.

Raw output: see `research/frax-vefxs-exit-routing-3d.json`.
