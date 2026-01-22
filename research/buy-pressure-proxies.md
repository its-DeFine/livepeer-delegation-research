---
title: "Buy pressure proxies (exchange outflows → bonders)"
description: "On-chain proxies for buy-side demand: labeled exchange outflows on L1 and whether recipients bond on Arbitrum."
sidebar_label: "Buy-side proxies"
---

# Buy pressure proxies (exchange outflows → bonders)

Most LPT buying happens off-chain (CEX order books), so on-chain we use **proxies**:

- L1 LPT transfers **from labeled exchange wallets** → recipient wallets (exchange outflows).
- Whether those recipients **bond on Arbitrum**, and how soon after the first exchange inflow.
- Best-effort overlap with **cashout-heavy** wallets (sell-pressure proxies).

This is not proof of buyers or hedges; treat it as a reproducible signal to combine with other packs.

## Summary

- Generated: `2026-01-22T02:19:47.491403+00:00`
- Ethereum RPC: `https://rpc.flashbots.net`
- Arbitrum RPC: `https://arb1.arbitrum.io/rpc`
- L1 window: `14600000` → `24287265`
- Arbitrum window (Bond scan): `0` → `423885844`
- Labeled exchange wallets scanned: **23**
- Unique unlabeled recipients (any size): **11,637**
- Total unlabeled recipient inbound: **127,182,765.742 LPT**

- Selected recipients (≥ 10000 LPT): **200**
- Selected inbound total: **90,746,628.915 LPT**
- Selected recipients in Arbitrum delegator set: **5**
- Bonded within 30d of first exchange inflow: **4**
- Selected delegator inbound total: **2,067,366.020 LPT** (2.28%)
- Bonded-within-window inbound total: **1,792,981.745 LPT** (1.98%)

## Top recipients (selected)

Columns: inbound from labeled exchanges on L1, whether the address is known as an Arbitrum delegator, and (best-effort) whether it bonded soon after the first inflow.

