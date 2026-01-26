---
title: "Aave (stkAAVE Redeem): exit → exchange routing (on-chain)"
description: "Evidence pack: on-chain exit events and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."
---

# Aave (stkAAVE Redeem): exit → exchange routing (on-chain)

- Generated: `2026-01-26T15:24:46.899800+00:00`
- Ethereum RPC: `https://ethereum.publicnode.com`
- Exit contract: `0x4da27a545c0c5b758a6ba100e3a049001de870f5`
- Exit event: `Redeem(address,address,uint256,uint256)` (topic0 `0x3f693fff038bb8a046aa76d9516190ac7444f7d69cf952c4cbdc086fdef2d6fc`)
- Token: `0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9` (AAVE)

## Exit events (observed)

- Range scanned: `23,671,815..24,319,815` (~90d)
- Exit events: **938**
- Unique recipients: **849**
- Total exited (events): **518,033.989 AAVE**

## Tight-window routing to labeled exchanges (top recipients)

- Window: **3 days** (~21,600 blocks)
- Exchange label set size: **105** addresses (`data/labels.json`)
- Top recipients analyzed: **50**

- Exit events considered (top recipients): **81**
- Exit amount considered: **472,247.006 AAVE**
- Direct matched within window (events): **0**
- Direct matched amount (lower bound): **0.000 AAVE**
- Second hop matched within window (events): **7**
- Second hop matched amount (lower bound): **15,940.009 AAVE**
- Third hop matched within window (events): **0**
- Third hop matched amount (lower bound): **0.000 AAVE**
- Total matched (events): **7**
- Total matched amount (lower bound): **15,940.009 AAVE**

## Arbitrum follow-up (L1 bridge deposit → exchange routing; best-effort)

- Arbitrum RPC: `https://arb1.arbitrum.io/rpc`
- L1 gateway router: `0x72ce9c846789fdb6fc1f34ac4ad25dd9ef7031ef`
- L1 token gateway: `0xa3a7b6f88361f48403514059f1f16c8e78d60eec`
- L2 token address: `0xba5ddd1f9d7f570dc94a51479a000e3bce967196`
- Follow-up window after deposit: **7 days**
- Exit events with detected Arbitrum deposit: **0**
- Exit amount (events) with deposit: **0.000 AAVE**
- Bridged token amount (outboundTransfer sum): **0.000 AAVE**
- Of those, matched to labeled exchange on Arbitrum (events): **0**
- Matched exit amount (events): **0.000 AAVE**
- Matched token amount to exchanges on Arbitrum: **0.000 AAVE**

## Post-exit roles (heuristic; top recipients)

These roles are a *best-effort* way to explain what “unknown EOAs / contracts” are doing after exit. They do **not** replace strict exchange routing.

- unknown_contract: **25** events; **116,197.142 AAVE** (24.61%)
- unknown_eoa: **24** events; **26,987.825 AAVE** (5.71%)
- hold_no_first_hop: **20** events; **74,386.073 AAVE** (15.75%)
- exchange_strict: **7** events; **15,940.009 AAVE** (3.38%)
- dex_router_interaction: **5** events; **238,735.958 AAVE** (50.55%)

Top intermediates on paths that end at labeled exchanges (by count):

- 0xa16a27cff6bd4f2dc3e6ca2cab3b244df543e27b: **2** (example downstream: Binance 14)
- 0x2ca4d4b110a54e1428318fb2f77c5c46c15c7a2b: **1** (example downstream: Binance 14)
- 0x4cfdd9ebf908cb9ca39afae40a0f0acfd5a28be4: **1** (example downstream: Binance 14)
- 0x04e804c048f4b589befdc9ecfffefe5d187c9b71: **1** (example downstream: Binance 14)
- 0x8a5247e382f9e516bab014103b8c16b07b840d92: **1** (example downstream: Binance 14)
- 0x41a8e187f9be0d83fe963bb56a44c10b3b92becb: **1** (example downstream: Gate.io 1)

## First hop destinations (top recipients; within window)

This categorizes the *first meaningful* outgoing token transfer after each exit (>= max(min_first_hop_token, min_first_hop_fraction*exit)) as a proxy for where the exit goes. It can miss split flows or transfers below threshold.

- unknown_eoa: **31** events; **42,927.834 AAVE** exited
- no_first_hop_meeting_threshold: **25** events; **313,122.031 AAVE** exited
- unknown_contract: **25** events; **116,197.142 AAVE** exited

Top exchange endpoints (by matched count):

- Binance 14: **6**
- Gate.io 1: **1**

## Notes / limitations

- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.
- Hop routing is a lower bound: it only detects intermediates that sweep into labeled exchange endpoints within the same window.
- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.

Raw output: see `research/aave-stkaave-redeem-exit-routing-3d.json`.
