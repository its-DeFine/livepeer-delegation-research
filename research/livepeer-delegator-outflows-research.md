# Livepeer Arbitrum Delegator Inflows/Outflows — Onchain Research (RPC `eth_getLogs`)

This note is meant to ground any “small-delegator incentive” tokenomics proposals in **observed onchain behavior**, and specifically to test the hypothesis:

> “Delegator outflows were driven by sybil farmers cashing out.”

---

## Scope

- **Chain**: Arbitrum One
- **Contract**: Livepeer `BondingManager` proxy `0x35Bcf3c30594191d53231E4FF333E8A770453e40`
- **Data source**: JSON-RPC `eth_getLogs` (no Arbiscan/Etherscan key)
- **Window scanned**:
  - Start (deployment): block `5,856,381` (`2022-02-11 13:25:10 UTC`)
  - End (scan time): ~block `422,274,552` (`2026-01-17`)
- **Events scanned**:
  - `Bond`
  - `Unbond`
  - `WithdrawStake`
  - `EarningsClaimed`

Outputs live under:
- `artifacts/livepeer-delegator-flows/daily.json` (UTC day aggregates)
- `artifacts/livepeer-delegator-flows/delegators_state.pkl` (per-delegator summary state)
- Scanner: `tools/livepeer/arb_bondingmanager_scan.py`

---

## High-level results (from the full window)

### New delegators (first-time bonders)

- **Total new delegators** (addresses with a recorded first `Bond`): **4,886**
- New delegators by year (first bond timestamp):
  - 2022: 2,213
  - 2023: 1,492
  - 2024: 685
  - 2025: 482
  - 2026: 14 (partial year to `2026-01-17`)

Note: there are additional addresses that appear in later events but do not have a recorded `first_bond_ts` (likely due to `TransferBond` paths, which are not included in the scan set).

### Delegator size distribution (max bonded amount, among first-time bonders)

Among the 4,886 addresses with `first_bond_ts`:
- **Median** max bonded stake: ~**72 LPT**
- **83.5%** had max bonded stake **≤ 1,000 LPT**
- Threshold counts:
  - ≤ 10 LPT: 1,097
  - ≤ 100 LPT: 2,760
  - ≤ 1,000 LPT: 4,079

### How fast do new delegators exit? (first bond → first withdraw)

Among the 4,886 first-time bonders:
- Withdrew within 7 days: 126 (**2.6%**)
- Withdrew within 30 days: 419 (**8.6%**)
- Withdrew within 60 days: 585 (**12.0%**)
- Withdrew within 90 days: 734 (**15.0%**)
- Withdrew within 180 days: 1,030 (**21.1%**)
- Withdrew within 365 days: 1,472 (**30.1%**)
- Never withdrew (as of `2026-01-17`): 2,564 (**52.5%**)

This is not perfect “retention” (delegators can re-enter), but it’s a useful “first exit” signal.

---

## Merkle migration claimers: how fast do they exit?

Livepeer’s Arbitrum migration uses `L2Migrator` (Controller key `L2Migrator`) with a Merkle snapshot contract (Controller key `MerkleSnapshot`).

- `L2Migrator`: `0x148D5b6B4df9530c7C76A810bd1Cdf69EC4c2085`
- `MerkleSnapshot`: `0x10736ffaCe687658F88a46D042631d182C7757f7`
- Event analyzed: `StakeClaimed(address,address,uint256,uint256)` (topic0 `0xc08c27…`)
- Scanner: `tools/livepeer/arb_l2migrator_stake_claims.py`
- Outputs:
  - `artifacts/livepeer-delegator-flows/stake_claimed.ndjson`
  - `artifacts/livepeer-delegator-flows/stake_claimed_summary.json`

### Claim volume

- **Unique claimers**: 1,575 addresses
- **Total stake claimed**: ~9.76M LPT
- Claim timing (by count + stake):
  - Concentrated in **Feb–Mar 2022** (initial migration), but claim activity continues through 2026 (long tail).

