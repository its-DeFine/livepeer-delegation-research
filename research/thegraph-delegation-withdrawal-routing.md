---
title: "The Graph: delegation withdrawals → exchange routing (on-chain)"
description: "Evidence pack: delegator withdrawals from The Graph staking contract and tight-window routing into labeled exchange endpoints (direct + 2-hop + 3-hop)."
---

# The Graph: delegation withdrawals → exchange routing (on-chain)

- Generated: `2026-01-24T00:31:42.474358+00:00`
- Ethereum RPC: `https://ethereum.publicnode.com`
- Staking contract: `0xF55041E37E12cD407ad00CE2910B8269B01263b9`
- GRT token: `0xc944e90c64b2c07662a292be6244bdf05cda44a7`

## Protocol parameters (on-chain)

- `thawingPeriod()`: **201,600 blocks** (Indexer unstake → withdraw delay)
- `delegationUnbondingPeriod()`: **28 epochs** (Delegator undelegate → withdraw delay)

## Delegation withdrawals (events)

- Range scanned: `23,005,043..24,301,043` (~180d)
- `StakeDelegatedWithdrawn` events: **168**
- Unique delegators: **147**
- Total withdrawn (delegators): **10,669,470.803 GRT**

## Tight-window routing to labeled exchanges (top delegators)

- Window: **30 days** (~216,000 blocks)
- Exchange label set size: **37** addresses (`data/labels.json`)
- Top delegators analyzed: **50**

- Withdraw events considered (top delegators): **60**
- Withdrawn amount considered: **10,491,820.509 GRT**
- Direct matched to labeled exchange within window (events): **0**
- Direct matched amount (lower bound): **0.000 GRT**
- Second hop matched to labeled exchange within window (events): **5**
- Second hop matched amount (lower bound): **353,110.972 GRT**
- Third hop matched to labeled exchange within window (events): **8**
- Third hop matched amount (lower bound): **925,283.442 GRT**
- Total matched (events): **13**
- Total matched amount (lower bound): **1,278,394.414 GRT**

Top exchange endpoints (by matched count):

- Binance 14: **13**

## Example traces (largest matched withdrawals)

Second hop (delegator → intermediate → exchange):

