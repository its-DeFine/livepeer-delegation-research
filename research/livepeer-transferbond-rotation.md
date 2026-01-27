---
title: "Livepeer: TransferBond stake rotation (on-chain)"
description: "Evidence pack: TransferBond activity on Livepeer Arbitrum BondingManager to quantify stake rotation / wallet splitting behavior."
---

# Livepeer: TransferBond stake rotation (on-chain)

- Generated: `2026-01-26T15:37:43.855133+00:00`
- Arbitrum RPC: `https://arb1.arbitrum.io/rpc`
- BondingManager: `0x35bcf3c30594191d53231e4ff333e8a770453e40`
- Range scanned: `422,832,090..425,460,090` (~365d)

## Summary

- TransferBond events: **122**
- Unique senders (oldDelegator): **33**
- Unique recipients (newDelegator): **28**
- Total transferred: **33,803.586 LPT**
- Amount quantiles (LPT): p50=68.504, p90=814.641, p99=2,810.000

## Top senders (by transferred amount)

- `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc`: **9,457.372 LPT** across 9 events
- `0xd00354656922168815fcd1e51cbddb9e359e3c7f`: **7,607.271 LPT** across 9 events
- `0xdb22609515433e664e28067c81704d8266098986`: **2,810.000 LPT** across 1 events
- `0x104a7ca059a35fd4def5ecb16600b2caa1fe1361`: **2,000.000 LPT** across 1 events
- `0x525419ff5707190389bfb5c87c375d710f5fcb0e`: **1,530.314 LPT** across 3 events
- `0x0d509d8b46b072f8fc330942b2e3cc0ac34d6d8d`: **1,128.642 LPT** across 4 events
- `0xbac7744ada4ab1957cbaafef698b3c068beb4fe0`: **856.678 LPT** across 2 events
- `0xb1c579757622d8ca7bd42542cb0325de1c8e1f8d`: **814.641 LPT** across 1 events
- `0x847791cbf03be716a7fe9dc8c9affe17bd49ae5e`: **803.777 LPT** across 1 events
- `0x5bdeedca9c6346b0ce6b17ffa8227a4dace37039`: **800.000 LPT** across 1 events
- `0xbd677e96a755207d348578727aa57a512c2022bd`: **660.988 LPT** across 5 events
- `0xbe8770603daf200b1fa136ad354ba854928e602b`: **638.347 LPT** across 9 events
- `0x3b28a7d785356dc67c7970666747e042305bfb79`: **626.392 LPT** across 4 events
- `0xdc28f2842810d1a013ad51de174d02eaba192dc7`: **517.938 LPT** across 4 events
- `0x4bd850175a4e43afee34ae7b7dcd079a572dd69b`: **447.106 LPT** across 2 events

## Top recipients (by received amount)

- `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877`: **9,457.372 LPT** across 9 events
- `0x708757efe4cdf6766f7a7976b31fa22f83dc41ef`: **7,607.271 LPT** across 9 events
- `0x87861c87d2b8031d1f5028d00e6e37591ff70478`: **2,810.000 LPT** across 1 events
- `0x70ded5d07299d56a7656b286b4c11bafe839c7de`: **2,000.000 LPT** across 1 events
- `0xf53a446a8d95da6738e1d6be459cfb5b895a69bc`: **1,530.314 LPT** across 3 events
- `0x6a51009ba056b349d7d202c7d132ab1e74ce6eb7`: **1,128.642 LPT** across 4 events
- `0x84edef77bcb20dbf0a373673b550c3eff10dbb5d`: **856.678 LPT** across 2 events
- `0x11e6e65625b0722ee136865f2616f3ff73268412`: **814.641 LPT** across 1 events
- `0x13c4299cc484c9ee85c7315c18860d6c377c03bf`: **803.777 LPT** across 1 events
- `0x455a304a1d3342844f4dd36731f8da066efdd30b`: **800.000 LPT** across 1 events
- `0x875bc4617dd691c16914e4414360ad428bd069ab`: **722.450 LPT** across 16 events
- `0xcf599b29a50d0b111455818c914f274c1bcc90ba`: **660.988 LPT** across 5 events
- `0xebb3438c1978e1aa8ff59e89a6e4c3b30b6e765b`: **626.392 LPT** across 4 events
- `0x5fed4e606b613f55b72cfb33f3c06a87abce8c4d`: **517.938 LPT** across 4 events
- `0x44d37300d1848fb795a94014a152f9e4ee4c6cf7`: **447.106 LPT** across 2 events