### Time from claim → exit actions (claimer behavior)

Quantiles (days from claim):
- Claim → first unbond: q25 ~16d, median ~261d, q75 ~689d
- Claim → first withdraw: q25 ~27d, median ~275d, q75 ~724d

Fast-exit rates (count-weighted, among claimers):
- Unbond within 7d: ~14.9%
- Withdraw within 30d: ~15.8%

Fast-exit rates (stake-weighted, by claimed stake of those wallets):
- Withdraw within 30d: ~11.4% of claimed stake

Interpretation: there is a meaningful “claimed → withdraw within ~1 month” cohort, but it is **not uniformly distributed** across delegates and is **amount-concentrated** (a few large wallets can dominate the stake-weighted picture).

---

## Outflow spikes: by amount vs by number of withdrawers

### Largest outflow-by-amount days (WithdrawStake)

Top days by total withdrawn amount (LPT), with number of withdrawers:
- `2023-02-09`: ~1.76M LPT withdrawn by **6** withdrawers
- `2025-09-17`: ~1.07M LPT withdrawn by **17** withdrawers
- `2024-12-23`: ~1.04M LPT withdrawn by **17** withdrawers
- `2024-12-31`: ~1.02M LPT withdrawn by **20** withdrawers
- `2024-03-15`: ~0.82M LPT withdrawn by **31** withdrawers

Interpretation: the biggest outflow-by-amount days are generally dominated by **small numbers of withdrawers** (whale-like behavior).

### Largest outflow-by-count days (WithdrawStake)

Top days by **number of withdrawers**:
- `2025-06-06`: **45** withdrawers (total ~404.7k LPT)
- `2024-12-13`: **33** withdrawers (total ~149.3k LPT)
- `2025-06-05`: **31** withdrawers (total ~582.1k LPT)
- `2024-03-15`: **31** withdrawers (total ~824.6k LPT)
- `2024-03-14`: **31** withdrawers (total ~27.0k LPT)

Interpretation: there are days with **many withdrawers but relatively small total amounts**, which is where “many small accounts exiting” would show up — but these peaks are on the order of **~30–45 withdrawers/day**, not thousands.

### “First withdraw” clustering is small

If we only count **first-ever** withdrawers (proxy for “cashout once and leave”), the maximum is still small:
- largest day by first-withdrawers: `2024-03-14` with **16** first-withdrawers

---

## Outflows by “team” (delegate/orchestrator address)

The `Unbond` event is indexed by `delegate` (orchestrator), so we can attribute stake outflows by “team” (delegate address).

Scanner: `tools/livepeer/arb_unbond_by_delegate_scan.py`  
Output: `artifacts/livepeer-delegator-flows/unbond_by_delegate.json`

### Top delegates by total unbonded stake (LPT)

Top 5 delegates by total unbonded stake over the full window:
- `0x525419ff5707190389bfb5c87c375d710f5fcb0e`: ~7.54M LPT unbonded (699 unique unbonders)
- `0x4416a274f86e1db860b513548b672154d43b81b2`: ~4.64M LPT unbonded (8 unique unbonders)
- `0x9c10672cee058fd658103d90872fe431bb6c0afa`: ~3.86M LPT unbonded (57 unique unbonders)
- `0x4f4758f7167b18e1f5b3c1a7575e3eb584894dbc`: ~2.04M LPT unbonded (13 unique unbonders)
- `0xda43d85b8d419a9c51bbf0089c9bd5169c23f2f9`: ~2.00M LPT unbonded (81 unique unbonders)

Interpretation:
- Some “top outflow” delegates are **whale-driven** (very few unbonders, very large unbond totals).
- Others are **broad-based** (many unique unbonders, moderate average size).

### How much of delegate outflow is migration-claimer driven?

