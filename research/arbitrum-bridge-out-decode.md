# Livepeer Arbitrum → Ethereum L1 — Bridge-out decode (LPT)

- Generated: `2026-01-19T19:44:31.893689+00:00`
- Arbitrum RPC: `https://arb1.arbitrum.io/rpc`
- Ethereum RPC (for code checks): `https://rpc.flashbots.net`
- LPT (Arbitrum): `0x289ba1701c2f088cf0faf8b3705246331cb8a839`
- Gateway router (Arbitrum): `0x5288c571fd7ad117bea99bf60fe0846c4e84f933`

This report decodes calls with selector:
- `0x7b3a3c8b` = `outboundTransfer(address,address,uint256,bytes)`

## Summary

- Decoded burn txs: **85**
- Unique L1 recipients: **10**
- Total bridged (decoded): **7,747,306.224 LPT**

## Top L1 recipients (overall)

| Rank | Recipient (L1) | Type | Total LPT | Share |
|---:|---|---|---:|---:|
| 1 | `0x3d6182c59dbbbbc648570762da316ac8404816ae` | eoa | 1,728,346.916 | 22.31% |
| 2 | `0xc5519fd1129d6d22744e0ac491401fff45d26528` | eoa | 1,159,397.506 | 14.97% |
| 3 | `0x962b029508b1054e2af4184bbaeb5d0c796f7526` | eoa | 1,051,858.717 | 13.58% |
| 4 | `0xe806c101a71522753ea6ea496bafe7b8d61e3baa` | eoa | 812,508.000 | 10.49% |
| 5 | `0xef83273cbd014c4ae7998467c422275a8b37827e` | eoa | 621,439.059 | 8.02% |
| 6 | `0x543df23b9a881fbdbdec7ab3e90f3ff7b905068b` | eoa | 588,040.990 | 7.59% |
| 7 | `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | eoa | 501,070.896 | 6.47% |
| 8 | `0x8d37a11a65b4f2c541af1312bc44f74a078160c7` | eoa | 455,737.253 | 5.88% |
| 9 | `0xadc6e5cbde4fbac7baf58a336edeab8590625baf` | eoa | 441,048.903 | 5.69% |
| 10 | `0xa3bd517dcbdc063c4c24f0d9837bbc5ce869d092` | eoa | 387,857.984 | 5.01% |

## Per whale (top withdrawers by burn total)

### `0x3d6182c59dbbbbc648570762da316ac8404816ae`

- Burn txs decoded: **16**
- Bridged total: **1,728,346.916 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0x3d6182c59dbbbbc648570762da316ac8404816ae` | eoa | 1,728,346.916 | 100.00% |

### `0xc5519fd1129d6d22744e0ac491401fff45d26528`

- Burn txs decoded: **18**
- Bridged total: **1,159,397.506 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0xc5519fd1129d6d22744e0ac491401fff45d26528` | eoa | 1,159,397.506 | 100.00% |

### `0x962b029508b1054e2af4184bbaeb5d0c796f7526`

- Burn txs decoded: **1**
- Bridged total: **1,051,858.717 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0x962b029508b1054e2af4184bbaeb5d0c796f7526` | eoa | 1,051,858.717 | 100.00% |

### `0x60b8eb0947d25194afa248b81a087214beec5cfe`

- Burn txs decoded: **2**
- Bridged total: **812,508.000 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **0.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0xe806c101a71522753ea6ea496bafe7b8d61e3baa` | eoa | 812,508.000 | 100.00% |

### `0xef83273cbd014c4ae7998467c422275a8b37827e`

- Burn txs decoded: **1**
- Bridged total: **621,439.059 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0xef83273cbd014c4ae7998467c422275a8b37827e` | eoa | 621,439.059 | 100.00% |

### `0x543df23b9a881fbdbdec7ab3e90f3ff7b905068b`

- Burn txs decoded: **1**
- Bridged total: **588,040.990 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0x543df23b9a881fbdbdec7ab3e90f3ff7b905068b` | eoa | 588,040.990 | 100.00% |

### `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e`

- Burn txs decoded: **12**
- Bridged total: **501,070.896 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | eoa | 501,070.896 | 100.00% |

### `0x8d37a11a65b4f2c541af1312bc44f74a078160c7`

- Burn txs decoded: **1**
- Bridged total: **455,737.253 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0x8d37a11a65b4f2c541af1312bc44f74a078160c7` | eoa | 455,737.253 | 100.00% |

### `0xadc6e5cbde4fbac7baf58a336edeab8590625baf`

- Burn txs decoded: **2**
- Bridged total: **441,048.903 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0xadc6e5cbde4fbac7baf58a336edeab8590625baf` | eoa | 441,048.903 | 100.00% |

### `0xa3bd517dcbdc063c4c24f0d9837bbc5ce869d092`

- Burn txs decoded: **31**
- Bridged total: **387,857.984 LPT**
- Unique L1 recipients: **1**
- Self-recipient share: **100.00%**

| Rank | Recipient (L1) | Type | Total LPT | Share of sender |
|---:|---|---|---:|---:|
| 1 | `0xa3bd517dcbdc063c4c24f0d9837bbc5ce869d092` | eoa | 387,857.984 | 100.00% |
