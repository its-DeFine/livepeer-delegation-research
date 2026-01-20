# Livepeer — L1 second-hop follow-up (post-bridge)

- Generated: `2026-01-20T21:45:48.029620+00:00`
- Input: `research/l1-bridge-recipient-followup.json`
- L1 RPC: `https://rpc.flashbots.net`
- L1 token: `0x58b6a8a3302369daec383334672404ee733ab239`
- Range: `14600000` → `24278701`
- Filter: `unknown_eoa` destinations with ≥ **100,000 LPT** inbound from bridge recipients

## Totals (selected addresses)

- Selected addresses: **9**
- Total inbound from bridge recipients: **7,703,391.299 LPT**
- Total outgoing from selected addresses: **10,803,734.108 LPT**

## Key findings (second hop)

- Outgoing to labeled exchanges: **5,509,570.311 LPT** (51.00%)
- Outgoing to unknown EOAs: **5,294,063.798 LPT** (49.00%)
- Outgoing to Livepeer contracts (labeled): **100.000 LPT**
- Outgoing to labeled DEX routers: **0.000 LPT**

Top labeled exchange destinations:
- `0xceb69f6342ece283b2f5c9088ff249b5d0ae66ea` (Coinbase Prime 2 (public label; best-effort)): **4,841,655.964 LPT**
- `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14 (public label; best-effort)): **667,914.347 LPT**

Interpretation: unlike the first hop (bridge recipients → EOAs), the second hop surfaces a material route into labeled exchange hot wallets (e.g., Coinbase Prime, Binance). This suggests that a portion of the bridge-outs are consistent with eventual exchange deposit flows.

## Category totals (outgoing)

| Category | Outgoing (LPT) | Share |
|---|---:|---:|
| exchange | 5,509,570.311 | 51.00% |
| livepeer_contract | 100.000 | 0.00% |
| unknown_eoa | 5,294,063.798 | 49.00% |

## Addresses (summary)

| Rank | Address | Inbound (LPT) | Outgoing (LPT) | Current balance (LPT) | Out txs |
|---:|---|---:|---:|---:|---:|
| 1 | `0x440f103a920a7228d4b6cd5caa13e5f6b9aeb69a` | 1,879,662.540 | 1,990,712.703 | 0.000 | 65 |
| 2 | `0xde346728906a36bfd06f28e9ee35005e2fde51ae` | 1,758,041.090 | 1,758,041.090 | 0.000 | 2 |
| 3 | `0xd8b9f62de8b8217ab997df060a47c020c81f9997` | 1,051,858.700 | 1,864,367.700 | 0.000 | 7 |
| 4 | `0x3941e792c7ab398f0d5fd244a84e2fc2004ed60d` | 812,508.000 | 1,625,016.000 | 0.000 | 3 |
| 5 | `0x6c78ae1d2a5ffdf7917d65e8586015d0933fc7ea` | 621,439.059 | 1,230,706.104 | 0.000 | 6 |
| 6 | `0xa87e90dfa587e7a499ee2f889816c1e4e317fac5` | 501,070.896 | 526,141.289 | 0.000 | 19 |
| 7 | `0xc60a78732f4f2275fb40d12021b6407f92626116` | 455,737.253 | 667,914.347 | 0.000 | 1 |
| 8 | `0x964feae75fd7a02ef728038741dd376eab020754` | 441,048.903 | 441,048.903 | 0.000 | 2 |
| 9 | `0x582c19f83a0383181c1ff15b6768de1005f629c4` | 182,024.858 | 699,785.972 | 0.000 | 16 |

## Addresses (top destinations)

### `0x440f103a920a7228d4b6cd5caa13e5f6b9aeb69a`

- Inbound from bridge recipients: **1,879,662.540 LPT**
- Outgoing in range: **1,990,712.703 LPT** across **65** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xceb69f6342ece283b2f5c9088ff249b5d0ae66ea` | Coinbase Prime 2 (public label; best-effort) | exchange | 1,990,712.703 | 65 |

### `0xde346728906a36bfd06f28e9ee35005e2fde51ae`