## Most “split-like” senders (fanout by unique recipient count)

- `0x66970f8b4a5376ed7961e8633a83809e49ad809d`: 1 unique recipients across 8 events
- `0xbd677e96a755207d348578727aa57a512c2022bd`: 1 unique recipients across 5 events
- `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc`: 1 unique recipients across 9 events
- `0x5263e0ce3a97b634d8828ce4337ad0f70b30b077`: 1 unique recipients across 9 events
- `0xd00354656922168815fcd1e51cbddb9e359e3c7f`: 1 unique recipients across 9 events
- `0x525419ff5707190389bfb5c87c375d710f5fcb0e`: 1 unique recipients across 3 events
- `0xbac7744ada4ab1957cbaafef698b3c068beb4fe0`: 1 unique recipients across 2 events
- `0xbe8770603daf200b1fa136ad354ba854928e602b`: 1 unique recipients across 9 events
- `0x5d11abd838073df76e32c495f97fd3239eabb9fb`: 1 unique recipients across 9 events
- `0x2e3a21ae7cdeb48f57fcad1ce16b258d5502ac05`: 1 unique recipients across 2 events
- `0x4bd850175a4e43afee34ae7b7dcd079a572dd69b`: 1 unique recipients across 2 events
- `0x5be44e23041e93cdf9bcd5a0968524e104e38ae1`: 1 unique recipients across 7 events
- `0xd21ee13175e0cf56876e76b0fa4003cd19e9ad2e`: 1 unique recipients across 10 events
- `0xd603d6bf88aa061fcab8fa552026694a7fd005ce`: 1 unique recipients across 2 events
- `0x733da28b0145ff561868e408d2ac8565ebe73aab`: 1 unique recipients across 2 events

## Receipt validation (best-effort)

- Validated events (Unbond+Rebond present): **122** / 122
- Validated amount: **33,803.586 LPT**
- Note: multiple TransferBond calls in one tx can make validation conservative.

## Largest TransferBond events (examples)

- 7,061.796 LPT: `0xd00354656922168815fcd1e51cbddb9e359e3c7f` → `0x708757efe4cdf6766f7a7976b31fa22f83dc41ef` (tx `0x42cea8a0e781b0b3d328c92a01a83d8dd1d4869f247bf9a19140ee3f300d0375`)
- 2,810.000 LPT: `0xdb22609515433e664e28067c81704d8266098986` → `0x87861c87d2b8031d1f5028d00e6e37591ff70478` (tx `0xcab0b89a317bf03cf897c1ad9bd712ac26cb40b52ce614661e74ab9cf71d01d6`)
- 2,000.000 LPT: `0x104a7ca059a35fd4def5ecb16600b2caa1fe1361` → `0x70ded5d07299d56a7656b286b4c11bafe839c7de` (tx `0xf2b4a98d14a5515d01f453e3fc7fd64910defebcc82f83a8a2faa459558e80c5`)
- 1,097.428 LPT: `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc` → `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` (tx `0x5f601efe3ee62a3b9ce407081151b1154828c37ee3d708a808577129fdc0049c`)
- 1,096.558 LPT: `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc` → `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` (tx `0x2335588a230fe48612e3fe7be72728a4a934380c9ad0b8a30d7b0f7df8852116`)
- 1,074.111 LPT: `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc` → `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` (tx `0x62e20c26a9dc7d6886b780076c6bfbd15525f154a73ca3939187e0e3f017d8fd`)
- 1,071.216 LPT: `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc` → `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` (tx `0x2bd6a720a413c5bdc663360dc1f061b0ad980836343caf4e1a1c1afa21d09b8e`)
- 1,071.182 LPT: `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc` → `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` (tx `0x1bf611340414f7ccb43392cf3f4d28445c930c1736d7169961a06f3d9a74ed43`)
- 1,069.313 LPT: `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc` → `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` (tx `0x85df6572623b06a4a7b9d51a5e3ddfc5bd166dcae76f1251359138b6af2f1436`)
- 1,062.171 LPT: `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc` → `0xcfe1ed2d133fbb488929edc15eee5812f5dc8877` (tx `0x742b9b565f314163b9024eae3442db6ab3f3ac4fcbbea572abdc50f15aa78b05`)

## Notes / limitations

- TransferBond indicates stake rotation, not necessarily selling.
- This report does not (yet) attribute *delegate* changes; it focuses on delegator address rotation.
- This report does not prove common ownership, but large fanout patterns are consistent with wallet-splitting behavior.

Raw output: see `research/livepeer-transferbond-rotation.json`.
