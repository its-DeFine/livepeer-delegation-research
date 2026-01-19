# Livepeer (Ethereum L1) — Wallet origin trace — `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e`

## Snapshot

- Snapshot block: `24269265` — `2026-01-19T13:57:35+00:00` (lag `5`)
- Wallet type: `EOA`
- Bonded now: `311,906.100 LPT`
- Current delegate: `0xda43d85b8d419a9c51bbf0089c9bd5169c23f2f9`

## Bonding history (Bond events)

- Bond events: `52` (with additional: `50`)
- Total additional bonded: `723,840.892 LPT`
- Max bonded (from events): `1,020,530.087 LPT`
- First observed Bond: `2018-08-24T14:14:11+00:00` (block `6205497`) — additional `5,104.877 LPT`, bonded `24,423.806 LPT`, delegate `0x50d69f8253685999b4c74a67ccb3d240e2a56ed6`
- Biggest single add: `2021-07-05T22:58:53+00:00` (block `12770306`) — additional `394,628.606 LPT`, delegate `0xda43d85b8d419a9c51bbf0089c9bd5169c23f2f9` (tx `0xacf92f125a1cd28be4ef3b0e95c3778daff102296687b8eb9ae29713718a544c`)

## Bond deposit destinations (escrows)

| Destination | Total bond deposits (LPT) |
|---|---:|
| `0x505f8c2ee81f1c6fa0d88e918ef0491222e05818` | 396,429.414 |
| `0x8573f2f5a3bd960eee3d998473e50c75cdbe6828` | 327,411.477 |

## Lifecycle totals (BondingManager)

- Unbond events: `18` (total: `1,313,289.079 LPT`)
- WithdrawStake events: `18` (total: `1,313,289.079 LPT`)
- EarningsClaimed events: `25` (rewards: `378,963.985 LPT`, fees: `0.115177 ETH`)

## LPT token transfer summary

- Inbound transfers: `6,924` (unique senders: `28`)
- Outbound transfers: `171` (unique recipients: `24`)
- Total inbound: `2,275,844.773 LPT`
- Total outbound: `2,275,844.773 LPT`
- Net (in - out): `0.000 LPT`

Top inbound senders (by total LPT):

| From | Total inbound (LPT) |
|---|---:|
| `0x505f8c2ee81f1c6fa0d88e918ef0491222e05818` | 1,211,759.079 |
| `0x6a23f4940bd5ba117da261f98aae51a8bffa210a` | 501,070.896 |
| `0x2e0eeaeb1af7565bd5381aaedeb8eeb0b1082d02` | 194,417.452 |
| `0x8573f2f5a3bd960eee3d998473e50c75cdbe6828` | 113,058.519 |
| `0x50d69f8253685999b4c74a67ccb3d240e2a56ed6` | 73,485.923 |
| `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | 50,070.775 |
| `0xa5e37e0ba14655e92deff29f32adbc7d09b8a2cf` | 21,621.557 |
| `0xf89c64db88824c54df24607d64cbafda88ba3268` | 14,901.096 |
| `0x3e78f6520e7dcc58b5e25b50b445bef4c75ecafd` | 12,199.813 |
| `0x2d656f02aa73c13e5727a3a2e0a90b0b1e82f1f0` | 11,404.152 |

Top outbound recipients (by total LPT):

| To | Total outbound (LPT) |
|---|---:|
| `0xf89c64db88824c54df24607d64cbafda88ba3268` | 522,059.548 |
| `0xa87e90dfa587e7a499ee2f889816c1e4e317fac5` | 501,070.896 |
| `0x505f8c2ee81f1c6fa0d88e918ef0491222e05818` | 396,429.414 |
| `0x8573f2f5a3bd960eee3d998473e50c75cdbe6828` | 354,716.055 |
| `0x2a7e552ff8255499115a5543328dbc423b170e3b` | 100,000.000 |
| `0x7b66d3060306d6f54da7731dca7ee2994a303ccc` | 99,000.000 |
| `0x49c5b31bc6f54ba598322bb7359685d5300536b8` | 54,545.450 |
| `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | 50,070.775 |
| `0xb7ddbe0ebcbb7bac36a00d822701ea261c84be35` | 50,000.000 |
| `0xac0c7b17fd3029a15438245b8a433720c13a5d5c` | 50,000.000 |

## Notes

- Bond deposits are inferred by matching the Bond event's `additional` amount to an ERC20 `Transfer` in the same transaction receipt.
- Transfers involving escrow destinations are typically protocol-internal (bond deposits + stake withdrawals), not external purchases.
- See the JSON output for raw tx hashes and evidence rows.