For some delegates, a large fraction of unbonded stake plausibly traces back to migration claims (claimer stake claimed to that delegate):
- `0x9c1067…`: claimedStake/unbond ≈ **63%**
- `0xda43d8…`: claimedStake/unbond ≈ **52%**
- `0x4ff088…`: claimedStake/unbond ≈ **49%**

For others, migration-claimer stake is a small fraction of total unbond outflow:
- `0x525419…`: claimedStake/unbond ≈ **10%**

---

## Whale-driven outflows: are the whales “orchestrators”?

There are multiple “whale-driven” delegate outflow cases where a very small number of wallets unbond a very large amount. Two separate questions matter:

1) Is the **delegate** an orchestrator? (i.e., a transcoder address)  
2) Are the **whale wallets** themselves orchestrators, or just delegators?

### Delegate attribution (service URIs)

On Arbitrum, orchestrator “service URIs” are stored in `ServiceRegistry` (Controller key `ServiceRegistry`).

- `ServiceRegistry`: `0xC92d3A360b8f9e083bA64DE15d95Cf8180897431`
- Query used: `getServiceURI(address)(string)`

Examples of whale-driven delegates and their service URIs:
- `0x4416a274…` (registered transcoder): `"https://livepeer-orchestrator.prod.dcg-labs.co:8935"`
- `0x104a7ca0…` (registered transcoder): `"https://node.eliteencoder.net:8935"`
- `0x21d1130d…` (registered transcoder): `"https://93.115.27.44:8935"`
- `0xf5a88945…` (registered transcoder): `"https://54.144.38.201:8935"`

### Whale wallet status

For the top whale wallets driving these delegate outflows:
- `BondingManager.isRegisteredTranscoder(address)` returns **false** (i.e., they are not transcoders/orchestrators).
- They are delegators (EOAs) that can be bonded to a delegate/orchestrator.

Interpretation: whale-driven outflows are often “whales leaving (or rotating) an orchestrator”, not “orchestrators exiting”.

---

## Funding-source clustering (wallet linkage signals)

Purpose: look for clusters that suggest a small number of entities controlling many wallets (sybil-like), or internal wallet shuffles.

Tooling:
- Script: `tools/livepeer/arb_funding_source_clustering.py`
- Output: `artifacts/livepeer-delegator-flows/funding_cluster.json`

Heuristics used (read as signals, not proof):
- Migration claim sources via `L2Migrator.StakeClaimed` (delegate + claimed stake)
- Inbound `LPT Transfer` events in a backward block window before a wallet’s first observed `Bond` event

### Example: direct whale-to-whale funding link

In the whale-driven cohort around the `0x4416a274…` orchestrator, there is a direct funding edge:

- `0x3d6182c5…` (migration claimer; claimed ~1.81M LPT on `2022-02-27` to `0x9c10672…`)
  → transferred **1,000,000 LPT** to
- `0xc5519fd1…` shortly before `0xc551…`’s first observed `Bond` to `0x4416a274…`

Interpretation: this looks like wallet linkage / internal capital movement, not a mass of unrelated small wallets.

### Bridge-mint pattern

Several large wallets’ “funding source” appears as `Transfer(from=0x0000… , to=wallet)` near bonding time, which is consistent with canonical bridge minting on L2 (not necessarily sybil behavior).

### Whale exits often look like bridge-out burns (Transfer to zero)

Many of the largest withdrawers by amount show large `LPT Transfer(from=wallet, to=0x0000…)` events, and the underlying txs are highly consistent:
- `tx.to == 0x5288c571…` with selector `0x7b3a3c8b` (gateway-like)
- the `Transfer(... → 0x0000…)` amount matches the value being exited

Interpretation: a large share of whale exits are not “sold on Arbitrum” in-place; they appear to be **bridge-out / burn flows** that remove LPT from Arbitrum supply (likely bridging to L1 or elsewhere).

