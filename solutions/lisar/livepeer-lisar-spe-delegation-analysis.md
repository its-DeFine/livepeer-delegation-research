# Livepeer — Lisar SPE Delegation Program (Arbitrum) — What Happened

This is an evidence-based review of how the Lisar SPE’s delegation onboarding performed, using:
- Lisar’s public dashboard API (`/admin/dashboard/summary`, `/admin/dashboard/transactions`)
- On-chain Livepeer **BondingManager** events on **Arbitrum One** via `eth_getLogs` / `eth_call`

Forum thread (context): `https://forum.livepeer.org/t/lisar-spe-release-notes/3159/3`

Treasury proposal (context): `https://explorer.livepeer.org/treasury/37756926437624644602157853528130337382237946922701155023801139566954226305300`  
Proposal + ROI memo: `livepeer-lisar-spe-treasury-roi.md`

---

## Reproduce

Generate the report (writes JSON + a short human summary):
```bash
python3 tools/livepeer/lisar_program_delegation_report.py --out-dir artifacts/livepeer-lisar-spe-delegation
```

Primary outputs:
- `artifacts/livepeer-lisar-spe-delegation/report.md`
- `artifacts/livepeer-lisar-spe-delegation/report.json`

---

## Executive Summary (as of 2026-01-17)

From Lisar dashboard transactions + on-chain verification (`artifacts/livepeer-lisar-spe-delegation/report.json`):
- **14** unique delegator addresses bonded (first bond observed: **2025-11-14**)
- **13 / 14** are still bonded now (**~93% retention**, small sample)
- Total bonded via Bond events (additional): **35.244726 LPT**
- Current bonded (on-chain `getDelegator().bondedAmount` summed across the cohort): **33.260234 LPT**
- Lisar dashboard reports: `totalDelegators=13`, `totalLptDelegated=30.444726 LPT`
- Dashboard mismatch:
  - `bond_additional_total_lpt - totalLptDelegated = 4.800000 LPT` (exactly)
  - `current_total_bonded_lpt - totalLptDelegated = 2.815508 LPT`

Interpretation: Lisar successfully onboarded **new, small** delegators (count impact), but the absolute stake is still **tiny** (stake impact).

---

## Timeline (new delegators by first bond date)

New-to-Livepeer bonders (first bond per address):
- `2025-11-14`: 3
- `2025-11-15`: 4
- `2025-11-16`: 3
- `2025-11-17`: 1
- `2025-11-18`: 2
- `2025-11-28`: 1 (largest single delegator in this cohort: **15.734726 LPT**)

The on-chain “bonding activity” for this cohort mostly happened over ~5 days (Nov 14–18), then one larger add on Nov 28, then small top-ups until Dec 04.

---

## Stake Distribution (current)

Among the **13 active** delegators:
- Total: **33.260234 LPT**
- Median: **1.9 LPT**
- Min: **0.388792 LPT**
- Max: **15.734726 LPT**
- Top-1 concentration: **47.3%** of bonded stake is held by a single address
- Excluding that top address, mean stake is **~1.46 LPT**

This is exactly the “small delegator” segment (single-digit LPT) we care about increasing.

---

## Delegate Concentration (current)

Active delegators by current orchestrator delegate:
- 9 / 13 delegate to: `0x5d98f8d269c94b746a5c3c2946634dcfc75e5e60`
- The remaining 4 are split 1 each across 4 other orchestrators (see `report.json`)

Interpretation: Lisar onboarding is currently **highly concentrated** to a single orchestrator choice (which may or may not be desired, depending on decentralization goals).

---

## Deposit → Bond Funnel (from dashboard txs)

The dashboard exposes 48 “transactions”:
- `bond`: 23
- `deposit`: 18
- `unbond`: 3
- `withdraw`: 4

Key observations:
- Deposits appear as on-chain **LPT ERC20 transfers** into user addresses:
  - **17** unique deposit recipients
  - **3** unique deposit senders (likely Lisar-controlled wallets) funding users
  - Total deposit transfers (decoded from ERC20 `transfer` calldata): **45.1807 LPT**
- There are **3 deposit-only addresses** (received deposit, never bonded) — suggests drop-off between “funded” and “delegated”.

This is a useful “retail onboarding funnel” signal: even with gas sponsorship / product UX, some portion of users still didn’t complete delegation.

---

## Benchmark vs Livepeer Network (Arbitrum)

Using the network-wide BondingManager scan aggregated in `artifacts/livepeer-delegator-flows/daily.json`:

Window A (Lisar bond window): `2025-11-14` → `2025-12-04`
- Livepeer network new delegators (first-time bonders): **42**
- Lisar cohort new delegators: **14** (**~33% of new delegators** in this window)
- Livepeer network bonded (additional) volume: **331,283.863 LPT**
- Lisar bonded (additional): **35.245 LPT** (**~0.0106%** of bonded volume)

Stake-size context (first-bond amounts for those 42 new delegators in Window A, from `delegators_state.pkl`):
- Network median first bond: **~24.75 LPT** (p75 **~200 LPT**, max **~48,639 LPT**)
- % of new delegators with first bond ≤ 2 LPT: **~40.5%**
- Lisar cohort: **13 / 14 (~92.9%)** had first bond ≤ 2 LPT (one was **15.734726 LPT**)

Window B (extended): `2025-11-14` → `2025-12-18`
- Livepeer network new delegators: **56**
- Lisar cohort new delegators: **14** (**25%**)

Interpretation: Lisar’s visible impact is much stronger on **new-delegator count** than on **total stake** (so far).

---

## What This Means for “Small Delegator Incentives”

1) **A low-friction product can move the needle on small-delegator count**, even if stake is small.
2) **Count-based programs are sybil-sensitive**: this cohort looks like real retail sizes, but uniqueness is not provable from on-chain data alone.
3) **If Livepeer wants more small delegators**, a “small-delegator boost” should be paired with a distribution channel like Lisar (or an LST) to reduce onboarding friction, otherwise incentives alone get captured by existing wallets.

---

## Open Questions / Follow-ups

- Why does the dashboard `totalLptDelegated` differ from on-chain current bonded totals for the same addresses?
  - The delta vs total bonded via Bond events is **exactly 4.8 LPT**, which may indicate a specific exclusion rule (beta cohort? internal/test delegations?).
- Are the “deposit sender” wallets verified as Lisar-controlled, and do they correlate to KYC’ed users (uniqueness signal)?
- Did Lisar’s new delegators persist beyond the initial learning period (90/180d retention), or does churn rise later?
