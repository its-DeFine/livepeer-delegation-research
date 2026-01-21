---
title: "Extraction fingerprints (on-chain proxies)"
description: "A proxy dashboard for systematic reward extraction: rewards claimed vs withdrawn, post-withdraw routing, and whether top withdrawers remain bonded."
sidebar_label: "Extraction fingerprints"
---

# Extraction fingerprints (on-chain proxies)

We cannot directly see off-chain hedges (CEX borrowing / perp shorts) on-chain. But systematic extraction strategies often leave on-chain footprints: frequent claims, reward-withdraw behavior, post-withdraw routing (bridge-outs / EOAs), and cases where wallets keep large bonded stake while continuously withdrawing.

This page summarizes **top-50 wallets by proxy rewards withdrawn** (from `research/earnings-report.json`).

## Topline stats (top-50 cohort)

- Proxy rewards withdrawn (sum): **5,329,277.600 LPT**
- Wallets still bonded ≥ `10k` LPT: **12 / 50**
- Wallets still bonded ≥ `100k` LPT: **4 / 50**

Archetypes (best-effort heuristics):
- `exiter`: **28**
- `mixed`: **10**
- `still bonded (large)`: **4**
- `still bonded (mid)`: **8**

## Wallet table (top-50 by proxy rewards withdrawn)

Columns: proxy rewards withdrawn, rewards claimed, reward-withdraw ratio, current bonded stake (snapshot), claim cadence proxy, and post-withdraw routing shares.