Examples (top withdrawers):
- `0x3d6182c5…`: ~**1.73M LPT** burned across 16 txs (2023-02-09 → 2024-12-23)
- `0xc5519fd1…`: ~**1.16M LPT** burned across 18 txs (2025-02-18 → 2026-01-14)
- `0x962b0295…`: ~**1.05M LPT** burned in 1 tx (2025-09-17)

Artifacts:
- Burn summary: `artifacts/livepeer-delegator-flows/top_withdrawers_burn_to_zero_summary.json`
- Burn date ranges: `artifacts/livepeer-delegator-flows/top_withdrawers_burn_to_zero_daterange.json`
- Post-withdraw outflow window sample (includes tx.to + selector): `artifacts/livepeer-delegator-flows/top_withdrawer_post_withdraw_outflows_window2m.json`

### “Minter” transfers are often protocol-funded withdrawals (not external funding)

When clustering “fast-exit small” wallets, a surprisingly common inbound `LPT Transfer` source is the Livepeer `Minter` contract (`0xc20de371…`).

By inspecting the underlying transactions for these `Minter → wallet` transfers:
- **41 / 42** are `tx.to == BondingManager proxy (0x35Bcf3…)` with selector `0x25d5971f` (i.e., `withdrawStake(...)`).
- The receipt typically contains a single `LPT Transfer` log **from `Minter` to the withdrawing wallet** plus the `BondingManager.WithdrawStake` event.

Interpretation: in this cohort, “Minter-funded wallets” is primarily a **protocol payout pattern at withdrawal time**, not “someone funding many new wallets”.

Artifacts:
- Minter audit output: `artifacts/livepeer-delegator-flows/minter_transfer_fast_exit_small_audit.json`

### Fast-exit small cohort: infrastructure vs sybil signals

Cohort definition:
- First withdraw ≤ 30 days from first bond
- `max_bonded_amount ≤ 1,000 LPT`
- Cohort file: `artifacts/livepeer-delegator-flows/cohort_fast_exit_small_30d_1000lpt.txt` (275 wallets)

Funding clustering output:
- `artifacts/livepeer-delegator-flows/funding_cluster_fast_exit_small.json`

Key patterns:
- **Bridge mints**: 51 wallets show `Transfer(from=0x0000…, to=wallet)` where `tx.to == 0x6d2457a4…` and selector `0x2e567b36` (bridge/gateway-like). In these txs, `tx.from` is often `0x7253f1c8…` or `0x0000…` (system/L1→L2 message execution), so `tx.from` clustering here is **not** a reliable “EOA funder”.
- **Protocol withdrawals**: 42 wallets show `Transfer(from=Minter, to=wallet)`, and as above this is almost entirely explained by `withdrawStake(...)` calls to `BondingManager`.
- **Small, sybil-like batch**: one EOA (`0xee3da44e…`) sends **2 LPT** (`ERC20.transfer`, selector `0xa9059cbb`) to **11 wallets** in a tight block range (~371.75M–371.78M). Those wallets then:
  - first bond on **2025-08-24**
  - unbond on **2025-09-12**
  - withdraw on **2025-09-21** (earliest-possible timing)
  - bond across many different delegates (not a single orchestrator)

Cash-out behavior (within protocol + post-withdraw consolidation):
- Total withdrawn from BondingManager across the 11 wallets: **~51.95 LPT**
- Post-withdraw, they consolidate:
  - **~16.44 LPT** moved *between* the 11 wallets (internal consolidation into 1–2 “collector” wallets)
  - **~29.32 LPT** moved from the 11-wallet set to a single external EOA (`0x1d863e2a…`)
- The external EOA then **re-bonds** LPT via `BondingManager` (selector `0x6bd9add4`) rather than transferring to DEX routers/pools in this window.

Artifacts:
- Batch post-withdraw internal vs external flow summary: `artifacts/livepeer-delegator-flows/sybil_batch_ee3da44e_post_withdraw_internal_external.json`
- External collector wallet outgoing LPT transfers: `artifacts/livepeer-delegator-flows/ee3da44e_aggregator_1d863_lpt_outgoing.json`

