# Liquidity management providers (Arrakis vs Gamma vs Steer vs ICHI) — public evidence

This note collects *publicly available* evidence (case studies, partner docs, stats pages, incident reports) relevant to selecting a concentrated-liquidity manager for Livepeer’s DEX-liquidity workstream (e.g., LPT/WETH on Arbitrum).

It is not a full diligence report: most vendors publish “execution quality” metrics (depth/price impact/volume share) but do **not** publish complete net economics (fees – IL/LVR – swaps/gas – vendor fees).

## What “success” usually means (objective metrics)

Liquidity management programs typically claim to optimize for some mix of:
- **Liquidity depth** near spot (e.g., $ depth at 0.5%/1%/2% levels).
- **Lower price impact** for target swap sizes (e.g., $5k / $10k / $25k / $50k).
- **Higher DEX share** vs CEX venues (volume share / routing share).
- **Better CEX parity** (fewer/shallow arb gaps, fewer “toxic” arb opportunities).
- **Staying in-range** during volatile periods (execution stability under stress).
- **Capital efficiency** (achieve similar depth with less treasury deployed vs full-range/passive).
- **Net economics** for the principal (fees earned + incentives – IL/LVR – rebalancing swaps – manager fees).

## Arrakis (Arrakis Pro / Arrakis Finance)

### Scale (DefiLlama)
- DefiLlama reports ~**$84.6M** TVL for Arrakis Finance across multiple chains.
  - Source: `https://api.llama.fi/protocol/arrakis-finance`

### Public case studies with explicit metrics (Arrakis-authored)

1) **Bitpanda / Vision (VSN) post-TGE case study**
- Source: `https://arrakis.finance/blog/bitpanda-case-study`
- Claims/metrics (TL;DR section):
  - ~**55% greater depth** at 1–2% levels vs the primary CEX venue (Gate.io).
  - Full-range would require up to **~3× more capital** to match the same 2% depth.
  - **Realized volatility** on Uniswap reported up to **40% lower** than the primary CEX venue during the analysis window.
  - Uniswap captured **~20% of total VSN spot volume** post-TGE.

2) **Morpho (MORPHO): Arrakis Pro vs self-managed liquidity**
- Source: `https://arrakis.finance/blog/morpho-case-study`
- Claims/metrics (TL;DR section + tables):
  - Morpho shifted from **self-managed Uniswap v3 (0.3%)** to **Arrakis-managed Uniswap v4 (0.3%)**.
  - **Sell-side price impact on $5k trades** reported to drop ~60% (**0.45% → 0.16%**).
  - **Average swap size** reported to increase (**$2.0k → $3.4k**).

3) **“Doubling down on POL” liquidity top-up case study (token not named in excerpt)**
- Source: `https://arrakis.finance/blog/the-benefits-of-doubling-down-on-pol-an-arrakis-pro-case-study`
- Claims/metrics (text section):
  - After a ~$2M liquidity injection, the pool’s **average daily volume share** rose from **0.97% → 2.06%** vs broader market venues.
  - Median daily volume share increased **0.35% → 1.15%**.

### Named partners / users mentioned publicly (examples, not endorsements)
- Arrakis homepage references:
  - **Usual** (TGE volatility navigation).
  - **Across foundation** (bootstrapping ETH liquidity).
  - **EtherFi** (ongoing liquidity management).
  - Source: `https://arrakis.finance`
- Arrakis LST vault launch references **Lido Finance** as first user.
  - Source: `https://arrakis.finance/blog/introducing-arrakis-liquid-staking-token-(lst)-vaults`

### Public risk disclosures + incidents to note
- Arrakis publishes a risk page describing:
  - **48-hour timelock** for upgrades.
  - Off-chain liquidity management with on-chain guardrails (manager risk is explicitly acknowledged).
  - Source: `https://arrakis.finance/risks`
- A third-party security writeup describes an **Arrakis DNS hijacking / front-end compromise** (Jan 15, 2025) affecting the website interface (not smart contract logic).
  - Source: `https://threesigma.xyz/blog/exploit/defi-front-end-exploits` (Arrakis section)

### Diligence note
Arrakis publishes the most “token issuer style” case studies (depth vs CEX, volume share, impact) — but they are vendor-authored and may be selection-biased. If used for Livepeer, request methodology + raw inputs for any numbers used to justify costs.

## Gamma (Gamma Strategies / Gamma)