| Rank | Recipient | Inbound (LPT) | Txs | First inflow | Arbitrum delegator | Bond ≤ window | Bonded now (LPT) | Cashout fp |
|---:|---|---:|---:|---:|:---:|:---:|---:|---:|
| 1 | `0x2110e5ed88b0489797f6a1d997815d2b360fe43b` | 5,144,219.624 | 66 | 2022-05-11 |  |  | 0.000 |  |
| 2 | `0x2d6ee5c8a3b2370cbc0de309bf5d1a4aa09c3918` | 3,569,484.010 | 854 | 2022-08-17 |  |  | 0.000 |  |
| 3 | `0xe3792a9c235d434b702023b33f03c48c41631090` | 3,244,302.705 | 670 | 2022-06-24 |  |  | 0.000 |  |
| 4 | `0x9c3b2c8fa50fa171ba438433b4908bde8922935c` | 2,878,402.250 | 542 | 2022-04-18 |  |  | 0.000 |  |
| 5 | `0x0084dfd7202e5f5c0c8be83503a492837ca3e95e` | 2,706,594.054 | 687 | 2022-06-15 |  |  | 0.000 |  |
| 6 | `0xc1c4a5c41b62989acdbb9a11bbab668158f5d481` | 2,159,847.638 | 1965 | 2024-02-17 |  |  | 0.000 |  |
| 7 | `0xab782bc7d4a2b306825de5a7730034f8f63ee1bc` | 1,810,165.214 | 658 | 2024-01-09 |  |  | 0.000 |  |
| 8 | `0x41fbba5cb38d22b2d80606406944cedd7c97f6f9` | 1,671,120.390 | 234 | 2023-05-27 |  |  | 0.000 |  |
| 9 | `0x7e6af92df2aecd6113325c0b58f821ab1dce37f6` | 1,452,755.063 | 891 | 2023-10-09 |  |  | 0.000 |  |
| 10 | `0x8048498c795c15f6471161ae029f6c888f43cb54` | 1,358,889.028 | 1068 | 2024-09-12 |  |  | 0.000 |  |
| 11 | `0x3c5883c650d600bd543a9b5c8d9a3a6f5d16b8f4` | 1,270,899.991 | 264 | 2022-04-21 |  |  | 0.000 |  |
| 12 | `0x21debfa81fc74415383cfbc597f77ccf6b61334b` | 1,257,224.313 | 245 | 2024-10-23 |  |  | 0.000 |  |
| 13 | `0x3acedc6f89c65a288f25e80d9080898c3ca66776` | 1,229,446.042 | 1358 | 2022-06-25 |  |  | 0.000 |  |
| 14 | `0xd8d6ffe342210057bf4dcc31da28d006f253cef0` | 1,212,171.919 | 678 | 2022-08-18 |  |  | 0.000 |  |
| 15 | `0x22e0b8dd688f34a0cc21709ee64f52fe4de4d599` | 1,077,861.815 | 251 | 2022-07-19 |  |  | 0.000 |  |
| 16 | `0x95b564f3b3bae3f206aa418667ba000afafacc8a` | 1,001,446.700 | 265 | 2022-04-21 |  |  | 0.000 |  |
| 17 | `0x91d40e4818f4d4c57b4578d9eca6afc92ac8debe` | 911,758.378 | 2 | 2025-03-19 |  |  | 0.000 |  |
| 18 | `0x002e1798bff1ea5bcd703133eb61706070080c19` | 876,234.907 | 258 | 2022-06-04 |  |  | 0.000 |  |
| 19 | `0xfee86db2b983a5c4418c314c9bc1d724c0abf929` | 872,562.881 | 213 | 2023-09-05 |  |  | 0.000 |  |
| 20 | `0x5d0492749595406812001ee163b00f1a0506e4a0` | 857,619.424 | 266 | 2022-12-03 |  |  | 0.000 |  |
| 21 | `0x8389f4f008c3a3d72662d2b77f6bee3ca6cc6174` | 827,689.140 | 234 | 2023-08-23 |  |  | 0.000 |  |
| 22 | `0xf217f7facf4e53b334217d3dcb3e86d32974c7c4` | 814,654.908 | 103 | 2023-07-10 |  |  | 0.000 |  |
| 23 | `0xd8b9f62de8b8217ab997df060a47c020c81f9997` | 812,509.000 | 2 | 2024-08-16 |  |  | 0.000 |  |
| 24 | `0x962b029508b1054e2af4184bbaeb5d0c796f7526` | 812,507.000 | 2 | 2025-03-12 | yes | yes | 0.000 | #6 |
| 25 | `0xbdc7b3526f593f6ccbf620efb0c972bea707a941` | 812,434.830 | 4 | 2022-12-19 |  |  | 0.000 |  |
| 26 | `0x1c2a393e3e7d14f4b8b9e9819217c2e8dfdb10d6` | 808,664.321 | 209 | 2022-12-22 |  |  | 0.000 |  |
| 27 | `0x39e274cb173999eca1cc3daf0c3e938d2cd69a50` | 780,857.135 | 409 | 2023-12-20 |  |  | 0.000 |  |
| 28 | `0x20a3a4ae2aacb8bbcfd89dc71280dd18cd9a0cb4` | 768,612.113 | 801 | 2023-12-28 |  |  | 0.000 |  |
| 29 | `0x47513e36b088a366e6fe7aab2c67b37957c35005` | 756,700.160 | 8 | 2023-08-23 |  |  | 0.000 |  |
| 30 | `0x989a69a3e608483ae3f6fb21e2874f5c8fb98697` | 751,628.206 | 343 | 2022-04-21 |  |  | 0.000 |  |
| 31 | `0x9dc54226c0f86245707396255d4fcd87eb55b676` | 689,837.528 | 1 | 2023-04-26 |  |  | 0.000 |  |
| 32 | `0x8fef490d614fce8b93bd6f28835dd35a8b3229a9` | 682,311.090 | 187 | 2023-06-30 |  |  | 0.000 |  |
| 33 | `0x0bec9f000860c03383757265c952969fa6f9a090` | 678,508.502 | 113 | 2023-08-29 |  |  | 0.000 |  |
| 34 | `0xd1305fbda97c035f86fdaa7785fb568c203174e1` | 646,306.345 | 348 | 2022-04-25 |  |  | 0.000 |  |
| 35 | `0xe66baa0b612003af308d78f066bbdb9a5e00ff6c` | 634,583.350 | 259 | 2024-10-24 |  |  | 0.000 |  |
| 36 | `0x22a709eece6ee82293e5fcdeea7ceefdefd499cd` | 587,043.993 | 11 | 2024-07-09 | yes | yes | 0.000 | #19 |
| 37 | `0x771713755f5a887ef7a455220cb493e0aca73120` | 582,124.797 | 43 | 2023-08-10 |  |  | 0.000 |  |
| 38 | `0x3aff86656a65f3d81b3e0b4c4f8d4199f3b3fbde` | 579,822.860 | 666 | 2023-08-09 |  |  | 0.000 |  |
| 39 | `0xa7a5c7602bd8a0b156980b9c41efa781e1af208f` | 572,560.030 | 109 | 2025-08-18 |  |  | 0.000 |  |
| 40 | `0xf733c29e2918271490d8318846f617b16e613be0` | 567,555.490 | 91 | 2025-08-26 |  |  | 0.000 |  |
| 41 | `0x5fa485b644fba4335fdabc820752038c0dcb8cdb` | 557,895.649 | 2 | 2022-12-28 |  |  | 0.000 |  |
| 42 | `0x478271c960137418c9d90082dddbf68aa72e4367` | 535,011.427 | 236 | 2022-05-15 |  |  | 0.000 |  |
| 43 | `0x5d550635f87e21337462b582dff589f552e609ae` | 521,269.561 | 549 | 2022-11-02 |  |  | 0.000 |  |
| 44 | `0xe129188380d48fa09a6a89ac91adc761afdc1612` | 511,923.447 | 762 | 2024-03-26 |  |  | 0.000 |  |
| 45 | `0xfc9161b99a3b0691477e12737163d007600ac262` | 503,262.663 | 147 | 2025-05-30 |  |  | 0.000 |  |
| 46 | `0x37ec907ec1f200fa6b86522d27ba2af478652aa0` | 502,385.810 | 3 | 2023-09-04 |  |  | 0.000 |  |
| 47 | `0xecda6cec1fcf38429138ca06a7bcbbc4415f9586` | 500,000.000 | 1 | 2024-05-14 |  |  | 0.000 |  |
| 48 | `0x5770815b0c2a09a43c9e5aecb7e2f3886075b605` | 485,452.568 | 838 | 2022-11-23 |  |  | 0.000 |  |
| 49 | `0x07a48c5a537d9c7ac079aefe875b209dc8360704` | 484,061.090 | 200 | 2022-05-02 |  |  | 0.000 |  |
| 50 | `0xe5bd360c2336066482324a0298235850eb39da9c` | 470,397.300 | 68 | 2023-04-11 |  |  | 0.000 |  |