Interpretation: there is at least some “farm addresses for delegator-count/eligibility” behavior in the long tail; in this instance it looks like a coordinated batch that withdraws and then consolidates into a collector that re-stakes.

---

## Evidence for/against “sybil farmers cashing out”

### What the data supports

- The **largest outflow-by-amount** days look **whale-driven** (single-digit to tens of withdrawers).
- Periods with higher “many-withdrawer” days exist, but maxima are **~30–45 withdrawers/day**.
- Migration-claimer exits exist (non-trivial “claim → withdraw within ~30d”), but stake-weighted fast exits appear **concentrated in a small number of large wallets**, not “mass thousands of small accounts” in aggregates.
- In a large “fast exit small” cohort (withdrew within 30 days and max stake ≤ 1,000 LPT), exits are spread across **many** delegates (no obvious single-orchestrator funnel).
- Within that cohort, there are **some** clear automation-looking clusters (e.g., a single EOA funding many wallets that bond/unbond/withdraw in lockstep), but they appear **small by stake**.
- There are “dust”/automation-looking cohorts (e.g., many tiny new bonders on a single day), but they do **not** obviously map to later large withdrawals in the aggregates.

### What we cannot yet conclusively rule out

- A coordinated actor could still operate many wallets and exit over many days with small amounts.
- Without funding-source clustering (e.g., “all these wallets were funded by the same 1–3 addresses”), we can’t definitively label/quantify sybil activity.

### Next research step (if we want a stronger answer)

Do **funding-source clustering** on suspect cohorts:
- Select cohorts such as:
  - “fast exit small” addresses
  - top “many-withdrawer” weeks
  - specific “spike days” by withdrawer count
- For each address, fetch inbound `LPT Transfer` logs around their first bond window to identify common funders.
- Optionally include `TransferBond` scanning to capture “entry” via transfers (so we don’t miss “new delegators” that were actually farm wallets receiving stake).

---

## Why this matters for tokenomics design

If outflows are mostly whale-driven (by amount), then “small-delegator count” problems are likely more about:
- product/UX friction
- unclear expected yield
- lack of liquidity (no LST path)
- lack of retention incentives

If we want to **aggressively boost small delegators**, any “per-address progressive rewards” design is sybilable unless we add:
- identity attestation (optional or required for the highest boosts), and/or
- proof-of-usage/proof-of-spend gates that make sybils economically expensive.

---

## Addendum (2026-01-17): “Dormant vs active” unbonders (tx-gap proxy)

The earlier “dormant” proxy (based on `EarningsClaimed`) turned out to be misleading because `Bond`/`Unbond` transactions often emit `EarningsClaimed` in the same tx.

So we re-scanned the full window and classified “dormancy” by **time since the delegator’s previous distinct BondingManager transaction** (any of: `Bond`, `Unbond`, `Rebond`, `WithdrawStake`, `EarningsClaimed`, `TransferBond`).

Artifacts:
- Full scan output: `artifacts/livepeer-bm-scan-arbitrum-v2/daily.json`
- Per-`Unbond` NDJSON: `artifacts/livepeer-bm-scan-arbitrum-v2/unbond_events.ndjson`
- Summary report (fast, uses embedded timestamps): `artifacts/livepeer-bm-scan-arbitrum-v2/unbond_report.embedded.md`
- Scanner: `tools/livepeer/arb_bondingmanager_scan.py`
- Reporter: `tools/livepeer/arb_unbond_events_report.py`

Key results (full window, through `2026-01-17`):
- `Unbond` events: **24,059**
- Unique unbonders: **3,290**
- Total unbonded: **~48.43M LPT**
- “Exit `<30d`” (first bond → unbond): **1,548 events**, **~8.56M LPT**

Prev-tx gap buckets (event-level, amount-weighted):
- `<=30d`: **21,011 events**, **~34.33M LPT**
- `>=90d`: **1,939 events**, **~8.76M LPT**
- `mid` (30–90d): **1,109 events**, **~5.34M LPT**

