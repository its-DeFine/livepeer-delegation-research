# Executive summary — IDOL / Arrakis DEX liquidity proposal (draft)

Goal: assess whether allocating ~250k LPT (~$1M) to an Arrakis-managed LPT/ETH liquidity strategy is likely to add net value to the Livepeer ecosystem, and identify asymmetric risks + mitigations.

This summary is based on reproducible artifacts in this folder (scripts + cached forum snapshot + outputs). Re-run the scripts before treating any metric as current.

## What the proposal gets right (real value)

- **The onchain UX problem is real.** The Arbitrum LPT/WETH Uniswap v3 pool exhibits large price impact for mid/large trades, and can become extremely punitive on the sell side when trades cross sparse tick ranges (liquidity cliff).
- **Better onchain liquidity likely reduces friction** for orchestrators/builders who need to acquire/sell LPT without going through CEX rails + delayed L2 withdrawals.
- **Self-custody via a Foundation multisig is directionally good** versus opaque offchain market maker arrangements (at least for custody/withdraw rights).

## The biggest “gotchas” (where this can fail even with honest actors)

- **Uniswap v4 vs v3 mismatch needs clarification.** The proposal references “Uniswap v4”, but the “existing 0.3% LPT/ETH pool” on Arbitrum is Uniswap v3.
- **Current DEX flow is modest.** 30d pool volume is ~$1.35M with ~$4k of total fees at 0.30% (see `outputs/cases/livepeer_lpt_weth_arb_v3_0p3-swap-analytics-30d.json`). If volume doesn’t rise materially, fee income is unlikely to offset inventory risk.
- **The DAO bears most of the downside.** The DAO takes IL/LVR + tail risk; the vendor is paid on gross fees (50%) regardless of net PnL. That incentive mismatch matters when volume is low and volatility is high.
- **“Savings per trade” depends on behavior.** The pool sometimes reverts quickly after $500–$2k swaps, but it’s variable: in the latest 24h snapshot we measured, only ~47% reverted within the next 10 swaps (±2 ticks), with median revert latency ~22s (p90 ~61s). A sophisticated user can split a $25k swap into $1k chunks and (best-case) reduce effective impact from ~7% to ~0.6% — but this is not “one-click UX”. See `outputs/univ3-reversion-lpt-1d.json`.

## “Hidden exploit / asymmetric profit” plausibility

- **Pure wash trading isn’t a free-profit channel** in this fee split model: a wash trader who is also the fee recipient still pays the portion of fees that goes to the DAO (plus slippage/gas). A Hardhat toy simulation shows break-even external rewards ≈ (1 − managerFeeShare) × feeTier (e.g., 0.15% of volume at 50% fee share and 0.30% tier). See `sim-hardhat/` and run `npm run simulate:wash`.
- **But** if any external incentives exist (trade mining, rebates, liquidity programs tied to volume/fees), wash trading can become profitable quickly. Guardrail: avoid volume-based rewards around this pool, or design robust anti-wash-trade constraints.

## Recommendation: treat as a pilot with explicit guardrails

If the DAO wants onchain liquidity improvement, a staged pilot is the highest-signal / lowest-regret path:

- **Tranche funding**: start with a smaller amount (e.g., $100–$250k equivalent), time-boxed (e.g., 6–8 weeks), with an explicit option to scale.
- **Pre-commit KPIs**: repeated onchain measurements of price impact at $5k/$10k/$25k both directions, and volume/fees over rolling windows (24h/7d/30d).
- **Pre-commit stop conditions**: mandate breach, material underperformance, inventory drift outside agreed bounds, or any security incident.
- **Fee structure improvements**: consider lowering performance fee, adding a cap, or tying performance fee to net performance (e.g., fee share only paid if vault outperforms a benchmark after accounting for IL).
- **Technical guardrails** (especially if v4 is used): strict allowlisting of hooks/modules, least-privilege approvals, transparent role management, and an onchain “kill switch” (withdraw) that the multisig can execute quickly.

## Where to look in this folder

- Proposal snapshot: `data/forum-posts-3151/index.md`
- Onchain slippage (LPT pool): `outputs/onchain-slippage.csv`
- Swap volume/fees + case studies: `reports/arrakis-case-studies.md`
- Reversion + chunking: `outputs/univ3-reversion-lpt-1d.json`, `outputs/chunked-trade-lpt-25k-by-1k.json`
- Full risk writeup: `reports/risk-assessment.md`
