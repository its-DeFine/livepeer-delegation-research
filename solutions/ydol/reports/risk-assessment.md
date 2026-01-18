# Risk assessment — IDOL / Arrakis DEX liquidity (working draft)

This is a living document. Re-run scripts in `scripts/` to refresh numbers and regenerate `outputs/`.

As-of snapshot: 2025-12-20 (re-run scripts to update).

## Key questions this review aims to answer

1. Does the proposal reduce real UX friction for Livepeer participants?
2. Is the treasury taking asymmetric risk relative to the vendor’s compensation?
3. Could the structure be used as “exit liquidity” or create hidden profit opportunities for certain actors?
4. Should this be staged as a pilot, and what objective stop/go criteria should apply?

## Major inconsistencies / clarification blockers

- The proposal describes deployment to “Uniswap v4”, but the referenced “existing 0.3% LPT/ETH pool” is an onchain Uniswap v3 pool on Arbitrum.
- The proposal’s slippage table should be reproducible from onchain state with a method + timestamp (and ideally quoted via Uniswap quoter contracts).

## Onchain liquidity snapshot (Uniswap v3, Arbitrum)

Reference pool used by the proposal’s “existing pool” language:

- LPT/WETH Uniswap v3 (0.30%): `0x4fD47e5102DFBF95541F64ED6FE13d4eD26D2546`

Quoted via Uniswap v3 Quoter against live onchain state (see `scripts/onchain_slippage_univ3.py`):

| Notional (USD) | Buy impact | Sell impact |
|---:|---:|---:|
| $1,000 | ~0.60% | ~0.59% |
| $5,000 | ~1.78% | ~1.73% |
| $10,000 | ~3.25% | ~3.12% |
| $25,000 | ~7.67% | ~7.14% |
| $50,000 | ~15.04% | ~45.26% |

Observation: sell-side impact exhibits a liquidity cliff (large jump by ~$50k notional), which is consistent with sparse initialized ticks outside the current active range.

Tick-boundary depth estimate (within current liquidity range, ignoring cross-range liquidity changes):

- ~2,424 LPT of sells to hit the nearest initialized lower tick boundary
- ~3.38 WETH of buys to hit the nearest initialized upper tick boundary

## Onchain flow reality (volume + fees)

Computed from onchain `Swap` logs (see `scripts/univ3_swap_analytics.py`):

- 24h: ~$74k volume, ~$223 fees (0.30% tier) → ~$112/day to DAO at 50% fee split (if the vault captured ~100% of fees)
- 30d: ~$1.35M volume, ~$4,054 fees → ~$2,027 to DAO at 50% fee split

Directional flow (same window, approximating “buy” as `WETH in` and “sell” as `LPT in`):

- 24h: buy ~$35.9k vs sell ~$38.6k (net sells ~$2.7k)
- 30d: buy ~$717.6k vs sell ~$633.5k (net buys ~$84.1k)

This matters because the vendor fee (50% of trading fees) can look “cheap” in dollars if volume stays low, while the treasury still bears the full tail risk of inventory + LVR.

## Address concentration (baseline “wash-trade surface”)

To sanity-check whether pool activity is broadly distributed (organic flow) or concentrated in a small set of contracts/actors (easier to game), we also aggregated swap notionals by `sender`/`recipient` from the onchain `Swap` logs (see `scripts/univ3_swap_address_analytics.py`).

Latest snapshot:

- 24h: ~161 swap logs, ~20 unique senders; top sender ~26% of volume
- 30d: ~4,572 swap logs, ~51 unique senders; top sender ~45% of volume
- Outputs: `outputs/lpt-univ3-swap-address-analytics-24h.json`, `outputs/lpt-univ3-swap-address-analytics-30d.json`

Interpretation: flow appears to be routed through a small number of smart contracts (routers/aggregators), which is normal — but it also means that if any external incentives are ever added (fee rebates, volume mining, etc.), a small number of actors could generate a large share of volume quickly. This amplifies the importance of “no volume-based rewards around this pool” as a guardrail.

## Fork-based “does $~1M liquidity actually move the needle?” sanity check

The proposal’s core claim is “more liquidity will materially reduce price impact”. To sanity-check magnitude (and to reproduce the table-like comparisons), we ran a Hardhat **fork** of Arbitrum, minted additional 50/50 liquidity into the *existing* LPT/WETH Uniswap v3 0.30% pool, and re-quoted via the Uniswap v3 Quoter.

This is an intentionally simplified “upper bound” experiment (single LP position, fixed range, no active management), but it’s useful for magnitude:

- Baseline (fork, matches live): ~$25k swap ≈ ~7–8% impact both sides; $50k sells can hit a liquidity cliff (~45%+).
- After minting ~$782k 50/50 liquidity:
  - With a moderate range (±60×tickSpacing): $25k ≈ ~1.2% impact; $50k sell ≈ ~2.1%.
  - With a wide range (±200×tickSpacing): $25k ≈ ~2.4% impact; $50k sell ≈ ~4.3%.
- After minting ~$1M 50/50 liquidity (wide range ±200×tickSpacing): $25k ≈ ~2.0%; $50k sell ≈ ~3.6%.
- Outputs: `outputs/fork-liquidity-impact-782k-range20.json`, `outputs/fork-liquidity-impact-782k-range60.json`, `outputs/fork-liquidity-impact-782k-range200.json`, `outputs/fork-liquidity-impact-1m-range200.json`

