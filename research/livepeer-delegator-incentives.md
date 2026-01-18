# Livepeer Delegator Growth — Tokenomics Ideas

Goal: bring **net-new delegators + stake** into Livepeer (not just reshuffling existing LPT), while improving **retention** and **stake decentralization**.

This is written as a menu of mechanisms (protocol-level vs. “program-level”) plus a few concrete, parameterizable program designs.

---

## What the Arbitrum on-chain data says (2022-02-11 → 2026-01-17)

All numbers below are from RPC `eth_getLogs` scans of the Arbitrum `BondingManager` proxy `0x35Bcf3c30594191d53231E4FF333E8A770453e40` (no explorer keys). Full artifacts live under `artifacts/livepeer-bm-scan-arbitrum-v2/` and summarized in `fundraising/livepeer-delegator-outflows-research.md`.

- **New delegators are trending down**: 2,213 (2022) → 1,492 (2023) → 685 (2024) → 482 (2025).
- **Early churn exists, but it’s not a “thousands/day” sybil wave**:
  - Overall (eligible-only): unbond within 30d **10.78%**, within 90d **17.24%** (`artifacts/livepeer-bm-scan-arbitrum-v2/retention_report.md`).
  - Max unique unbonders in a day: **122** (through 2026-01-17) (`artifacts/livepeer-bm-scan-arbitrum-v2/unbond_report.embedded.md`).
- **Rewards are highly concentrated**:
  - Total staking rewards claimed: **17.495M LPT**
  - Top 10 earned **33.69%**, top 100 earned **75.51%** (`artifacts/livepeer-bm-scan-arbitrum-v2/earnings_report.md`).
- **A large fraction of rewards appears to be extracted (stake leaves BondingManager)**:
  - Proxy “rewards withdrawn”: **7.198M LPT** (upper-bound: **11.292M LPT**) (`artifacts/livepeer-bm-scan-arbitrum-v2/earnings_report.md`).
  - For top “cashout” wallets, post-withdraw LPT transfers are dominated by **bridge/burn-to-zero** and **EOA transfers**, with ~0 LPT going back into BondingManager from the same wallets (`artifacts/livepeer-bm-scan-arbitrum-v2/outflow_destination_classification_top50.md`).

Implication: if Livepeer wants “many more small delegators”, the program should be designed to (1) acquire net-new users, (2) enforce retention/vesting, and (3) avoid simply subsidizing large, already-sophisticated wallets that are likely to cash out and bridge.

---

## Delegator decision model (what you’re competing against)

Delegators typically optimize for:
- **Net yield**: inflation rewards + fee share − orchestration cut − gas/ops costs
- **Liquidity**: ability to exit or use the stake elsewhere (DeFi composability)
- **Simplicity**: low-friction onboarding, clear “best defaults”, good tooling
- **Downside risk**: smart contract risk, orchestrator performance risk, “unknown unknowns”

Tokenomics incentives should primarily target one of these:
1) increase net yield, 2) reduce friction costs, 3) improve liquidity, 4) reduce downside.

---

## Incentive levers (ordered from “lowest protocol change” to “highest”)

### 1) Delegation mining (treasury-funded, time-boxed)

Allocate a fixed incentive budget (e.g., X LPT) distributed to eligible delegators over a defined window.

Design knobs:
- **Eligibility**: new-to-delegation addresses, new capital, minimum stake, lock/retention requirement
- **Distribution curve**: linear, capped, non-linear (e.g., sqrt) to reduce whale dominance
- **Retention**: vesting over N rounds; clawback/forfeit on early unbond
- **Decentralization**: multiplier for delegating to under-staked orchestrators

Implementation path (no core protocol change): periodic Merkle drops (monthly/weekly) based on snapshot rules.

### 2) Gas subsidies / “first delegation” rebates

For many retail delegators, Ethereum gas makes small stakes irrational.

Program: reimburse (or prepay) gas for `bond`/`rebond`/`unbond` actions, but only after an address remains bonded for N rounds.

This is “tokenomics-adjacent” but often the highest ROI for onboarding.

### 3) Liquidity: liquid staking + LP incentives

The biggest unlock for delegator growth is often **liquid staking** (an LST like `stLPT`) so delegators can:
- remain staked (earning inflation/fees)
- keep liquidity (trade/borrow/LP)

Tokenomics angle: seed and/or incentivize `stLPT/LPT` and `stLPT/ETH` liquidity with a time-boxed program.

### 4) Time-weighted staking (lockup boosts)

Optional lockups (or continuous-time multipliers) increase retention and can outperform “one-time bonuses”.

Two common patterns:
- **Simple**: multiplier ramps up with continuous delegation; resets on unbond
- **Vote-escrow (ve)**: lock LPT for longer → higher multiplier + governance weight (bigger protocol lift)

### 5) Real-yield sharing (fees → delegators)

Delegators like “real yield” (ETH/stable) more than pure inflation.

If protocol/treasury can redirect a portion of revenue (or external grant revenue) into a transparent fee pool distributed to delegators, it tends to attract more new capital than higher inflation alone.

