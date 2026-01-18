Subject: IDOL / Arrakis DEX liquidity proposal — review summary + reproducible results

Hi Livepeer Foundation team,

Sharing our data-backed review of the “IDOL – Improving DEX / Onchain Liquidity” pre-proposal (topic `3151`). We focused on (1) current onchain liquidity/UX, (2) whether the proposed structure creates asymmetric risk for the treasury, and (3) what a safer pilot would look like if the DAO proceeds.

Key takeaways (as-of 2025-12-20; numbers depend on onchain state/prices):

- Current Arbitrum LPT/WETH Uniswap v3 pool has severe depth issues (e.g., ~$25k swaps ≈ ~7% impact; ~$50k sells can hit a ~45% cliff).
- Current DEX volume is modest (~$74k/day; ~$223/day total fees at 0.30%), so fee income is unlikely to offset IL/LVR unless volume rises materially.
- Adding ~$1M liquidity can plausibly reduce $25k impact into the ~1–2% range (fork sanity check), but strategy/range placement and governance guardrails matter.
- Recommendation: treat as a smaller, time-boxed pilot with explicit KPIs/stop conditions, and require clarity on v3 vs v4 + exact contract/role/upgrade/approval surfaces.

Attachments / links in this folder:

- Summary for sharing: `reports/livepeer-foundation-summary.md`
- Full writeups: `reports/executive-summary.md`, `reports/risk-assessment.md`, `reports/asymmetric-opportunities.md`, `reports/arrakis-case-studies.md`
- Reproducible outputs (slippage/volume/IL/audits): `outputs/`

Happy to walk through findings and help translate them into specific diligence questions / pilot guardrails for the vote.

