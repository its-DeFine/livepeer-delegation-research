# Livepeer — Lisar Treasury Proposal (Fiat Delegation) — Evidence-Based Status

This memo ties together:
- The **executed treasury proposal** (on-chain) for Lisar’s “Fiat Delegation for Livepeer Network”
- The **observable delegation outcomes** so far (on-chain + Lisar dashboard)

Goal: answer “was the treasury spend appropriate so far?” with evidence, not vibes.

---

## Reproduce

### 1) Generate the delegation cohort report (Lisar dashboard → on-chain)
```bash
python3 tools/lisar_program_delegation_report.py --out-dir artifacts/livepeer-lisar-spe-delegation
```

Primary outputs:
- `artifacts/livepeer-lisar-spe-delegation/report.md`
- `artifacts/livepeer-lisar-spe-delegation/report.json`

### 2) Decode the on-chain proposal (Governor ProposalCreated → description + actions)
```bash
python3 tools/lisar_treasury_proposal_report.py \
  --proposal-id 37756926437624644602157853528130337382237946922701155023801139566954226305300 \
  --out-dir artifacts/livepeer-lisar-treasury-proposal
```

Primary outputs:
- `artifacts/livepeer-lisar-treasury-proposal/report.md`
- `artifacts/livepeer-lisar-treasury-proposal/report.json`
- `artifacts/livepeer-lisar-treasury-proposal/proposal_description.md`

---

## Proposal Facts (On-Chain)

Source: `artifacts/livepeer-lisar-treasury-proposal/report.json`

- Proposal id: `37756926437624644602157853528130337382237946922701155023801139566954226305300`
- Title (from description): “Fiat Delegation for Livepeer Network”
- Proposal created: `2025-09-05` (Arbitrum block `375998163`)
- Proposal executed: `Executed` (per Explorer API)

### Requested amount + transfer action

The proposal action is a single ERC20 transfer on Arbitrum:
- Token: LPT `0x289ba1701C2F088cf0faf8B3705246331cB8A839`
- Transfer: `4450 LPT` → `0x7b9f63f244066ff5cf9a24b6043a1c75bff8de45`

Note: `0x7b9f63…` is a contract wallet (Gnosis Safe-style multisig), not an EOA.

Treasury execution transfer (ERC20 `Transfer` log):
- From (Treasury): `0xf82C1FF415F1fCf582554fDba790E27019c8E8C4`
- To (recipient): `0x7b9f63f244066ff5cf9a24b6043a1c75bff8de45`
- Tx: `0xa6467a0d8c176c88bac3689ca6232d0e8b26d759d690eb94d385f0453c7f65b6`
- Time: `2025-09-16T09:14:22Z`

---

## Promised Deliverables (From Proposal Text)

Source: `artifacts/livepeer-lisar-treasury-proposal/proposal_description.md`

Duration: **4 months**

Key deliverables / KPIs listed in the proposal:
- “Fully functional app” enabling users to deposit local currency and delegate
- Multi-currency support (e.g. NGN, KES, ZAR, USD)
- Public real-time transparency dashboard (delegators, total fiat converted, delegations per orchestrator, total LPT delegated, rewards)
- Referral system
- Delegator workshops
- Native mobile apps (iOS/Android)
- **Delegator onboarding KPI: 500–1,000 delegators onboarded and actively delegating through LISAR**

---

## Public Progress Updates (Forum)

These don’t substitute for on-chain verification, but they help anchor *what Lisar reports they’ve shipped* and when:

- 2025-09-10: “LISAR Proposal: FAQ” (embedded wallet via Privy, education curriculum, workshops): `https://forum.livepeer.org/t/lisar-proposal-faq/3069`
- 2025-10-27: “LISAR Month 1 Report” (links to a Notion report): `https://forum.livepeer.org/t/lisar-month-1-report/3132`
- 2025-12-10: “Lisar SPE Release Notes” (Nov status update: closed beta, dashboard live, public launch): `https://forum.livepeer.org/t/lisar-spe-release-notes/3159`
- 2026-01-12: “Lisar SPE Release Notes” (Dec status update: multi-asset yield tiers, GTM campaign, workshop upcoming): `https://forum.livepeer.org/t/lisar-spe-release-notes/3159/3`

---

## Observed Outcomes So Far (On-Chain + Lisar Dashboard)

Source: `artifacts/livepeer-lisar-spe-delegation/report.json` (generated 2026-01-17)

### Delegator count + stake (what’s verifiable on-chain)
- Delegators (ever bonded): `14`
- Delegators (active now): `13`
- Current total bonded (cohort sum): `33.260234 LPT`
- Total bonded via Bond events (additional): `35.244726 LPT`
- First observed bond for this cohort: `2025-11-14`

### Funnel signals (from Lisar dashboard tx list, decoded on-chain)
- Deposit transfers: `3` unique senders → `17` recipients, total `45.1807 LPT` (decoded from ERC20 transfer calldata)
- “Deposit-only” addresses (funded but never bonded): `3`

### Data quality / mismatch
Lisar dashboard summary reports:
- `totalDelegators = 13`
- `totalLptDelegated = 30.444726 LPT`

But on-chain current bonded for the same dashboard cohort is `33.260234 LPT`:
- Delta: `+2.815508 LPT` vs dashboard

This likely has an explanation (exclusion rules / definition mismatch), but it’s currently ambiguous from public data.

---

## ROI View (Strictly Against the Proposal KPI)

If we evaluate only against the explicit KPI “500–1,000 delegators onboarded and actively delegating”:
- On-chain + dashboard both point to **~13 active delegators**, as of 2026-01-17
- That is **~1.3%–2.6%** of the proposal’s target range

Rough “cost per active delegator” (treating the grant as fully spent for the period):
- `4450 LPT / 13 ≈ 342 LPT per active delegator`

This does **not** mean “the work is worthless” (product work can compound later), but it does mean the **measurable adoption KPI has not been hit yet**.

---

## Questions That Matter for a Fair Assessment

These are the key items I’d want Lisar to answer publicly to make evaluation rigorous:

1) **What is the current true delegator count, and how is it counted?**
   - “Users onboarded” vs “unique on-chain delegator addresses” vs “KYC’d unique humans”

2) **Explain the dashboard vs on-chain mismatch** (`30.444726` vs `33.260234` LPT).

3) **What percent of users are fiat-onboarded vs LPT-credited?**
   - The dashboard’s `totalNgNConverted` appears `0` in the public summary API snapshot (might be a bug or a different accounting field).

4) **Sybil resistance / uniqueness**
   - If fiat rails require KYC, that’s a meaningful uniqueness anchor; if not, what prevents “many-wallet” farming?

5) **GTM plan + timeline for hitting the KPI**
   - Acquisition channels, expected conversion funnel, and when we should expect 100/500/1000 active delegators on-chain.
