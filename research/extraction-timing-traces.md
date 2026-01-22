---
title: "Extraction timing traces (L2→L1→exchange)"
description: "On-chain timing evidence: WithdrawStake → bridge-out → L1 escrow release → exchange routing (often via a repeatable second hop)."
sidebar_label: "Timing traces"
---

# Extraction timing traces (L2→L1→exchange)

This evidence pack attempts to strengthen (or falsify) the on-chain leg of the yield-extraction thesis by linking a tighter, repeatable sequence than a one-off exit:

- Arbitrum `WithdrawStake` (liquid LPT leaves BondingManager)
- Arbitrum bridge-out (LPT burn via gateway router)
- Ethereum L1 escrow release (LPT transfer from the Livepeer L1 escrow)
- Tight-window routing into **labeled** exchange endpoints (best-effort; often via a repeatable second-hop EOA)

This is still **not proof of delta-neutral hedging** (the hedge is mostly off-chain). It is, however, a measurable “cashout routing + timing” fingerprint that is harder to explain as a single discretionary exit.

## Summary

- Generated: `2026-01-22T00:46:05.137369+00:00`
- Arbitrum RPC: `https://arb1.arbitrum.io/rpc`
- Ethereum RPC: `https://rpc.flashbots.net`
- L1 token: `0x58b6a8a3302369daec383334672404ee733ab239`
- L1 escrow: `0x6a23f4940bd5ba117da261f98aae51a8bffa210a`
- L2 window: `5856381` → `423863641`
- L1 window: `14600000` → `24286807`

- Senders analyzed: **10**
- Burn (bridge-out) events: **85**
- Matched `WithdrawStake`→burn (≤ 72.0h): **75**
- Matched burn→L1 escrow receipt (≤ 60.0d): **84**
- Matched L1 receipt→labeled exchange (≤ 72.0h forward, then ≤ 72.0h to exchange): **68**

## Sender table

Columns: Arbitrum bonded stake **now** (snapshot), number of bridge-outs, and how many cycles can be followed all the way to a labeled exchange endpoint with tight timing windows.

| Sender (L2) | Bonded now (LPT) | Burns | Matched withdraw→burn | Matched burn→L1 receipt | Matched receipt→exchange | Median burn→receipt (d) | Median receipt→exchange (h) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `0x3d6182c59dbbbbc648570762da316ac8404816ae` | 0.000 | 16 | 16 | 16 | 11 | 8.08 | 0.19 |
| `0xc5519fd1129d6d22744e0ac491401fff45d26528` | 2,322,141.979 | 18 | 16 | 17 | 16 | 7.34 | 2.85 |
| `0x962b029508b1054e2af4184bbaeb5d0c796f7526` | 0.000 | 1 | 1 | 1 | 0 |  |  |
| `0x60b8eb0947d25194afa248b81a087214beec5cfe` | 0.000 | 2 | 0 | 2 | 2 | 7.01 | 0.18 |
| `0xef83273cbd014c4ae7998467c422275a8b37827e` | 0.000 | 1 | 1 | 1 | 0 |  |  |
| `0x543df23b9a881fbdbdec7ab3e90f3ff7b905068b` | 0.000 | 1 | 1 | 1 | 0 |  |  |
| `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | 283,800.279 | 12 | 8 | 12 | 7 | 7.06 | 0.27 |
| `0x8d37a11a65b4f2c541af1312bc44f74a078160c7` | 0.000 | 1 | 1 | 1 | 1 | 10.68 | 0.39 |
| `0xadc6e5cbde4fbac7baf58a336edeab8590625baf` | 0.000 | 2 | 2 | 2 | 0 |  |  |
| `0xa3bd517dcbdc063c4c24f0d9837bbc5ce869d092` | 592,264.609 | 31 | 29 | 31 | 31 | 7.04 | 0.19 |

## Notes + limitations

- This report relies on the canonical Arbitrum bridge-out signature captured in `research/arbitrum-bridge-out-decode.json`.
- “Exchange” routing is label-set based (best-effort). The absence of a labeled exchange does **not** imply the tokens weren’t sold.
- Many flows route via one or more EOAs on L1 before an exchange deposit; this report only follows **one** intermediate hop.

Raw output: see `research/extraction-timing-traces.json`.