First unbond per unbonder (unique-unbonder classification):
- `<=30d`: **1,527 unbonders** (46.4%)
- `>=90d`: **1,350 unbonders** (41.0%)
- `mid`: **413 unbonders** (12.6%)

Day-by-day “who unbonds” highlights:
- Largest unbond-by-amount days are still **whale-driven** (few wallets dominate the day’s amount), e.g.:
  - `2024-03-07`: ~**812.5k LPT** unbonded by a single wallet with a `>=90d` gap (dormant-exit shaped).
  - `2024-12-10`: **1.0M LPT** unbonded by a single wallet.
- Largest day by **unique unbonders** is only **122** wallets (`2025-05-30`) — not thousands — which is inconsistent with “mass sybil cashout wave” in the raw daily counts (but does not rule out smaller trickle-style sybil behavior).

---

## Addendum (2026-01-18): Cumulative staking rewards + “cashout” bounds (Arbitrum)

To answer “who extracted value systematically” and “did rewards stay staked or get cashed out?”, we ranked all addresses by cumulative `EarningsClaimed.rewards` and compared against on-chain `WithdrawStake.amount`.

Artifacts:
- Report: `artifacts/livepeer-bm-scan-arbitrum-v2/earnings_report.md`
- Data: `artifacts/livepeer-bm-scan-arbitrum-v2/earnings_report.json`
- Tool: `tools/livepeer/arb_earnings_report.py`

Key results (through `2026-01-17`, spot conversion uses **$3.29/LPT** passed to the report tool):
- Total staking rewards claimed: **17,495,206.038769 LPT** (≈ **$57.56M** at $3.29).
- Reward concentration (by rewards): top 10 = **33.6863%**, top 100 = **75.5056%**.
- Rewards claimed by wallets with any withdraw: **15,150,251.289056 LPT** (**86.6%** of all rewards).
- “Rewards cashed out” (observable only as stake leaving BondingManager, not as fiat conversion):
  - Upper bound (rewards-first attribution): **11,291,848.749311 LPT** (≈ **$37.15M**).
  - Proxy (withdraw beyond `bond_additional + stake_claimed`, capped by rewards): **7,197,879.226981 LPT** (≈ **$23.68M**).
- GPU equivalence example (if you assume **$5,000 capex per GPU**):
  - Total rewards: ≈ **11,511.85 GPUs**
  - Upper bound withdrawn rewards: ≈ **7,430.04 GPUs**
  - Proxy withdrawn rewards: ≈ **4,736.20 GPUs**

Important caveat: This does **not** prove “selling” (DEX/CEX). It measures stake exiting the staking contract. Full sell-tracing would require following LPT `Transfer` logs after withdraw and classifying destinations (routers, CEX deposit addrs, etc.).

---

## Addendum (2026-01-18): What top “cashout” wallets did after withdrawing (post-withdraw LPT transfers)

We additionally traced **LPT ERC20 `Transfer`** events *after* each wallet’s first `WithdrawStake` to see whether liquid LPT tended to:
- re-enter BondingManager (likely re-staking), vs
- leave to other addresses (could be selling/bridging/self-custody moves)

Artifacts:
- Report: `artifacts/livepeer-bm-scan-arbitrum-v2/post_withdraw_lpt_transfers_top50.md`
- Data: `artifacts/livepeer-bm-scan-arbitrum-v2/post_withdraw_lpt_transfers_top50.json`
- Tool: `tools/livepeer/arb_post_withdraw_lpt_transfers.py`

