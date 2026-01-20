---
title: L1 follow-up (bridge-outs)
description: Where major Arbitrum bridge-out recipients route LPT on Ethereum L1 (contracts vs EOAs vs labeled endpoints).
sidebar_label: L1 follow-up (bridge-outs)
---

# L1 follow-up for Arbitrum bridge-outs (LPT)

- Generated: `2026-01-20T23:35:04.404731+00:00`
- L1 RPC: `https://rpc.flashbots.net`
- L1 LPT token: `0x58b6a8a3302369daec383334672404ee733ab239`
- Inputs: `research/arbitrum-bridge-out-decode.json` + `data/labels.json`
- L1 block range: `14600000` → `24279306`
- Unique recipients analyzed: **10**
- Total bridged (decoded on L2): **7,747,306.224 LPT**
- Total outgoing on L1 (transfers from recipients): **9,133,234.864 LPT**

## Key findings (from on-chain L1 transfers)

- Outgoing / bridged ratio (upper bound): **117.89%**
- To `dex_router` (our small label set): **0.000 LPT**
- To `exchange` (our small label set): **0.000 LPT**
- To Livepeer contracts (labeled): **1,412,595.000 LPT**
- To unknown EOAs: **7,720,639.863 LPT** (84.53%)

Interpretation: in this sample, we do not observe whales routing bridged LPT to known DEX routers on L1. Most value goes to EOAs (potentially CEX deposit wallets or self-custody) plus Livepeer’s `L1 Escrow`. This is consistent with “bridge-out ≠ immediate DEX selling”, but it does not prove whether a given EOA sold on a CEX.

## Category totals (outgoing)

| Category | Outgoing (LPT) | Share |
|---|---:|---:|
| livepeer_contract | 1,412,595.000 | 15.47% |
| unknown_eoa | 7,720,639.863 | 84.53% |

## Recipients (summary)

| Rank | Recipient | Bridged (LPT) | Current balance (LPT) | Outgoing (LPT) | Out txs |
|---:|---|---:|---:|---:|---:|
| 1 | `0x3d6182c59dbbbbc648570762da316ac8404816ae` | 1,728,346.916 | 0.000 | 1,728,459.008 | 39 |
| 2 | `0xc5519fd1129d6d22744e0ac491401fff45d26528` | 1,159,397.506 | 0.000 | 1,118,331.056 | 107 |
| 3 | `0x962b029508b1054e2af4184bbaeb5d0c796f7526` | 1,051,858.717 | 0.017 | 1,864,375.700 | 10 |
| 4 | `0xe806c101a71522753ea6ea496bafe7b8d61e3baa` | 812,508.000 | 0.000 | 812,508.000 | 2 |
| 5 | `0xef83273cbd014c4ae7998467c422275a8b37827e` | 621,439.059 | 0.000 | 621,439.059 | 3 |
| 6 | `0x543df23b9a881fbdbdec7ab3e90f3ff7b905068b` | 588,040.990 | 0.000 | 588,040.990 | 1 |
| 7 | `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | 501,070.896 | 0.000 | 515,461.911 | 69 |
| 8 | `0x8d37a11a65b4f2c541af1312bc44f74a078160c7` | 455,737.253 | 0.000 | 455,737.253 | 1 |
| 9 | `0xadc6e5cbde4fbac7baf58a336edeab8590625baf` | 441,048.903 | 0.000 | 441,048.903 | 2 |
| 10 | `0xa3bd517dcbdc063c4c24f0d9837bbc5ce869d092` | 387,857.984 | 0.000 | 987,832.984 | 74 |

## Recipients (top destinations)

Tip: expand only the wallets you care about.

<details>
<summary><code>0x3d6182c59dbbbbc648570762da316ac8404816ae</code> — bridged <b>1,728,346.916 LPT</b>, outgoing <b>1,728,459.008 LPT</b> (39 txs)</summary>

- Bridged (decoded on L2): **1,728,346.916 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **1,728,459.008 LPT** across **39** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xde346728906a36bfd06f28e9ee35005e2fde51ae` |  | unknown_eoa | 1,170,000.100 | 2 |
| `0x440f103a920a7228d4b6cd5caa13e5f6b9aeb69a` |  | unknown_eoa | 383,837.370 | 18 |
| `0x582c19f83a0383181c1ff15b6768de1005f629c4` |  | unknown_eoa | 171,661.988 | 11 |
| `0x582c45936c34c699360f85147777ce7760b629c4` |  | unknown_eoa | 2,847.550 | 3 |
| `0x6a23f4940bd5ba117da261f98aae51a8bffa210a` | Livepeer: L1 Escrow | livepeer_contract | 112.000 | 1 |
| `0x582c390093e9d401504a03c4b2e0247052df29c4` |  | unknown_eoa | 0.000 | 1 |
| `0x440fef576863b530fc4735d0ea0b7b682d25b69a` |  | unknown_eoa | 0.000 | 3 |