- Inbound from bridge recipients: **1,758,041.090 LPT**
- Outgoing in range: **1,758,041.090 LPT** across **2** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xe4ae0de30267a66e8d8327452d535ab671786ab7` |  | unknown_eoa | 1,758,031.090 | 1 |
| `0xac9a3d8fe8d4812a714eca33b885720e1e731530` |  | unknown_eoa | 10.000 | 1 |

### `0xd8b9f62de8b8217ab997df060a47c020c81f9997`

- Inbound from bridge recipients: **1,051,858.700 LPT**
- Outgoing in range: **1,864,367.700 LPT** across **7** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xabac151fab95b3414d8f6cca2397d479cecd76aa` |  | unknown_eoa | 1,051,859.700 | 1 |
| `0x3941e792c7ab398f0d5fd244a84e2fc2004ed60d` |  | unknown_eoa | 812,508.000 | 1 |
| `0x3941d59d68a6e0ac6fbac6d85bfec7b83753d60d` |  | unknown_eoa | 0.000 | 1 |
| `0xabac66e8d30bf82a199ed69577c6c0d4247ac6aa` |  | unknown_eoa | 0.000 | 2 |
| `0xabac3299044de9a2129fa71c6be2fe7e273076aa` |  | unknown_eoa | 0.000 | 2 |

### `0x3941e792c7ab398f0d5fd244a84e2fc2004ed60d`

- Inbound from bridge recipients: **812,508.000 LPT**
- Outgoing in range: **1,625,016.000 LPT** across **3** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xceb69f6342ece283b2f5c9088ff249b5d0ae66ea` | Coinbase Prime 2 (public label; best-effort) | exchange | 1,625,016.000 | 3 |

### `0x6c78ae1d2a5ffdf7917d65e8586015d0933fc7ea`

- Inbound from bridge recipients: **621,439.059 LPT**
- Outgoing in range: **1,230,706.104 LPT** across **6** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x275f6dd19822cae02c9a5d1fc1bfa3591dbe02f2` |  | unknown_eoa | 805,076.104 | 3 |
| `0x0b54420ee63aa04da4cc87064142c6e64b70bb94` |  | unknown_eoa | 425,530.000 | 2 |
| `0x6a23f4940bd5ba117da261f98aae51a8bffa210a` | Livepeer: L1 Escrow | livepeer_contract | 100.000 | 1 |

### `0xa87e90dfa587e7a499ee2f889816c1e4e317fac5`

- Inbound from bridge recipients: **501,070.896 LPT**
- Outgoing in range: **526,141.289 LPT** across **19** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xceb69f6342ece283b2f5c9088ff249b5d0ae66ea` | Coinbase Prime 2 (public label; best-effort) | exchange | 526,141.289 | 19 |

### `0xc60a78732f4f2275fb40d12021b6407f92626116`

- Inbound from bridge recipients: **455,737.253 LPT**
- Outgoing in range: **667,914.347 LPT** across **1** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x28c6c06298d514db089934071355e5743bf21d60` | Binance 14 (public label; best-effort) | exchange | 667,914.347 | 1 |

### `0x964feae75fd7a02ef728038741dd376eab020754`

- Inbound from bridge recipients: **441,048.903 LPT**
- Outgoing in range: **441,048.903 LPT** across **2** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0x5ba44cd09abe5d39673dc9b87547602ce8298138` |  | unknown_eoa | 341,048.903 | 1 |
| `0xac9a3d8fe8d4812a714eca33b885720e1e731530` |  | unknown_eoa | 100,000.000 | 1 |

### `0x582c19f83a0383181c1ff15b6768de1005f629c4`

- Inbound from bridge recipients: **182,024.858 LPT**
- Outgoing in range: **699,785.972 LPT** across **16** txs
- Current L1 balance: **0.000 LPT**

| Destination | Label | Category | Outgoing (LPT) | Txs |
|---|---|---|---:|---:|
| `0xceb69f6342ece283b2f5c9088ff249b5d0ae66ea` | Coinbase Prime 2 (public label; best-effort) | exchange | 699,785.972 | 16 |