Top 50 wallets by **proxy rewards withdrawn** (spot uses **$3.29/LPT**):
- Total `WithdrawStake` (liquid LPT leaving BondingManager): **14,914,258.407986 LPT** (≈ **$49.07M**).
- Total post-withdraw outgoing LPT to **non-BondingManager** destinations: **18,108,291.978155 LPT** (≈ **$59.58M**).
- Of that, outgoing “burn” transfers to `0x000…000` (often consistent with **bridge-out style burns**): **7,933,388.951882 LPT** (≈ **$26.10M**).
- Many wallets show near-1:1 behavior where `withdraw ≈ outgoing_non_bm`, suggesting a strong tendency to move withdrawn stake out of the wallet rather than keep it liquid locally or re-stake.
- GPU equivalence example (if you assume **$5,000 capex per GPU**):
  - Total withdraw: ≈ **9,813.58 GPUs**
  - Total outgoing non-BM: ≈ **11,915.26 GPUs**
  - Proxy withdrawn rewards (top-50 cohort only): ≈ **3,506.66 GPUs**

Note: Outgoing transfers can exceed withdraw totals because we count *all* LPT transfers from the wallet after its first withdraw (it may have had LPT from other sources too). This is still strong evidence of “value leaving the staking contract”, but not definitive proof of “sold for USD” without destination labeling.

---

## Addendum (2026-01-18): Delegator retention curves (first bond → first unbond/withdraw)

To move beyond anecdotes, we generated event-based retention curves using the full BondingManager scan:
- “New delegator” = first `Bond` event seen for an address
- Churn proxies:
  - first `Unbond` (any partial unbond counts)
  - first `WithdrawStake` (stake leaves BondingManager)

Artifacts:
- Report: `artifacts/livepeer-bm-scan-arbitrum-v2/retention_report.md`
- Data: `artifacts/livepeer-bm-scan-arbitrum-v2/retention_report.json`
- Tool: `tools/livepeer/arb_delegation_retention_report.py`

Key results (eligible-only to avoid right-censoring, through `2026-01-17`):
- New delegators (first bond): **4,887**
- Ever unbonded: **2,684**
- Ever withdrew: **2,322**
- Overall churn within N days:
  - `<=30d`: **10.78%** unbonded, **6.32%** withdrew
  - `<=90d`: **17.24%** unbonded, **12.56%** withdrew
  - `<=180d`: **23.29%** unbonded, **18.16%** withdrew
  - `<=365d`: **32.87%** unbonded, **26.39%** withdrew

Interpretation: there is real early churn, but it’s not “everyone instantly farms and leaves”; much of churn happens over months.

---

## Addendum (2026-01-18): Outflow destination labeling (bridge vs DEX vs transfers)

We added a classifier that labels post-withdraw LPT outflows for “big cashout” wallets using:
- `Transfer(to=0x0)` as a strong bridge/burn signal on Arbitrum
- receipt-based “DEX sale likely” when the same tx shows incoming **USDC/USDT/DAI/WETH** to the wallet
- 4byte selector hints as a weak signal (collision-prone; used only as a fallback)

Artifacts:
- Top-50 report: `artifacts/livepeer-bm-scan-arbitrum-v2/outflow_destination_classification_top50.md`
- Data: `artifacts/livepeer-bm-scan-arbitrum-v2/outflow_destination_classification_top50.json`
- Tool: `tools/livepeer/arb_outflow_destination_classify.py`

Key result (top 50 by proxy rewards withdrawn; limited to top 20 tx per wallet by LPT out for speed):
- Total outgoing LPT analyzed: **17,666,111.461738 LPT**
- Bridge/burn-like (to `0x0`): **7,890,569.262153 LPT**
- Direct transfers (tx.to is LPT token; mostly EOAs): **6,582,511.577837 LPT**
- DEX swap signals (receipt-based): **~31k LPT** “likely” (+ **~21k LPT** “possible” via selector hints)

Important caveat: the DEX heuristic will miss sales where the wallet receives **native ETH** (not WETH) or routes proceeds to a *different* address. So “DEX sold” here is a **lower bound**. Even with that caveat, bridge/burn + EOA consolidation dominate the observed flows in the biggest-wallet cohort.