</details>

<details>
<summary><code>0xc5519fd1129d6d22744e0ac491401fff45d26528</code> — bridged <b>1,159,397.506 LPT</b>, outgoing <b>1,118,331.056 LPT</b> (107 txs)</summary>

- Bridged (decoded on L2): **1,159,397.506 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **1,118,331.056 LPT** across **107** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x440f103a920a7228d4b6cd5caa13e5f6b9aeb69a` |  | unknown_eoa | 1,118,330.056 | 26 |
| `0x6a23f4940bd5ba117da261f98aae51a8bffa210a` | Livepeer: L1 Escrow | livepeer_contract | 1.000 | 1 |
| `0x440f64f3e87e4de248da2a3fcfe0c217963eb69a` |  | unknown_eoa | 0.000 | 2 |
| `0x440f2e9422df3b52627e281b7e9179a28851069a` |  | unknown_eoa | 0.000 | 10 |
| `0x440f69ce84c54a967ecd7211923f4d88a657b69a` |  | unknown_eoa | 0.000 | 29 |
| `0x440f6723f73e0d1004374109c9dfcd921d21b69a` |  | unknown_eoa | 0.000 | 9 |
| `0x4404a9cd59f4f0916c0e62a98fc890b17f6fb69a` |  | unknown_eoa | 0.000 | 1 |
| `0x440f4d5747334c36576c186a455f3bd19d5ab69a` |  | unknown_eoa | 0.000 | 22 |
| `0x44088af6295472c4fb4fd15126905f95ce78b69a` |  | unknown_eoa | 0.000 | 7 |

</details>

<details>
<summary><code>0x962b029508b1054e2af4184bbaeb5d0c796f7526</code> — bridged <b>1,051,858.717 LPT</b>, outgoing <b>1,864,375.700 LPT</b> (10 txs)</summary>

- Bridged (decoded on L2): **1,051,858.717 LPT**
- Current L1 LPT balance: **0.017 LPT**
- Outgoing transfers in range: **1,864,375.700 LPT** across **10** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xd8b9f62de8b8217ab997df060a47c020c81f9997` |  | unknown_eoa | 1,051,858.700 | 2 |
| `0x6a23f4940bd5ba117da261f98aae51a8bffa210a` | Livepeer: L1 Escrow | livepeer_contract | 812,507.000 | 1 |
| `0x962b029508b1054e2af4184bbaeb5d0c796f7526` |  | unknown_eoa | 10.000 | 1 |
| `0xd8b9860df113459cecf6a4d55e37aa0fb33d9997` |  | unknown_eoa | 0.000 | 3 |
| `0xd8b9b50defd126e98322fc0e679382021f469997` |  | unknown_eoa | 0.000 | 3 |

</details>

<details>
<summary><code>0xe806c101a71522753ea6ea496bafe7b8d61e3baa</code> — bridged <b>812,508.000 LPT</b>, outgoing <b>812,508.000 LPT</b> (2 txs)</summary>

- Bridged (decoded on L2): **812,508.000 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **812,508.000 LPT** across **2** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x3941e792c7ab398f0d5fd244a84e2fc2004ed60d` |  | unknown_eoa | 812,508.000 | 2 |

</details>

<details>
<summary><code>0xef83273cbd014c4ae7998467c422275a8b37827e</code> — bridged <b>621,439.059 LPT</b>, outgoing <b>621,439.059 LPT</b> (3 txs)</summary>

- Bridged (decoded on L2): **621,439.059 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **621,439.059 LPT** across **3** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x6c78ae1d2a5ffdf7917d65e8586015d0933fc7ea` |  | unknown_eoa | 621,439.059 | 2 |
| `0x6c709951b72320aef8fd431270edf159170fc7ea` |  | unknown_eoa | 0.000 | 1 |