| Rank | Address | Archetype | Proxy rewards withdrawn | Rewards claimed | Ratio | Bonded now | Avg claim interval | Bridge/burn share | EOA share |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `0x3d6182c59dbbbbc648570762da316ac8404816ae` | `exiter` | 912,011.799 | 912,011.799 | 100.00% | 0.000 | 34.4 d | 59.78% | 38.02% |
| 2 | `0x1d97640e2e54a2b28201da4e5ec8cf3785efd871` | `exiter` | 634,144.155 | 634,144.155 | 100.00% | 0.000 | 94.8 d | 2.57% | 97.43% |
| 3 | `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` | `exiter` | 293,837.167 | 293,837.167 | 100.00% | 0.000 | 0.9 d | 0.00% | 25.25% |
| 4 | `0x60b8eb0947d25194afa248b81a087214beec5cfe` | `exiter` | 276,310.212 | 276,310.212 | 100.00% | 0.000 | 329.0 d | 100.00% | 0.00% |
| 5 | `0xf977814e90da44bfa03b6295a0616a897441acec` | `exiter` | 259,777.500 | 259,777.500 | 100.00% | 0.000 | 57.9 d | 4.89% | 87.53% |
| 6 | `0x962b029508b1054e2af4184bbaeb5d0c796f7526` | `exiter` | 239,351.717 | 239,351.717 | 100.00% | 0.000 | 181.0 d | 100.00% | 0.00% |
| 7 | `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | `still bonded (large)` | 170,686.386 | 452,074.160 | 37.76% | 283,800.279 | 129.8 d | 100.00% | 0.00% |
| 8 | `0x9c10672cee058fd658103d90872fe431bb6c0afa` | `exiter` | 162,765.181 | 162,765.181 | 100.00% | 0.000 | 20.3 d | 0.00% | 100.00% |
| 9 | `0x4416a274f86e1db860b513548b672154d43b81b2` | `exiter` | 114,236.000 | 114,236.875 | 100.00% | 0.875 | 33.9 d | 0.00% | 100.00% |
| 10 | `0xd044e4e2499c7a3ab92e284e18851b3462f9c6ad` | `exiter` | 111,445.648 | 111,445.648 | 100.00% | 0.000 | 197.0 d | 0.00% | 41.13% |
| 11 | `0xa20416801ac2eacf2372e825b4a90ef52490c2bb` | `still bonded (mid)` | 104,779.062 | 154,779.760 | 67.70% | 50,000.698 | 35.1 d | 66.66% | 13.36% |
| 12 | `0x4b0e5e54df6d5eccc7b2f838982411dc93253daf` | `mixed` | 97,249.502 | 102,402.241 | 94.97% | 3,422.442 | 4.7 d | 0.00% | 1.62% |
| 13 | `0x2f6c263c2b89001980c05261d878a243fc155e07` | `exiter` | 90,000.000 | 94,883.033 | 94.85% | 0.000 | 414.0 d | 0.00% | 94.29% |
| 14 | `0xe6e1a485fce7e69d4e382240a1bb476b2ebda803` | `still bonded (mid)` | 90,000.000 | 130,910.795 | 68.75% | 57,175.704 | 206.8 d | 0.00% | 51.27% |
| 15 | `0xe6a9a8db8871eef779019a27e57203a65e736aaf` | `still bonded (mid)` | 83,126.356 | 83,126.356 | 100.00% | 33,268.064 | 312.7 d | 0.00% | 22.23% |
| 16 | `0x543df23b9a881fbdbdec7ab3e90f3ff7b905068b` | `exiter` | 76,908.372 | 76,908.372 | 100.00% | 0.000 | 171.0 d | 100.00% | 0.00% |
| 17 | `0x7f1d38b35e1004b8ee2c4fe7be0dfee30367d195` | `exiter` | 76,512.146 | 76,512.146 | 100.00% | 0.000 | 135.7 d | 56.99% | 0.00% |
| 18 | `0x3f0591aa42627a43fe940b1863691b98df84a90b` | `exiter` | 76,389.813 | 76,389.813 | 100.00% | 0.000 | 120.0 d | 56.61% | 0.00% |
| 19 | `0x22a709eece6ee82293e5fcdeea7ceefdefd499cd` | `exiter` | 75,572.676 | 75,572.676 | 100.00% | 0.000 | 23.2 d | 40.03% | 31.96% |
| 20 | `0x84edef77bcb20dbf0a373673b550c3eff10dbb5d` | `still bonded (mid)` | 70,038.790 | 70,038.790 | 100.00% | 90,321.826 | 14.3 d | 20.63% | 79.37% |
| 21 | `0x8f042230c52b4180b0a9c7da284b1ef8b83680f9` | `still bonded (large)` | 70,000.000 | 122,962.812 | 56.93% | 109,136.230 | 249.6 d | 0.00% | 0.00% |
| 22 | `0xc71a8b4fdc83e37647b08566e7bd128ee06e87dc` | `still bonded (mid)` | 70,000.000 | 82,795.756 | 84.55% | 99,795.756 | 155.7 d | 0.00% | 0.00% |
| 23 | `0xfa9acd0be4de121748c0b79b189ad8f143e72591` | `still bonded (mid)` | 58,416.625 | 58,416.625 | 100.00% | 18,416.625 | 133.3 d | 0.00% | 21.05% |
| 24 | `0x40f18cc812e483615984bc471d8b2d16dee02d57` | `exiter` | 53,637.678 | 53,637.678 | 100.00% | 0.000 | 225.0 d | 0.00% | 99.25% |
| 25 | `0xadc6e5cbde4fbac7baf58a336edeab8590625baf` | `exiter` | 52,082.354 | 52,082.354 | 100.00% | 0.000 | 157.5 d | 100.00% | 0.00% |
| 26 | `0x5e27a64bb2743e7b7ebdd03923cbae07605c4dd7` | `exiter` | 50,868.745 | 50,868.745 | 100.00% | 0.000 | 116.0 d | 56.94% | 0.00% |
| 27 | `0x111702c2746c36fd0b942bb87c33de1f03452a20` | `exiter` | 50,325.642 | 50,325.642 | 100.00% | 0.000 | 135.3 d | 56.59% | 0.00% |
| 28 | `0xe4a3a2ba2e6645ad5da7d04773316c5857638d8e` | `exiter` | 49,018.394 | 49,018.394 | 100.00% | 0.000 | 336.0 d | 100.00% | 0.00% |
| 29 | `0xe0a4a877cd0a07da7c08dffebc2546a4713147f2` | `exiter` | 49,011.492 | 49,011.492 | 100.00% | 0.000 | 20.3 d | 0.00% | 100.00% |
| 30 | `0xf4e8ef0763bcb2b1af693f5970a00050a6ac7e1b` | `exiter` | 48,638.063 | 51,254.063 | 94.90% | 0.000 | 13.8 d | 18.42% | 56.66% |
| 31 | `0xac2e50c8f7ac0f82923a7df9d9903f6ec4741919` | `mixed` | 47,140.360 | 49,493.496 | 95.25% | 10.000 | 0.9 d | 0.00% | 100.00% |
| 32 | `0x21d1130dc36958db75fbb0e5a9e3e5f5680238ff` | `mixed` | 46,782.740 | 47,115.213 | 99.29% | 332.474 | 22.5 d | 85.61% | 0.00% |
| 33 | `0xef83273cbd014c4ae7998467c422275a8b37827e` | `exiter` | 46,402.052 | 46,402.052 | 100.00% | 0.000 | 191.0 d | 100.00% | 0.00% |
| 34 | `0xd0aa1b9d0cd06cafa6af5c1af272be88c38aa831` | `exiter` | 45,264.367 | 45,470.145 | 99.55% | 0.000 | 206.6 d | 99.97% | 0.00% |
| 35 | `0x9d61ae5875e89036fbf6059f3116d01a22ace3c8` | `mixed` | 40,979.253 | 42,571.517 | 96.26% | 2,380.253 | 9.0 d | 0.00% | 100.00% |
| 36 | `0x10b21af759129f32c6064adfb85d3ea2a8c0209c` | `mixed` | 40,541.883 | 40,840.130 | 99.27% | 8.247 | 6.1 d | 0.00% | 93.41% |
| 37 | `0xdac817294c0c87ca4fa1895ef4b972eade99f2fd` | `mixed` | 40,442.669 | 120,888.954 | 33.45% | 20.822 | 23.1 d | 3.26% | 70.44% |
| 38 | `0x19b44aead5958af81d4cd5baf0caa8b9b3c64ba2` | `still bonded (large)` | 40,000.000 | 102,786.005 | 38.92% | 149,644.227 | 214.2 d | 0.00% | 0.00% |
| 39 | `0xd00354656922168815fcd1e51cbddb9e359e3c7f` | `exiter` | 38,879.144 | 41,711.355 | 93.21% | 1.000 | 4.5 d | 67.72% | 16.60% |
| 40 | `0x59df6a78a7ac617f00a0175c45949004ae900114` | `exiter` | 38,047.433 | 38,047.433 | 100.00% | 0.000 | 2.4 d | 0.00% | 72.99% |
| 41 | `0x65bb13ffa703f6278f2f33cae2f35da0da1874cb` | `exiter` | 36,393.694 | 36,393.694 | 100.00% | 0.817 | 14.2 d | 35.44% | 38.80% |
| 42 | `0x1e2a215628612cf770d6bf159249af536750eef9` | `still bonded (mid)` | 35,756.966 | 45,660.900 | 78.31% | 10,000.142 | 396.3 d | 0.00% | 100.00% |
| 43 | `0x3bbe84023c11c4874f493d70b370d26390e3c580` | `mixed` | 35,117.510 | 40,053.665 | 87.68% | 4,936.155 | 46.9 d | 41.65% | 0.00% |
| 44 | `0x46ca88ccbe7cc9af9b9dd9e9a14c4b81f0ef14e6` | `still bonded (large)` | 35,000.000 | 93,128.879 | 37.58% | 150,953.753 | 261.4 d | 0.00% | 0.00% |
| 45 | `0x3a63afc862107fc21baf40a5025db7c4062ac2da` | `exiter` | 34,790.497 | 34,790.497 | 100.00% | 0.000 | 22.9 d | 0.00% | 50.46% |
| 46 | `0x22b544d19ffe43c6083327271d9f39020da30c65` | `mixed` | 33,286.812 | 104,184.153 | 31.95% | 0.000 | 71.6 d | 78.74% | 0.00% |
| 47 | `0xa5d8da258a75312f117324d8e14387c31584c41d` | `exiter` | 32,726.367 | 32,726.367 | 100.00% | 0.000 | 406.0 d | 0.00% | 100.00% |
| 48 | `0x9d2b4e5c4b1fd81d06b883b0aca661b771c39ea3` | `mixed` | 32,163.895 | 45,272.046 | 71.05% | 108.151 | 201.5 d | 100.00% | 0.00% |
| 49 | `0xa6a9eb29e786b5233bd99c0ba28be882fe954a0e` | `still bonded (mid)` | 31,323.377 | 68,743.334 | 45.57% | 37,419.957 | 60.4 d | 0.00% | 39.56% |
| 50 | `0xb5164d6b780786338c52f4787abba0e4a371af4d` | `mixed` | 31,097.107 | 34,878.561 | 89.16% | 3,400.004 | 3.1 d | 0.00% | 0.00% |

## Top still-bonded withdrawers (subset)

These are the most relevant wallets for a “harvest without exit” fingerprint (still bonded while withdrawing).

| Rank | Address | Bonded now | Proxy rewards withdrawn | Bridge/burn share |
|---:|---|---:|---:|---:|
| 7 | `0x86abf78ac7ef44423873dabff35fe3e462b1ff6e` | 283,800.279 | 170,686.386 | 100.00% |
| 44 | `0x46ca88ccbe7cc9af9b9dd9e9a14c4b81f0ef14e6` | 150,953.753 | 35,000.000 | 0.00% |
| 38 | `0x19b44aead5958af81d4cd5baf0caa8b9b3c64ba2` | 149,644.227 | 40,000.000 | 0.00% |
| 21 | `0x8f042230c52b4180b0a9c7da284b1ef8b83680f9` | 109,136.230 | 70,000.000 | 0.00% |
| 22 | `0xc71a8b4fdc83e37647b08566e7bd128ee06e87dc` | 99,795.756 | 70,000.000 | 0.00% |
| 20 | `0x84edef77bcb20dbf0a373673b550c3eff10dbb5d` | 90,321.826 | 70,038.790 | 20.63% |
| 14 | `0xe6e1a485fce7e69d4e382240a1bb476b2ebda803` | 57,175.704 | 90,000.000 | 0.00% |
| 11 | `0xa20416801ac2eacf2372e825b4a90ef52490c2bb` | 50,000.698 | 104,779.062 | 66.66% |
| 49 | `0xa6a9eb29e786b5233bd99c0ba28be882fe954a0e` | 37,419.957 | 31,323.377 | 0.00% |
| 15 | `0xe6a9a8db8871eef779019a27e57203a65e736aaf` | 33,268.064 | 83,126.356 | 0.00% |
| 23 | `0xfa9acd0be4de121748c0b79b189ad8f143e72591` | 18,416.625 | 58,416.625 | 0.00% |
| 42 | `0x1e2a215628612cf770d6bf159249af536750eef9` | 10,000.142 | 35,756.966 | 0.00% |

## Notes + limitations

- This report is **not proof** of delta-neutral hedging; it is a set of on-chain proxies.
- Claim cadence is approximate (we only use first/last claim day + number of claim events).
- Post-withdraw routing uses a small label set; unlabeled EOAs can still be CEX deposit wallets.
- For bridge-outs specifically, see `/research/l1-bridge-recipient-followup` and `/research/l1-bridge-recipient-second-hop`.
