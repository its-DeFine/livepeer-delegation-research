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

## Livepeer lens: is an Arrakis premium justified (based on proposal text only)?

Based on the Livepeer proposal post alone, Arrakis is not clearly “premium” on *commitments* — it mostly promises active management + reporting, but does not publish hard KPI targets, guarantees, or a fee structure that shares downside risk.

In contrast, Gamma’s quoted model (20% of earned fees, no AUM fee, permissionless entry/exit, constrained rebalance authority) is the same product category (active liquidity management) at materially lower ongoing “rent”.

For Arrakis to justify higher take rates, the DAO should require at least one of:
- **Hard KPI commitments** (e.g., max price impact at $25k/$50k swaps both directions) with timeboxes + stop conditions.
- **Evidence of outperformance vs cheaper ALMs** on comparable volatile-token/WETH pairs at similar capital.
- **Extra value beyond “just” ALM** (e.g., verifiable orderflow advantages, MEV/LVR mitigation with realistic deployment timing, or explicit risk-sharing terms).

## On-chain spot checks (Arbitrum) — how “active” are the vaults?

Below are on-chain spot checks using `cast` against Arbitrum to understand the *actual* state of some public Gamma (Uniswap v3 hypervisors) and Arrakis (Arrakis Vault V1 / “G-UNI”) deployments. This is not decision-grade benchmarking, but it does help confirm how these systems work in practice.

### Gamma: Uniswap v3 hypervisors (base+limit ranges)

Gamma hypervisors hold **two Uniswap v3 positions** (“base” + “limit”), expose the live ticks onchain, and emit a `Rebalance` event when the manager updates ranges/compounds.

- **WETH/USDC (fee=3000)**
  - Hypervisor: `0x20b520adc4d068974105104ed955a4dbadfa4ea6`
  - Pool: `0x17c14d2c404d167802b16c450d3c99f88f2c4f4d`
  - Current ranges (as of spot check):
    - Base: `baseLower=-204480`, `baseUpper=-187380`
    - Limit: `limitLower=-195900`, `limitUpper=-187380`
    - Current pool tick: `-196266` (inside base range)
  - Access control signals:
    - `owner=0xce1ebe29e7218726ec07875dc711953d35512070` (can call `rebalance(...)`)
    - `directDeposit=false` and `whitelistedAddress=0x82fceb07a4d01051519663f6c1c919af21c27845` (deposits are routed/gated)
  - Rebalance cadence (log count):
    - `Rebalance` events from block `300000000` → `latest`: **8**
    - Last `Rebalance` event at block: **396839825**

- **WETH/ARB (fee=10000)**
  - Hypervisor: `0x6b7635b7d2e85188db41c3c05b1efa87b143fce8`
  - Pool: `0x92fd143a8fa0c84e016c2765648b9733b0aa519e`
  - Current ranges (as of spot check):
    - Base: `baseLower=91000`, `baseUpper=100400`
    - Limit: `limitLower=91000`, `limitUpper=95800`
    - Current pool tick: `97159` (inside base range)
  - Access control signals:
    - `owner=0xce1ebe29e7218726ec07875dc711953d35512070`
    - `directDeposit=false` and `whitelistedAddress=0x82fceb07a4d01051519663f6c1c919af21c27845`
  - Rebalance cadence (log count):
    - `Rebalance` events from block `300000000` → `latest`: **8**
    - Last `Rebalance` event at block: **406030013**

### Arrakis: Vault V1 / “G-UNI” (single range + optional Gelato compounding)

Arrakis Vault V1 holds **one Uniswap v3 position** (`lowerTick/upperTick`). On-chain, there are two “active management” pathways:
- `executiveRebalance(...)` (manager changes the range), and
- `rebalance(...)` (Gelato executor reinvests/compounds fees *without* changing the range),
both emitting `Rebalance(int24,int24,uint128,uint128)` when used.

On Arbitrum, the sampled public community vaults below appear to be **effectively unmanaged** (no `Rebalance` events) and currently sit **out of range** (not providing liquidity).

- **WETH/ARB (fee=10000)** (same pool as Gamma example above)
  - Vault: `0xd2e386214b1cf1e5790de69d8a957cf874a835a4`
  - Pool: `0x92fd143a8fa0c84e016c2765648b9733b0aa519e`
  - Range: `lowerTick=52000`, `upperTick=92000`
  - Current pool tick: `97159` (**above upperTick**, so the position is out-of-range)
  - `Rebalance` events (lifetime): **0**

- **WETH/ARB (fee=3000)**
  - Vault: `0xb1121975f0080ed05253a825cb98af20357c17cb`
  - Pool: `0x92c63d0e701caae670c9415d91c474f686298f00`
  - Range: `lowerTick=57000`, `upperTick=84780`
  - Current pool tick: `97198` (**above upperTick**, so the position is out-of-range)
  - `Rebalance` events (lifetime): **0**
  - Recent activity is mostly exits:
    - `Minted` events from block `300000000` → `latest`: **0**
    - `Burned` events from block `300000000` → `latest`: **9** (last at block **409171076**)

### Implication for Livepeer

These spot checks illustrate a key diligence point for the Livepeer DAO: the “brand name” of an ALM provider does not guarantee that *a given vault* is being actively managed on-chain. If Livepeer pays premium fees for “active management”, it should require:
- the exact **vault + pool addresses** up front,
- explicit commitments on **in-range / depth / slippage** outcomes, and
- a monitoring plan (e.g., periodic verification of `Rebalance` activity + range placement vs current tick).
