---
title: Overview
description: Synthesis and recommendations from on-chain Livepeer delegation research on Arbitrum (acquisition, retention, cashout behavior, and solution evaluation).
---

# Synthesis & Recommendations

Updated: **2026-01-18** (Arbitrum era).

This is the “single doc” overview that ties together:
- What we measured on-chain (delegation flows, churn, withdrawals, post-withdraw transfers)
- What we learned from solution proposals (Lisar, IDOL/Arrakis, Tenderize)
- What tends to work across protocols for growing small participants
- What we recommend Livepeer should do next (and how to measure it)

<CardGroup cols={2}>
  <Card title="Deep dive: outflows + retention" href="/research/livepeer-delegator-outflows-research">
    The core evidence pack behind churn and “cashout” claims.
  </Card>
  <Card title="Design space: incentives + tokenomics" href="/research/livepeer-delegator-incentives">
    Practical mechanism options and sybil constraints.
  </Card>
</CardGroup>

---

## TL;DR (what we believe is true from evidence)

1) **Delegator acquisition is trending down** on Arbitrum (first-time bonders drop year-over-year).
2) **Retention is not “instantly everyone farms and exits”**, but early churn exists and increases over months.
3) **Rewards + “cashout” behavior are highly concentrated**; a large fraction of rewards is withdrawn and then moved out (often via bridge/burn-to-zero patterns).
4) The “mass sybil cashout wave” hypothesis is **not supported** by daily unique-unbonder counts (peaks are ~O(100), not thousands), though small trickle sybil behavior is still possible.
5) The biggest unlock for small delegator growth is still: **liquidity + UX** (liquid staking / LST), paired with **time-boxed, retention-gated** incentives.
6) Any “give smaller addresses higher APR” mechanic is **sybilable** unless tied to a uniqueness primitive (identity / proof) or made economically expensive to split.

---

## 1) What we measured (hard evidence)

### Chain / contract / method

- Chain: **Arbitrum One**
- Livepeer staking contract: `BondingManager` proxy `0x35Bcf3c30594191d53231E4FF333E8A770453e40`
- Method: RPC `eth_getLogs` scans (no explorer API keys)
- Window scanned: **2022-02-11 → 2026-01-17** (see research notes)

Primary sources in this repo:
- Delegation flows + sybil/churn research: `research/livepeer-delegator-outflows-research.md`
- Tokenomics/program ideas grounded in the data: `research/livepeer-delegator-incentives.md`

Primary artifacts (raw-ish outputs) referenced by those notes:
- `artifacts/livepeer-bm-scan-arbitrum-v2/retention_report.md`
- `artifacts/livepeer-bm-scan-arbitrum-v2/unbond_report.embedded.md`
- `artifacts/livepeer-bm-scan-arbitrum-v2/earnings_report.md`
- `artifacts/livepeer-bm-scan-arbitrum-v2/outflow_destination_classification_top50.md`

### Key network-level results (Arbitrum)

From `research/livepeer-delegator-incentives.md` and `research/livepeer-delegator-outflows-research.md`:

- **First-time bonders (“new delegators”) are trending down**:
  - 2022: **2,213**
  - 2023: **1,492**
  - 2024: **685**
  - 2025: **482**
- **Churn / retention (eligible-only)**:
  - Unbond within 30d: **10.78%**
  - Unbond within 90d: **17.24%**
  - Withdraw within 30d: **6.32%**
  - Withdraw within 90d: **12.56%**
- **Sybil-cashout wave not supported by daily unique exits**:
  - Max unique unbonders/day: **122**
- **Rewards are highly concentrated**:
  - Total rewards claimed: **17.495M LPT**
  - Top 10 earned: **33.69%**
  - Top 100 earned: **75.51%**
- **A large fraction of rewards appears to be withdrawn (“stake leaves BondingManager”)**:
  - Proxy “rewards withdrawn”: **7.198M LPT** (upper bound **11.292M LPT**)
- **Post-withdraw destinations (top cashout cohort)** skew heavily toward leaving:
  - Bridge/burn-to-zero and EOA transfers dominate the observed flows.

Interpretation: the core growth issue is more plausibly **liquidity + UX + weak retention hooks**, not a sudden “sybil apocalypse”.

---

## 2) What “delegation problem” are we solving?

There are two overlapping but distinct goals that often get conflated:

1) **Protocol security / decentralization**
   - Primarily driven by **how much stake is bonded** and **how concentrated it is**.
2) **Number of delegator addresses**
   - A proxy for decentralization and community participation, but easy to game if you reward “# of accounts”.

We should treat the canonical success metrics as:
- **Net-new bonded stake** (bond − unbond − withdraw)
- **New participants** (first-time bonders) and/or **new stake participants** (e.g., LST depositors) with clear definitions
- **Retention** (still bonded/participating after 30/90/180d)
- **Concentration / decentralization impact**

This aligns with `docs/problem.md` + `docs/rubric.md`.

---

## 3) What we learned from specific solutions

See `docs/scoreboard.md` for the roll-up.

### 3.1 Lisar — “Fiat delegation” (treasury-funded)

Where: `solutions/lisar/`

Finding (strictly vs the proposal KPI): adoption appears far below the stated target so far.
- Proposal KPI: **500–1,000 active delegators** in ~4 months.
- Observed (as of mid-Jan 2026): **~13 active delegators**, ~14 ever bonded.

Implication: anything claiming “we can onboard delegators” needs:
- A clear funnel (users → funded → bonded → retained)
- Clear on-chain definitions (what counts as “active”)
- A plan for retention and preventing “funded but never bonded” drop-off

### 3.2 IDOL / Arrakis — Improve DEX liquidity (treasury-funded)

Where: `solutions/ydol/`

