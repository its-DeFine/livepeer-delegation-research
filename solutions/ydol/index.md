# Livepeer — IDOL: Improving DEX / Onchain Liquidity

Working folder for reviewing: `https://forum.livepeer.org/t/pre-proposal-idol-improving-dex-onchain-liquidity/3151`

## Quick start

From this directory:

- Fetch forum thread snapshot: `python3 scripts/fetch_forum_topic.py`
- Generate onchain slippage table (Uniswap v3 pool on Arbitrum): `python3 scripts/onchain_slippage_univ3.py --include-tick-depth`
- Pool volume/fees from swap logs: `python3 scripts/univ3_swap_analytics.py --pool <POOL> --token0-coingecko-id <id> --token1-coingecko-id <id> --days 1`
- Address-level swap concentration (wash-trade surface): `python3 scripts/univ3_swap_address_analytics.py --pool <POOL> --token0-coingecko-id <id> --token1-coingecko-id <id> --days 30`
- “Reversion after swaps” analysis: `python3 scripts/univ3_reversion_analysis.py --pool <POOL> --token0-coingecko-id <id> --token1-coingecko-id <id> --days 1 --include-time`
- Chunked vs single trade best-case comparison: `python3 scripts/chunked_trade_analysis.py --pool <POOL> --token0-coingecko-id <id> --token1-coingecko-id <id> --total-usd 25000 --chunk-usd 1000`
- Run IL + breakeven volume models: `python3 scripts/il_models.py`
- Download + summarize relevant Arrakis audit PDFs: `python3 scripts/audit_summaries.py`
- Run cross-pool case studies (slippage + volume/fees): `python3 scripts/run_case_studies.py`

Outputs land in `outputs/` and cached downloads land in `data/` (both ignored by git).

## Notes

- The proposal text references “Uniswap v4”, but the existing LPT/WETH pool used in practice is Uniswap v3 on Arbitrum.
- Re-run scripts before sharing numbers; this analysis depends on live onchain state and current prices.

## Hardhat sandbox

Toy simulations live in `sim-hardhat/` (ignored by git via `node_modules/` etc). Example:

- `cd sim-hardhat && npm run simulate:wash`
- Forked slippage sanity check (adds 50/50 liquidity on an Arbitrum fork and re-quotes):
  - `cd sim-hardhat && SIM_OUT=../outputs/fork.json SIM_TOTAL_USD=782000 SIM_RANGE_MULT=60 npx hardhat run --network hardhat scripts/forkLiquidityImpactSim.js`