</details>

<details>
<summary><code>0x543df23b9a881fbdbdec7ab3e90f3ff7b905068b</code> — bridged <b>588,040.990 LPT</b>, outgoing <b>588,040.990 LPT</b> (1 txs)</summary>

- Bridged (decoded on L2): **588,040.990 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **588,040.990 LPT** across **1** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xde346728906a36bfd06f28e9ee35005e2fde51ae` |  | unknown_eoa | 588,040.990 | 1 |

</details>

<details>
<summary><code>0x86abf78ac7ef44423873dabff35fe3e462b1ff6e</code> — bridged <b>501,070.896 LPT</b>, outgoing <b>515,461.911 LPT</b> (69 txs)</summary>

- Bridged (decoded on L2): **501,070.896 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **515,461.911 LPT** across **69** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xa87e90dfa587e7a499ee2f889816c1e4e317fac5` |  | unknown_eoa | 501,070.896 | 18 |
| `0x7c9342a4c5a638483f0b7546fccdfc491ddd5c1a` |  | unknown_eoa | 14,391.014 | 2 |
| `0xa874c016eae586fcb6ed5b39adf2d22e4807fac5` |  | unknown_eoa | 0.000 | 1 |
| `0xa87e963c5d2eec7a9d4a11a4a461b1cfeb67fac5` |  | unknown_eoa | 0.000 | 1 |
| `0xa87e8a6e61eab27819fadc3abb5fb33190122ac5` |  | unknown_eoa | 0.000 | 24 |
| `0xa87ed76868a18527e580c52bcd9c98887157fac5` |  | unknown_eoa | 0.000 | 23 |

</details>

<details>
<summary><code>0x8d37a11a65b4f2c541af1312bc44f74a078160c7</code> — bridged <b>455,737.253 LPT</b>, outgoing <b>455,737.253 LPT</b> (1 txs)</summary>

- Bridged (decoded on L2): **455,737.253 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **455,737.253 LPT** across **1** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xc60a78732f4f2275fb40d12021b6407f92626116` |  | unknown_eoa | 455,737.253 | 1 |

</details>

<details>
<summary><code>0xadc6e5cbde4fbac7baf58a336edeab8590625baf</code> — bridged <b>441,048.903 LPT</b>, outgoing <b>441,048.903 LPT</b> (2 txs)</summary>

- Bridged (decoded on L2): **441,048.903 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **441,048.903 LPT** across **2** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x964feae75fd7a02ef728038741dd376eab020754` |  | unknown_eoa | 441,048.903 | 2 |

</details>

<details>
<summary><code>0xa3bd517dcbdc063c4c24f0d9837bbc5ce869d092</code> — bridged <b>387,857.984 LPT</b>, outgoing <b>987,832.984 LPT</b> (74 txs)</summary>

- Bridged (decoded on L2): **387,857.984 LPT**
- Current L1 LPT balance: **0.000 LPT**
- Outgoing transfers in range: **987,832.984 LPT** across **74** txs

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x6a23f4940bd5ba117da261f98aae51a8bffa210a` | Livepeer: L1 Escrow | livepeer_contract | 599,975.000 | 1 |
| `0x440f103a920a7228d4b6cd5caa13e5f6b9aeb69a` |  | unknown_eoa | 377,495.114 | 52 |
| `0x582c19f83a0383181c1ff15b6768de1005f629c4` |  | unknown_eoa | 10,362.870 | 2 |
| `0x440fef576863b530fc4735d0ea0b7b682d25b69a` |  | unknown_eoa | 0.000 | 4 |
| `0x440f64f3e87e4de248da2a3fcfe0c217963eb69a` |  | unknown_eoa | 0.000 | 6 |
| `0x440f2e9422df3b52627e281b7e9179a28851069a` |  | unknown_eoa | 0.000 | 1 |
| `0x440f4d5747334c36576c186a455f3bd19d5ab69a` |  | unknown_eoa | 0.000 | 4 |
| `0x440f69ce84c54a967ecd7211923f4d88a657b69a` |  | unknown_eoa | 0.000 | 4 |

</details>