Finding: the **liquidity UX problem is real**, but a large LP deployment has economics + incentive-alignment risks.

- Slippage is severe at $25k–$50k sizes in current Arbitrum LPT/WETH v3 pools (sell-side cliff exists).
- Current DEX flow is modest (fees may not offset IL/LVR), so the treasury takes most downside.
- Recommendation in the dossier: treat as a **pilot** with tranche funding + explicit KPIs/stop conditions.

Implication: DEX liquidity can reduce friction for larger actors, but **it’s not automatically a small-delegator growth engine** unless paired with onboarding + liquidity rails (e.g., an LST).

### 3.3 Tenderize — tLPT liquid staking (historical)

Where: `solutions/tenderize/`

Finding: Tenderize shows what LST adoption “looked like” historically on Livepeer:
- **2,518 unique depositors** / **2,786 deposits** / **~92.19k LPT deposited**
- Deposit sizes were mostly tiny (majority under 10 LPT total deposited)

Critical nuance:
- Tenderize **did not create 2,518 new protocol-level delegators**; the tenderizer contract is the delegator.
- It did create thousands of **stake participants** with LPT exposure.

Implication: “liquid staking” can attract many small participants, but if Livepeer’s goal is “more delegator accounts on BondingManager”, LSTs do that only indirectly (unless you add additional mechanics).

---

## 4) Cross-protocol patterns that tend to grow small stake participants

This section is “pattern-level” (not yet a full on-chain replication study across protocols). It’s included because these patterns repeatedly show up when “retail participation” increases in staking systems.

For additional precedent notes, see: `/research/cross-protocol-tokenomics-experiments`.

### Pattern A: Liquid staking + DeFi composability

Across major ecosystems (e.g., Ethereum, Solana, Cosmos), liquid staking protocols (Lido, Rocket Pool, Marinade, Stride, etc.) grew by:
- Pooling stake (removes minimums / operational complexity)
- Issuing a liquid token (used for trading, LPing, borrowing)
- Building integrations (money markets, DEX liquidity, vaults)

Why it matters for Livepeer:
- It’s **sybil-neutral** by design (rewards accrue pro-rata, not per account).
- It directly attacks the biggest retail blocker: “I want yield, but also liquidity.”

### Pattern B: Retention hooks (time + locks)

Incentives that vest over time (or increase with continuous participation) reduce “farm-and-dump” behavior.

Practical version (without a core protocol overhaul):
- Treasury bonus vests over N rounds; early unbond forfeits.

### Pattern C: Onboarding subsidies (gas, UX, defaults)

For small participants, friction costs dominate.
- Subsidize the first delegation (or gasless onboarding) but only pay out after retention.

### Pattern D: Avoid per-address progressive rewards without a uniqueness primitive

If you give better APR to “smaller balances per address”, whales can split.

If you want a “small holder boost”, you typically need one of:
- Identity attestation (with UX/privacy tradeoffs)
- Work/usage-based gating (makes sybils costly)
- Strong retention + minimums (reduces profitability of splitting)

---

## 5) Recommendations (Livepeer-specific, prioritized)

### 5.0 Define canonical KPIs and publish them

Before shipping more programs, standardize:
- “New delegator” definition (first `Bond`)
- Retention definition (unbond/withdraw triggers; censoring window)
- “Net new stake” (net bond/unbond/withdraw)
- Concentration metrics (top-N share, Gini proxy)

### 5.1 Ship an audited `stLPT / wstLPT` (liquid staking) with conservative security posture

Design goals:
- Minimal trust surface (avoid unnecessary upgradeability).
- Handle Livepeer unbonding delay cleanly (withdraw queue / lock IDs).
- Provide `wstLPT` (non-rebasing wrapper) for DeFi integrations.

Tenderize is a useful blueprint for the core staking mechanics (burn-before-unstake), but also a cautionary tale on **proxy upgrade/admin risk**.

### 5.2 Bootstrap LST liquidity (time-boxed) and measure

If you want LST adoption, liquidity is not optional.
- Incentivize `stLPT/ETH` (and/or `stLPT/LPT`) LP for a limited period.
- Use explicit stop/go criteria (volume, depth, spread, LP retention).

### 5.3 Run a “new delegator” acquisition program that is retention-gated

Use a treasury-funded program that:
- Targets first-time bonders (or first-time LST depositors) with a minimum stake.
- Vests over time; early unbond forfeits.
- Uses non-linear reward curves (e.g., `sqrt(stake)`) + caps to reduce whale dominance.

### 5.4 If you want a “small holder boost”, treat identity as optional/high-tier

There is no “0 friction, perfectly unique human” primitive.

If Livepeer wants aggressive per-person boosts, make it a higher-tier bonus:
- baseline incentives: sybil-neutral (stake-proportional + retention)
- additional boost: requires identity proof (Gitcoin Passport / World ID / equivalent), or credible “proof of work/usage” that makes sybil costly

One candidate design for “proof-of-work/usage gating” is a **delegator tiers** ladder: `/solutions/delegator-tiers`.

### 5.5 Treat DEX liquidity programs (Arrakis-style) as pilots, not forever programs

If the ecosystem pursues DEX liquidity improvement, use the guardrails from `solutions/ydol/`:
- tranche funding, explicit KPIs, stop conditions
- minimize incentive misalignment (avoid paying on gross fees if possible)

---

## 6) What we still need to research next

1) **Cross-protocol replication study**: pick 2–3 protocols and quantify “small participant growth” around LST launches (to the extent feasible).
2) **Livepeer LST design space**: audited building blocks, governance model, upgrade posture, and DeFi integration plan on Arbitrum.
3) **Sybil-resistant uniqueness options** for any “small holder boost” (UX and legal constraints included).