- Delegator `0x9cf14dd5b4347c55da5b1d2f2393cf54cc457ebe` withdrew 173434.513682545372691747 GRT (tx `0x7479ff02ea5066bff7b3ceff822fa40129c1f7855ea376caabe5004826d9b4f2`) → `0x9cd27859b3c88e6ca7f1015882eb052de1ca1dc5` (EOA) in 377 blocks (tx `0x483b10ece3216c6368f5e5ba1e11ad8a98bb2e56d02e0986a858870ad9038507`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 44 blocks (tx `0x89c16b31370e214ade1971f235b894bc47228eb493be44b1be9bc2223a6cda36`)
- Delegator `0x29fc5aacd613410b68c9c08d4e1656e3c890e482` withdrew 96440.525603600459779881 GRT (tx `0x96fcf5fcd67a88c42cf202eee6bf7f4c4b4cbf2fe47ba5cc1d0c93ff32469914`) → `0x7edf25752d63fadfac9fb410133b9bc95052fb1f` (EOA) in 36 blocks (tx `0xa0960edb85a4c795b51f9cdd4edce5affc32f6f645c899dcc9d037000f0b6b81`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 47 blocks (tx `0xc5efebcc5c4ba2da07b61f32947ac8fc7a222bb05d1cdc56e8da3a450ef5f42a`)
- Delegator `0x3c2aa5167342b42c82d45e38ed94d5093243bc26` withdrew 61262.360509370615783277 GRT (tx `0xd80c4cfe866b67af50e256982571369e0da7f0f44d4f26ec3fc7d2a24ef801fa`) → `0x27f7785d7ac9d5487d06d7eda8bf5d595f4b5869` (EOA) in 20 blocks (tx `0x8c4d9fc4b1f3dcd4ee0f4bca79084ab5eefa9b05375a5ce671b54f326766f74c`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 18 blocks (tx `0xb2096d88200914b957a4af13ba6b3481f80f1fb83cdace7d60689e581d024199`)
- Delegator `0x8f7cae3e51bd832ee0e2cdb73de4723010acff5c` withdrew 12521.078666516765133949 GRT (tx `0x29f82a1b515797e389e4f045ae8162e6c91f0efd60cb3bbc0dc2a674dd39ed72`) → `0xd646361c88c08b1fa52e5f4636a012989865fb26` (EOA) in 19 blocks (tx `0xde5835e17bbfa9617a6850fdecb394aea4e62db1064065735f52593a546ac605`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 31 blocks (tx `0xc9b2bd6e6e7c51458157e40b354d5b661e1c66c48e43becaece86ab7ab7ef5ad`)
- Delegator `0x70643f3e0c2f7bc94aa1fd71f427b890bb15478a` withdrew 9452.493339223015879416 GRT (tx `0xb0f8164fcec075334f331cb953792092e4a0b9731390eb31bd8d5b1661ba6a34`) → `0xeff7f327c2e757b445609b323c5e2d5aa2b2f594` (EOA) in 4404 blocks (tx `0xfa65c9faa442856a55536c064854349870183740e079dfc1f2af1eafd8da79a6`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 75 blocks (tx `0x2076dfc4edaadcb4e7e13bdd8031ad4db5e3d782bf142acba8a73e08dcd8cbf0`)

Third hop (delegator → intermediate → intermediate → exchange):

- Delegator `0x310de0d64b23568dd8a773149c016ddcdbafa2e7` withdrew 219270.619682907077738959 GRT (tx `0x4518ed808e0c08c955b928c7904e4013ab0f34cde755292333ab44107c628226`) → `0xcbdfa05673237dbd7947ccb97ac8d87ff6d55aec` (EOA) in 24 blocks (tx `0x4d729f41ad548b6c7d2b1a0d5e46c131ce6d768e889a150b8e99e60b8e0c5534`) → `0xdc716126040b616219d5fd322c4f359e5aca8a43` (EOA) in 1435 blocks (tx `0xd510fa58e74a00b7dbca16a57131a6dc7300e05a25f2c3836719733d5b9aaa16`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 857 blocks (tx `0x19fa9725f153a0ca4c8bca18000c4395222c061baa2216efb557a21806418cce`)
- Delegator `0xeea6303af45655cf91d028dcfe0968daf51d749f` withdrew 146180.40946742772377752 GRT (tx `0xa816e25fe467b619b169f0cf31a82f3d32e2399f93c167b74f505203e1b66f97`) → `0x69ebb9fa085f9ba64de06519dd3670e38957ba16` (EOA) in 18 blocks (tx `0xcbf59131281461d666663d1bb6762f1bb15d50279336280ab17bf043df190760`) → `0xdc716126040b616219d5fd322c4f359e5aca8a43` (EOA) in 1417 blocks (tx `0x679c790b9282288b3e5fbbe40ebf9079cab91a412e1a13297a2a199b2168792a`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 839 blocks (tx `0x19fa9725f153a0ca4c8bca18000c4395222c061baa2216efb557a21806418cce`)
- Delegator `0x38bafdd35f9774fb504f2f62ddcd9a87f539ae20` withdrew 146180.40946742772377752 GRT (tx `0xf2664db245ba5efe130ddcffbb5eb946bfb24aaedc024a0bbf21cfdd82e3cd47`) → `0xe49bd0471d4b2faf1df07887b2a2fcb916f6cf22` (EOA) in 9 blocks (tx `0xa052ec1f1a95b6e40e951a67f271f819aad486adb95c90bc575b92d6d66dfe6a`) → `0xdc716126040b616219d5fd322c4f359e5aca8a43` (EOA) in 1396 blocks (tx `0x8e4244a99a507e093bab95d4fb3148b8d99b090d5af4642e62167645999e75be`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 837 blocks (tx `0x19fa9725f153a0ca4c8bca18000c4395222c061baa2216efb557a21806418cce`)
- Delegator `0x90cf222639b8697ec167beb94677daff72a269c6` withdrew 110261.25631906741661559 GRT (tx `0x5059db15e63c1f735cf0361d57f674260468adad6f9fb0ffad28309dc744f8c7`) → `0x68a335b5ebdcb62567ef548dc08c8e61ac07b153` (EOA) in 44 blocks (tx `0x14763ab32bc5c9a0a7d0c63d69c5f432302cd8e8555b76d79235b7cfeb7cdaa0`) → `0x736b76e0232b77b12ab80b747ed8e266b9073cbd` (EOA) in 25 blocks (tx `0xe4fd27ccbfde15025036cfd2161e99ad3dcbc1d832e072797fbe13dd59fd0ea4`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 15 blocks (tx `0x46bc3db34c27df153a917f70dc0e1b8688ed24ea6d5fd2650cdf6d639f11a15b`)
- Delegator `0xd2a08929448d9526d2742245f108b8812852a827` withdrew 90000.41040901706366218 GRT (tx `0x68b64cf4bc3b7df5f58bedd2fc2daa3e5bd74edbdbeab7515aa80fe3f44a55d8`) → `0x68a02577e281488b21d147caa1ffdc7c298d7d1c` (EOA) in 1684 blocks (tx `0xf109601e241b1fe2b85ed64b432848b561fc5e00e241389b99e3f4c037ea0e13`) → `0x22a9d3614902051793338f5f11c95dc42b4ff884` (EOA) in 2164 blocks (tx `0x8d7dd37a26721d760ac619c92ba507af7818b277f99d14dd5071154d293c7ad3`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 41 blocks (tx `0x3fc4727828649e588b9e58d5604ee147cba2a1db2325478495d65c3b4800a3b4`)
- Delegator `0x117eec859b7652680212c97aaa152a57344bd3c3` withdrew 85480.905324555993446649 GRT (tx `0x4f5d4741f47ebd5d457a30c28bb433d9e535f3d1912cc8e79816c8a142fa1f2a`) → `0xf4ddc3cfdbd298dd9b9775ae05cff8119a689180` (EOA) in 124 blocks (tx `0x50fce9cbfa21d653c518eae4ca284fff1401a6229faaf226e2060ae862cebedf`) → `0xdc4e258754b4257712edd6a24872312c3fd0628c` (EOA) in 27 blocks (tx `0x71bc2334d371a0dd1a4991bba8df4c0ef75606d924816c2a8373b7a207ee3ba9`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 53 blocks (tx `0x4d5e891c3e0b7b6494725bb0d0d26a5d7dcc8ed0547ac961b189f60945bcfa76`)
- Delegator `0x117eec859b7652680212c97aaa152a57344bd3c3` withdrew 66111.878515712272250149 GRT (tx `0x1f82d5266a86b80b9b1613feb691a95707dc0d07ab6a46d1f855b657f2f7db83`) → `0xf4ddc3cfdbd298dd9b9775ae05cff8119a689180` (EOA) in 103 blocks (tx `0x50fce9cbfa21d653c518eae4ca284fff1401a6229faaf226e2060ae862cebedf`) → `0xdc4e258754b4257712edd6a24872312c3fd0628c` (EOA) in 27 blocks (tx `0x71bc2334d371a0dd1a4991bba8df4c0ef75606d924816c2a8373b7a207ee3ba9`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 53 blocks (tx `0x4d5e891c3e0b7b6494725bb0d0d26a5d7dcc8ed0547ac961b189f60945bcfa76`)
- Delegator `0x117eec859b7652680212c97aaa152a57344bd3c3` withdrew 61797.552700389316056785 GRT (tx `0xab998c3b69e290fa316f044f787a416bded640f8ad732d775940c7405a46dfcf`) → `0xf4ddc3cfdbd298dd9b9775ae05cff8119a689180` (EOA) in 98 blocks (tx `0x50fce9cbfa21d653c518eae4ca284fff1401a6229faaf226e2060ae862cebedf`) → `0xdc4e258754b4257712edd6a24872312c3fd0628c` (EOA) in 27 blocks (tx `0x71bc2334d371a0dd1a4991bba8df4c0ef75606d924816c2a8373b7a207ee3ba9`) → `0x28c6c06298d514db089934071355e5743bf21d60` (Binance 14) in 53 blocks (tx `0x4d5e891c3e0b7b6494725bb0d0d26a5d7dcc8ed0547ac961b189f60945bcfa76`)


## Notes / limitations

- This is a **lower bound** because the exchange label set is intentionally small; unlabeled exchanges and EOAs are not counted.
- Second hop routing is also a lower bound: it only detects intermediates that sweep into a labeled exchange endpoint within the same window.
- Third hop routing is also a lower bound: it only detects intermediates that route into a labeled exchange endpoint within the same window.
- Transfers to exchanges are not definitive proof of market sales, but are a strong proxy for off-protocol exit intent.

Raw output: see `research/thegraph-delegation-withdrawal-routing.json`.