### Scale (DefiLlama)
- DefiLlama reports ~**$6.6M** TVL for Gamma (note: DefiLlama’s classification may not capture all partner-deployed “Gamma-powered” vault liquidity).
  - Source: `https://api.llama.fi/protocol/gamma`

### Reported terms (from support; verify in a term sheet)
- As reported by Gamma support (via ticket), the proposed economics and operating constraints were:
  - **No launch fees**
  - **80/20 fee model**: 20% of earned fees taken by Gamma; 80% reinvested into the LP position
  - **No deposit/withdrawal fees**
  - **Suggested range** for LPT/WETH: ~**-40% to +66%** (log-symmetric), with rebalance triggers about halfway through the range on either side
  - **Permissionless deposits/withdrawals** (Gamma cannot stop or gate entry/exit)
  - Gamma controls **rebalances only**, with guardrails (cannot rebalance too far from prior range / cannot exceed certain range-width limits)
  - Can list on Gamma frontend; supports **Merkl** incentives
- Before any DAO decision, ask for a written term sheet confirming:
  - Whether the 20% is the *only* fee and whether it is **inclusive of keeper gas costs**
  - The exact DEX/pool engine (Uniswap v3 vs other) + the **exact pool address** they would manage
  - Upgradeability / admin controls / multisig / timelock model for the vault + manager

### Public “proof of operation” signals
- Gamma publishes protocol-level stats:
  - **Volumes Generated (to date): $94.40B**
  - **Protocol Revenues (to date): $7.99M**
  - Source: `https://app.gamma.xyz/stats`
- Gamma maintains a public directory of many vaults (TVL + “Total APR (24H)”).
  - Source: `https://www.gamma.xyz/vaults`

### Third-party/partner evidence: performance fee share (Camelot)
- Camelot docs describe their fee share from Gamma’s vaults:
  - “~⅓ of a 25% performance fees, i.e., 8% of the total … leaving Gamma with 13.25% of gross fees generated by their vaults.”
  - Source: `https://docs.camelot.exchange/tokenomics/protocol-earnings` (V3 vaults section)

### Public incident history to consider (risk)
- Cointelegraph reported a **$3.4M exploit** affecting Gamma Strategies (Jan 04, 2024), with deposits shut down while withdrawals remained open.
  - Source: `https://cointelegraph.com/news/gamma-attempts-to-negotiate-with-hacker-after-3-4m-exploit`

### Diligence note
Gamma has broad integrations and a lot of public “operational surface area”, but fewer token-issuer-style case studies with explicit “depth vs CEX / volume share” metrics. For a Livepeer decision, ask Gamma for named comparable deployments and before/after metrics.

## Steer Protocol

### Scale (DefiLlama)
- DefiLlama reports ~**$40.4M** TVL for Steer Protocol across many chains (including Arbitrum).
  - Source: `https://api.llama.fi/protocol/steer-protocol`

### Diligence note
Steer has meaningful reported TVL and a broad product surface (Smart Pools, etc.), but public “token issuer / POL deployment” case studies with explicit depth/impact targets are less discoverable than Arrakis’ Pro content. Ask for named references with the specific metrics Livepeer cares about (depth, impact, volume share).

## ICHI

### Scale (DefiLlama)
- DefiLlama reports ~**$22.2M** TVL for ICHI across multiple chains (including Arbitrum).
  - Source: `https://api.llama.fi/protocol/ichi`

### Case studies (note: generic / not client-named)
- ICHI docs publish “Case Studies” with claimed improvements (operational cost, liquidity depth, yields, volatility reduction) but do **not** name the specific protocols.
  - Source: `https://docs.ichi.org/home/case-studies`

### Diligence note
The published “case studies” are directionally informative but not independently verifiable. For a Livepeer decision, ask for named deployments and an explicit term sheet (fee model, custody/admin controls, withdrawal guarantees, reporting).

## What to request from any provider (decision-grade diligence)

To turn marketing into decision-grade diligence, request a short memo answering:
1) **Comparable examples** (≥2–3) with token volatility similar to LPT and similar capital size.
2) **Before/after metrics**: depth at 0.5/1/2%, price impact at $10k/$25k/$50k, DEX share vs CEX.
3) **Net economics**: fees + incentives – IL/LVR – swap/rebalance costs – provider fees, over a defined window.
4) **Operational model**: how often rebalances happen; do they swap inventory; what guardrails exist.
5) **Security posture**: audits, upgradeability + timelocks, admin keys/multisigs, incident history, disclosures.
6) **Reporting**: cadence + dashboards + onchain addresses, and how the community can independently verify.
