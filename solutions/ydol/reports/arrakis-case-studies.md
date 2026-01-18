# Arrakis case studies (pool-level)

These are pool-level metrics (slippage + recent onchain volume/fees) for pools associated with prior Arrakis/PALM-style proposals. They do **not** attribute outcomes to a specific Arrakis vault without vault addresses / share-of-liquidity data.

## Summary table (24h window)

| Case | Pool | Fee tier | 24h volume (USD) | 24h fees (USD) | $25k buy impact | $25k sell impact |
|---|---|---:|---:|---:|---:|---:|
| Livepeer LPT/WETH (Arbitrum, Uniswap v3 0.30%) | `0x4fD47e5102DFBF95541F64ED6FE13d4eD26D2546` | 0.30% | $74,455 | $223 | 7.67% | 7.14% |
| Radiant RDNT/WETH (Arbitrum, Uniswap v3 0.30%) | `0x446BF9748B4eA044dd759d9B9311C70491dF8F29` | 0.30% | $348 | $1 | 537.93% | 93.59% |
| Across ACX/WETH (Ethereum, Uniswap v3 1.00%) | `0x508acdC358be2ed126B1441F0Cff853dEc49d40F` | 1.00% | $709 | $7 | 75.85% | 43.35% |
| Compound COMP/WETH (Ethereum, Uniswap v3 0.30%) | `0xea4Ba4CE14fdd287f380b55419B1C5b6c3f22ab6` | 0.30% | $992 | $3 | 69.48% | 86.72% |
| Compound COMP/WETH (Ethereum, Uniswap v3 1.00%) | `0x5598931BfBb43EEC686fa4b5b92B5152ebADC2f6` | 1.00% | $1,273 | $13 | 128.74% | 99.34% |

## Fee split sensitivity (illustrative)

Assumes fees are paid pro-rata to the protocol-owned LP, and shows how much of pool fees the DAO retains under different splits.

| Case | 24h pool fees (USD) | DAO 50% | DAO 80% |
|---|---:|---:|---:|
| Livepeer LPT/WETH (Arbitrum, Uniswap v3 0.30%) | $223 | $112 | $179 |
| Radiant RDNT/WETH (Arbitrum, Uniswap v3 0.30%) | $1 | $1 | $1 |
| Across ACX/WETH (Ethereum, Uniswap v3 1.00%) | $7 | $4 | $6 |
| Compound COMP/WETH (Ethereum, Uniswap v3 0.30%) | $3 | $1 | $2 |
| Compound COMP/WETH (Ethereum, Uniswap v3 1.00%) | $13 | $6 | $10 |
