**Tangible red flags in the IDOL / Arrakis DEX-liquidity proposal (pasteable)**

1) **Core inconsistency (v3 vs v4):** proposal says “Uniswap v4” but references the “existing 0.3% LPT/ETH pool” (on Arbitrum today that’s **Uniswap v3**). No exact pool/vault/module/hook addresses are provided → cannot audit what we’re actually deploying into.

2) **No pilot / test run despite ~$1M ask:** proposal jumps straight to **250k LPT (~$1M)** with no staged rollout, no tranche sizing, no time-box, and no “stop button” criteria beyond “we can withdraw”.

3) **No measurable KPIs / stop conditions:** it says “reduce slippage / improve depth” but doesn’t define:
   - target price impact at $5k/$10k/$25k (both directions), measured repeatedly
   - inventory drift bounds / time-to-50-50
   - benchmark for net performance (HODL / passive LP proxy)
   - clear stop conditions (underperformance, drift breach, security incident, mandate breach)

4) **Fee structure misalignment:** Arrakis takes **50% of gross trading fees** even if the treasury loses money net (IL/LVR/tail risk). Fees ≠ net performance; downside is mostly on the DAO.

5) **Numbers don’t support “fees pay for it” at current volume:** last 30d onchain volume is ~**$1.35M** with ~**$4.1k total fees** (0.30% tier). With a 50/50 fee split, DAO keeps ~**$2.0k / 30d** (best-case). That’s tiny relative to inventory + smart-contract risk on ~$1M.

6) **“Savings per trade” is overstated without UX details:** today, live quotes show ~$25k swaps at **~7%** impact; $50k sells can hit a **~45%** cliff. Users can sometimes chunk to reduce effective slippage, but that’s not one-click UX and depends on reversion.

7) **If v4/hooks are involved, approvals/roles are the real risk:** audit summaries flag hook/approval surfaces where misconfig or role compromise can drain funds. Proposal doesn’t provide a concrete role map (who can upgrade/whitelist/approve/pause).

**What we should require before any vote**

- Exact chain + **contract addresses** (pool/vault/module/hook/manager/guardian), and which components are upgradeable.
- A **pilot** (e.g., $100k–$250k tranche, 6–8 weeks) with KPIs + stop conditions written into the mandate.
- Weekly reporting: depth snapshots, inventory drift, realized fees, net performance vs benchmark, role-change events.

Data + repro: `outputs/onchain-slippage.csv`, `outputs/lpt-univ3-swap-analytics-30d.json`, `outputs/breakeven-volume.csv`, `outputs/arrakis-audit-summary.md`.