### 6) Risk reduction: insurance / guarantees

If delegators perceive orchestrator or protocol risk, yields need to be meaningfully higher to compensate.

Program: create an insurance pool (funded from a small skim of incentives or fees) that covers specific adverse events (e.g., misconfiguration downtime, slashing if applicable), with clear terms.

---

## Concrete program templates (parameterizable)

### Program A: “First Delegation Bonus” (new delegators only)

Objective: acquire new delegators; require retention.

Rules:
- Eligible if address has **never been bonded** before the program start
- Must bond ≥ `min_stake` and stay bonded for ≥ `retention_rounds`
- Bonus vests linearly over `vesting_rounds` and is forfeited on early exit

Anti-sybil / anti-whale:
- Non-linear scaling: `bonus = k * sqrt(stake)` (plus a hard per-address cap)
- Minimum stake that makes sybil splitting costly

### Program B: “Decentralization Multiplier” (stake where it’s needed)

Objective: grow total delegated stake *and* improve stake distribution.

Rules:
- Base rewards as in Program A or ongoing delegation mining
- Add multiplier if delegating to orchestrators below a target stake band:
  - e.g., `multiplier = clamp(1, 1 + (targetStake - orchStake)/targetStake, max=2)`

Guardrails:
- Prevent gaming via orchestrator self-delegation rules or explicit exclusions
- Cap per-orchestrator inflow if needed to avoid sudden centralization

### Program C: “LST Bootstrapping” (liquid staking adoption)

Objective: attract DeFi-native delegators.

Rules:
- Incentivize LP positions for `stLPT/ETH` (and/or `stLPT/LPT`) for a fixed duration
- Pair with education + integrations (vaults, money markets)

Guardrails:
- Time-box incentives (avoid permanent mercenary liquidity)
- Concentrate rewards early, then taper (bootstrap not subsidize forever)

### Program D: “Small Delegator Boost” (progressive rewards) + sybil resistance

Objective: aggressively raise small-delegator APR without getting sybil-split by whales.

Key constraint (important): **any scheme that gives “more rewards to smaller balances per address” is sybilable** unless you can key it to a **unique identity** (or make sybil expensive via “work” requirements).

Two practical patterns:

1) **Boosted tranche per unique identity**
- Each unique delegator identity gets a boosted APR (or bonus) on their *first* `cap` LPT staked; above `cap` earns normal APR.
- Example “effective stake” for bonus weighting: `eff = min(s, cap) + (s - cap) * w`, where `w << 1` (e.g., `0.1`) and `s` is stake per identity.
- The bonus pool is distributed by `eff` (or you directly mint bonus shares on the tranche).

2) **Fixed “per-unique-delegator” stipend**
- Every eligible unique delegator gets a fixed bonus after bonding and meeting retention (strongly favors small).

Sybil resistance options (choose at least one):
- **Proof-of-personhood / identity attestation**: Gitcoin Passport / World ID / BrightID-style proof, anchored via an on-chain attestation (e.g., EAS). Bonus claims require the attestation and are limited “one per identity”.
- **Work-based gating**: require a verifiable “work receipt” per period (e.g., paid Livepeer usage minutes / fees generated / ecosystem contribution attestations). This doesn’t guarantee uniqueness, but makes sybil materially costly.
- **Retention + vesting**: rewards vest over N rounds; early unbond forfeits (reduces “farm and dump”).

Where `stLPT` fits:
- Easiest: keep protocol rewards unchanged; distribute the **bonus** as extra `LPT`/`stLPT` to small delegators (treasury-funded).
- Harder/optional: implement the progressive boost *inside* an `stLPT` vault (progressive share minting / progressive fee redistribution). This only works if large holders opt in, so it’s best paired with strong utility (liquidity/DeFi integrations) that makes `stLPT` desirable even with reduced marginal yield at high balances.

---

## Metrics + guardrails (how you know it worked)

Primary KPIs:
- **Net new bonded stake** (total + per-orchestrator distribution)
- **# of new delegators** (first-time bonders)
- **Retention** (still bonded after 30/60/90 days)
- **Cost per $ of net new stake** (incentive spend / net new stake)
- **Stake decentralization** (Gini / top-N share)

Operational guardrails:
- program is **time-boxed**
- rewards are **predictable** (avoid surprise parameter changes)
- incentives do not materially reduce orchestrator incentives to perform

---

## Embody-specific “distribution wedge” ideas (if you want delegators via product)

If you can acquire users via `embody.zone`, you can convert a subset into Livepeer delegators by tying delegation to utility:
- **Stake-to-unlock**: discount tiers, higher-quality video, or premium avatars unlocked by delegated LPT (with a lock/retention requirement)
- **Creator pools**: “delegate to support this avatar/creator” and share a portion of creator revenue back to delegators (off-chain accounting is simplest)
- **Gasless onboarding**: Embody fronts gas and recoups via retention rules (delegators stick around long enough to justify CAC)

These don’t require Livepeer protocol changes; they’re an app-layer growth engine for the network.