Notes:

- These “impact” numbers include the 0.30% LP fee (same methodology as `scripts/onchain_slippage_univ3.py`). Some UI tables report “price impact” excluding fees, which can make the results look ~0.30% smaller at small sizes.
- This demonstrates that the proposal’s slippage-improvement direction is *plausible* if the deployed liquidity is both large relative to current active liquidity and positioned around the active tick. It does not prove the **net economics** (IL/LVR) are favorable.

## Empirical arbitrage / “chunking” (why some users see low effective slippage)

There’s a credible counterpoint raised in the thread: in low-liquidity pools, CEX/DEX arb can re-balance the pool quickly after each swap, so a user can reduce effective slippage by splitting a large swap into smaller swaps with pauses in between.

We tested this on the Livepeer pool directly:

- Reversion analysis (`scripts/univ3_reversion_analysis.py`, 24h window, swaps $500–$2000 notional):
  - 32 candidates; 46.9% reverted within the next 10 swaps (±2 ticks)
  - median revert: 4 swaps
  - median revert latency: ~22s (p90 ~61s)
  - Output: `outputs/univ3-reversion-lpt-1d.json`
- Chunked trade best-case (assume full revert between chunks; `scripts/chunked_trade_analysis.py`):
  - $25k single swap impact: ~7.67% buy / ~7.14% sell
  - $25k split into 25x $1k chunks: ~0.60% buy / ~0.59% sell
  - Output: `outputs/chunked-trade-lpt-25k-by-1k.json`

Interpretation:
- The proposal still addresses a *real UX issue* (one-shot execution is extremely punitive), but “savings per trade” depends heavily on whether the user is willing/able to chunk and wait for arb reversion.

## Economic risk summary (why this can go wrong even if nothing is exploited)

- The DAO becomes the market maker in `LPT/ETH`, absorbing:
  - impermanent loss / divergence loss
  - adverse selection / loss-versus-rebalancing (LVR)
  - tail risk (fast repricing, liquidity cliffs, oracle issues)
- The vendor is paid as a share of trading fees, which can be positive even when treasury net PnL is negative (fees ≠ net performance).
- “Bootstrapping to 50/50” is conditional on net flow. If the dominant onchain flow is net selling of LPT, sell-side slippage can remain bad even after deployment (the vault trends LPT-heavy).

## Breakeven economics (fees required to offset IL)

This is a simplified model intended to highlight asymmetry, not forecast returns. It uses historical daily LPT/USD and ETH/USD data (CoinGecko) to estimate LPT/ETH ratio volatility and passive 50/50 AMM IL.

For $1,000,000 deployed with Uniswap 0.30% fees and a 50/50 split of trading fees (DAO effective capture ~0.15% of volume):

- 180d median IL (~4–5%) requires on the order of ~$170k/day sustained DEX volume to breakeven on fees alone.
- 180d bad IL (~15–17%) requires on the order of ~$620k/day sustained DEX volume.

See `outputs/breakeven-volume.csv` and `outputs/il-model-summary.json` (generated by `scripts/il_models.py`).

## Asymmetric opportunity channels to scrutinize

- Fee extraction without downside sharing: vendor earns on gross fees; DAO eats IL/LVR and smart-contract tail risk.
- “Exit liquidity” dynamics: deeper DEX liquidity can disproportionately benefit large sellers (DAO becomes the counterparty providing ETH liquidity).
- Trust surface: custody design (multisig threshold, key compromise) and any upgrade/role controls in the vault/module stack.
- v4 hooks risk (if v4 is actually used): hook selection and allowance/approval flows become part of the threat model.

### “Could they be setting up an asymmetric profit opportunity?”

Two distinct things can be true at the same time:

1) There’s no obvious “free money” exploit for the vendor *if nothing else changes*.
2) The fee structure still creates incentive misalignment (vendor maximizes gross fees; DAO bears IL/LVR).

One common concern is wash trading to farm fees. In isolation, wash trading is not profitable here because the wash trader pays fees on every swap:

- If the manager receives 50% of fees, a wash trader who is also the manager still loses ~50% of the paid fees (plus slippage/gas).
- We validated this in a toy Hardhat sandbox: `sim-hardhat/` (run `npm run simulate:wash`).
  - With 0.30% fee tier and 50% fee split, wash trading lost ~0.15% of volume (break-even reward rate ≈ 0.15% of volume).

However, this becomes exploitable if *any* external incentive pays per-volume or per-fee on the same pool (trade mining, rebates, etc.). Guardrail: avoid or tightly design any volume-based rewards around this pool, or require robust anti-wash-trade constraints.

## What a “safe” pilot would look like

- Tranche funding (e.g. `25k → 25k → 25k LPT`) with fixed review checkpoints.
- Pre-committed KPIs:
  - price impact at standard sizes ($5k/$10k/$25k) both directions (measured repeatedly, not one snapshot)
  - net performance vs benchmark (HODL and/or passive LP proxy)
  - inventory drift limits and explicit unwind policy
- Stop conditions: mandate breach, failure to meet depth targets, material underperformance, or any security incident.

## Repro steps

- Onchain slippage snapshot: `python3 scripts/onchain_slippage_univ3.py --include-tick-depth`
- IL + breakeven volume models: `python3 scripts/il_models.py`
- Audit PDF extraction: `python3 scripts/audit_summaries.py`
