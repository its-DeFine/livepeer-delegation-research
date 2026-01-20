# Livepeer Arbitrum — Post-withdraw outflow classification (bridge vs DEX vs transfers)

- Generated: `2026-01-18T15:53:24.368139+00:00`
- Source: `top_by_proxy_rewards_withdrawn` (top 50) from `artifacts/livepeer-bm-scan-arbitrum-v2/earnings_report.json`
- LPT token: `0x289ba1701C2F088cf0faf8B3705246331cB8A839`
- BondingManager: `0x35Bcf3c30594191d53231E4FF333E8A770453e40`

## Totals (selected wallets)

- Wallets analyzed: **50**
- Total post-withdraw outgoing LPT (all destinations): **17666111.461738 LPT**
- To BondingManager (re-stake-like): **0.000000 LPT**
- To 0x0 (bridge/burn-like): **7890569.262153 LPT**
- To EOAs (unknown; could be CEX/self): **6945839.856669 LPT**
- To contracts (non-BM): **2829702.342917 LPT**

## Category totals (tx-level)

- bridge_or_burn: 7890569.262153 LPT
- direct_transfer: 6582511.577837 LPT
- contract_interaction_other: 3124095.699613 LPT
- dex_swap_likely: 31161.227316 LPT
- dex_swap_possible: 20719.045988 LPT
- bridge_possible: 17054.648831 LPT

## Top EOA destinations (global)

- `0xc5519fd1129d6d22744e0ac491401fff45d26528` (top_earner): 2356463.793202 LPT
- `0xb38e8c17e38363af6ebdcb3dae12e0243582891d`: 1585162.535574 LPT
- `0x1ec36af004a5ecabddc7b991a02bdad2bede344c` (top_earner): 720000.000000 LPT
- `0x328abdaca7e5bbfa44b22f828816a351469d4398`: 350161.000000 LPT
- `0xe4a3a2ba2e6645ad5da7d04773316c5857638d8e` (selected_wallet): 313936.394279 LPT
- `0x52384f92cea42651061522dc1b67297ff62197f6`: 294179.659616 LPT
- `0xc5889d41651474517dc71ed98548eab07d004111`: 253789.000000 LPT
- `0x16beb8782c2607fd90ca93f3119cf12c00255c6e`: 170447.433154 LPT
- `0x579a9e5cd6a97a2fa27f3c18dd19ecf7f5500073`: 128211.028623 LPT
- `0xfa196b84fc4a692819fb8054e7c225147d102215`: 98000.000000 LPT

## Top contract destinations (global)

- `0xc20de37170b45774e6cd3d2304017fc962f27252`: 1503611.824658 LPT
- `0x2be5a5ce6555162d67c16b35ece3160c6f509e0a`: 616604.000000 LPT
- `0xb7dc1baf3b4367fffbe0316a207e1aba755d3d4c`: 212000.000000 LPT
- `0x4019062831a4f343ce7681632f89236134f074e5`: 198190.249420 LPT
- `0x64e0aa4631ae8f74627e68cf02565bec30d2ea4f`: 85000.000000 LPT
- `0x4fd47e5102dfbf95541f64ed6fe13d4ed26d2546`: 42219.279265 LPT
- `0xaf489b424b533ff19074167e967a0a704be102d8`: 30000.000000 LPT
- `0x3a23f943181408eac424116af7b7790c94cb97a5`: 24418.000000 LPT
- `0x67312d9279e9d4542dd8ae415a38658a4b310966`: 20000.000000 LPT
- `0x7648ee5472fef288508df12aad12390d72250f6b`: 16282.370000 LPT