## Delegator overlap (selected)

The selected recipients that overlap with the Arbitrum delegator set are rare and skew toward cashout-heavy wallets.

| Rank | Delegator | Inbound (LPT) | First inflow | Bond after inflow (d) | To Livepeer L1 contracts (LPT) | To labeled exchanges (LPT) | Cashout fp |
|---:|---|---:|---:|---:|---:|---:|---:|
| 24 | `0x962b029508b1054e2af4184bbaeb5d0c796f7526` | 812,507.000 | 2025-03-12 | 0.285821 | 812,507.000 | 0.000 | #6 |
| 36 | `0x22a709eece6ee82293e5fcdeea7ceefdefd499cd` | 587,043.993 | 2024-07-09 | 0.072662 | 587,043.993 | 0.000 | #19 |
| 91 | `0x0b13315bc1638ce38805c827f308cb2f1a2be45b` | 274,384.275 | 2023-02-20 | 66.37692 | 274,384.275 | 0.000 |  |
| 121 | `0xc69381073814920d1ce2bb009ac9982a74679814` | 214,959.920 | 2025-04-04 | 0.016944 | 214,959.920 | 0.000 |  |
| 152 | `0x0a776abbaae0e2161d0e131f57e605efbea4b99b` | 178,470.832 | 2024-06-28 | 0.014432 | 178,470.832 | 0.000 |  |

## Notes + limitations

- “Exchange” coverage is label-set based; many exchange wallets are unlabeled.
- Exchange outflows include internal wallet management as well as customer withdrawals; we exclude labeled destinations from the candidate set.
- Seeing an exchange outflow followed by a bond is suggestive, but does not prove that the inflow funded the bond (bridging and wallet reuse can vary).
- Recipient outflows are computed only for the top-N selected recipients and only to labeled exchanges/bridges (best-effort).

Raw output: see `research/buy-pressure-proxies.json`.
