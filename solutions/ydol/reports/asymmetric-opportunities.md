# Asymmetric opportunities / hidden-risk deep dive (draft)

Focus: scenarios where *someone* can benefit disproportionately versus the Livepeer treasury, even if all actors are “following the rules”.

This complements `reports/risk-assessment.md` with a more adversarial framing.

## 1) The “exit liquidity” channel (legitimate, but asymmetric)

If Livepeer deploys ~$1M-equivalent liquidity, the treasury becomes a meaningful counterparty onchain:

- Large holders can sell LPT for ETH on Arbitrum with materially lower slippage than today.
- The vault absorbs the inventory drift (more LPT / less ETH) when net flow is selling.
- If LPT underperforms ETH over the pilot window, the vault tends to be systematically worse than simply holding LPT (divergence/IL), and can be worse still if the strategy keeps re-centering ranges (“buying the dip” repeatedly).

Mitigations:

- Treat the initial deployment as a **pilot tranche**, not a permanent program.
- Pre-commit **inventory drift bounds** (e.g., “halt rebalances / start unwind if LPT share > 70% for > 7d”).
- Pre-commit an **unwind playbook** (who executes, how quickly, what happens if price gaps).

## 2) Fee-share misalignment (vendor paid on gross fees; DAO bears net PnL)

With a 50% performance fee on trading fees:

- The vendor can earn meaningfully even in regimes where the vault’s **net performance is negative** after IL/LVR.
- This can incentivize “maximize fee revenue” strategies (e.g., tight ranges) even if they increase LVR/selection losses.

Mitigations:

- Cap performance fee or reduce it (e.g., 15–25%), at least for the pilot.
- Tie the performance fee to **net performance** (e.g., paid only if vault beats a benchmark after IL).
- Require regular disclosures: range widths, % time in-range, rebalancing frequency, realized fees, and inventory drift.

## 3) Wash trading / rebate farming (becomes profitable if *any* external rewards exist)

In the proposed model, wash trading is not “free money” by default, because the trader pays fees on every cycle.

However, the break-even external rebate rate can be surprisingly low.

Rule-of-thumb:

- Net wash cost (ignoring gas/slippage) ≈ `(DAO fee share) × (pool fee tier)` per unit volume.
- Example: 0.30% pool fee tier and DAO share 50% → wash costs ≈ `0.15%` of traded volume (plus gas and any residual slippage).

So if any program anywhere pays ≥ ~0.15% of volume (or equivalent value tied to “fees generated”), wash trading can become profitable quickly.

Why this matters here:

- The LPT/WETH pool’s 30d activity is already **highly concentrated in a small number of router contracts** (see `outputs/lpt-univ3-swap-address-analytics-30d.json`), so a small number of actors can generate a large fraction of volume if incentivized.

Mitigations:

- Avoid any volume/fee-based incentives around this pool during the pilot (or design robust anti-wash constraints).
- If incentives are unavoidable, consider gating by “unique addresses”, holding periods, or proof-of-intent mechanisms (hard onchain).

## 4) Uniswap v4 hooks + approval surface (technical asymmetric risk)

The Arrakis Uniswap v4 module audit summary (see `outputs/arrakis-audit-summary.md`) highlights a key class of risk:

- Hooks can influence token deltas during liquidity actions; malicious hooks + approvals can drain funds.
- The metavault owner can approve arbitrary addresses; owners must treat approvals as “funds at risk”.

This is not an “exploit” so much as a **trust surface**: if any privileged role is compromised (or if integrations are misconfigured), the vault can lose funds.

Mitigations (pilot gating items):

- Require the proposal to specify **exact deployed addresses** (vault, module, hook, manager, guardian) and whether each is upgradeable.
- Require a clear **role map** (who can upgrade, pause, whitelist modules/hooks, set fees, set approvals).
- Prefer configurations where the Livepeer Foundation multisig is the only entity with approval powers; enforce least privilege.
- Require a practical “kill switch”: multisig can withdraw quickly even if modules are paused.

## 5) Bootstrapping from one-sided LPT to 50/50 may be slow or fail

The proposal expects the strategy to “bootstrap ETH” to reach 50/50 over months.

But the ability to convert depends on net buy pressure *and* the vault’s share of that flow.

Observed directional flow (from `outputs/lpt-univ3-swap-analytics-24h.json` and `outputs/lpt-univ3-swap-analytics-30d.json`):

- 24h: net sells (more LPT sold than bought)
- 30d: net buys, but modest in magnitude versus the $1M scale

Mitigations:

- Make “time to reach 50/50” an explicit KPI, with a stop condition if it doesn’t converge.
- Consider seeding with some ETH from day 1 (even if small) to avoid being stuck out-of-range / inactive.

## 6) A practical pilot structure (high signal, low regret)

If the DAO proceeds, structure it as:

- **Tranches**: start smaller; scale only if KPIs hit.
- **KPIs**: repeated quoter-based depth checks at $5k/$10k/$25k both directions; 7d/30d volume; time-in-range; inventory drift.
- **Stop conditions**: underperformance vs benchmark, drift breach, role/upgrade surprises, or any security event.
- **Reporting**: weekly public dashboard snapshot (or an onchain data export the community can reproduce).

## Diligence questions to resolve before voting

1. What chain and exact pool is this on (v3 vs v4 on Arbitrum)? Provide contract addresses.
2. Who owns the vault and who can upgrade modules/beacons/hooks?
3. What is the exact withdrawal path and worst-case time-to-withdraw?
4. What strategy parameters are expected (range widths, rebal frequency, target inventory drift bounds)?
5. What happens if volume stays ~current levels? What does “success” look like under low-volume reality?

