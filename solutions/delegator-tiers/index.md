---
title: Delegator Tiers (Stake + Proof-of-Contribution)
description: A tiered incentive ladder that targets small/mid delegators while reducing sybil incentives by requiring verifiable contributions or usage to unlock rewards.
---

# Delegator Tiers (Stake + Proof-of-Contribution)

This is a proposed **program-level** incentive design: keep Livepeer protocol rewards permissionless and stake-proportional, but add **bonus rewards and/or perks** that require both:

1) **Bonded stake** (alignment, anti-spam bond), and  
2) A **verifiable proof of contribution** (or usage) that is costly to sybil at scale.

The intent is to incentivize **small and mid delegators** without creating an easy “split stake across many wallets” farming strategy.

---

## Summary (what this tries to do)

- Create a ladder of delegator “classes” by **bonded LPT range**.
- Each class unlocks eligibility for **extra rewards or privileges**, but only if the wallet (or identity) produces “real work” for the ecosystem.
- The “work” is **measurable** (usage, merged PRs, orchestrator adoption, revenue) and ideally represented by an **on-chain attestation**.

This is closer to a “builders / contributors program” than a protocol-level staking change.

---

## Proposed tier ladder (refined)

The original idea maps increasing stake → increasing scope of contribution. A refined version should:
- avoid purely subjective criteria (“useful feedback”) without objective scoring
- use definitions that can be audited and re-run
- prefer **on-chain** or **cryptographically attestable** proofs

Suggested ladder (illustrative; numbers/thresholds should be tuned):

### Tier 0 — 1–10 LPT (new users)
- **Proof**: paid Livepeer usage (e.g., ≥$X in fees or ≥Y minutes/jobs) over a window.
- **Reward/perk**: small LPT rebate/credit, “new delegator” badge, onboarding support.

### Tier 1 — 10–100 LPT (feedback + reliability)
- **Proof**: accepted issues with reproducible steps + confirmations (e.g., N “triaged/accepted” GitHub issues), or participation in structured bug bashes.
- **Reward/perk**: early access / credits; not necessarily “more APR”.

### Tier 2 — 100–1,000 LPT (code contributions)
- **Proof**: merged PR(s) to core repos, with a minimum review threshold and post-merge maintenance window.
- **Reward/perk**: larger credits/rebates; public recognition; access to higher-rate API plans.

### Tier 3 — 1,000–10,000 LPT (ecosystem tooling adopted by orchestrators)
- **Proof**: an open-source tool used by ≥10 distinct orchestrators, proven via signed attestations or verifiable integrations.
- **Reward/perk**: higher credits, distribution support, co-marketing.

### Tier 4 — 10,000–100,000 LPT (revenue + capacity)
- **Proof**: measurable net-new protocol revenue or usage attributable to the contributor (ideally on-chain) + a concrete capacity pledge (e.g., GPU uptime commitments).
- **Reward/perk**: strategic partnership perks; capacity credits; potentially bespoke incentives.

### Tier 5 — 100,000–1,000,000 LPT (rare “whale builder” tier)
- **Proof**: truly large, measurable net-new value delivered (e.g., $10M+ attributable usage), audited.
- **Reward/perk**: bespoke; treat as BD/partnership rather than “delegator incentives”.

Key refinement: the higher tiers become **partnership/BD programs**; they should not be framed as “delegator APR”.

---

## Sybil posture (why this is better than per-address APR boosts)

The core problem with “small holder APR boosts” is that they are sybilable by stake-splitting.

This tier model avoids that only if:
- the “proof” requirements are **hard to replicate** cheaply across many wallets, or
- eligibility is tied to a **uniqueness primitive** (identity attestation) rather than wallet addresses

Practical options:
- **No-identity approach (sybil-costly):** require proofs that impose real external cost (paid usage, real adoption, real revenue).
- **Identity approach (per-person):** optional identity attestation for lower tiers (Gitcoin Passport / World ID / equivalent), then cap boosted rewards to the first `cap` LPT per identity.

There is no “0 friction, perfect uniqueness” system. The design should explicitly choose the tradeoff.

---

## Implementation sketch (no core protocol change)

1) Define a **scorecard** that maps proofs → tiers (public rules).
2) Issue proofs as **on-chain attestations** (e.g., EAS on Arbitrum) signed by:
   - maintainers (merged PRs / issues)
   - orchestrators (tool adoption)
   - a grants committee (revenue attribution claims, if needed)
3) Distribute bonus rewards via **Merkle drops** (monthly/weekly) to:
   - wallets that are bonded ≥N rounds (retention)
   - and hold valid tier attestations in the measurement window

This can be run by a single entity (foundation/company) without governance changes, but it adds trust assumptions.

---

## Expected impact (KPIs)

Must be defined up front:
- new first-time bonders (count) and retained-first-time-bonders (30/90/180d)
- net-new stake bonded (net of unbond/withdraw)
- # of proofs issued per tier (and cost per proof)
- decentralization impact (stake concentration among participating orchestrators)

---

## Risks / failure modes

- **Subjectivity / capture:** if proofs are discretionary, incentives can be perceived as favoritism.
- **Gaming:** low-quality PR spam; fake “adoption” with friendly orchestrators; wash-usage if “paid usage” is cheaply recyclable.
- **Complexity:** too many rules can reduce participation versus simple LST/UX improvements.
- **Legal/PR:** if framed as “profit share for token holders” it increases regulatory risk; frame as utility/credits + contributor program.

---

## Bottom line

This can be a useful **adjacent** solution (especially to create non-financial utility for holding/delegating LPT), but it should not replace the core, proven levers for small participant growth:
- liquid staking + liquidity + integrations
- retention-gated incentives
- better onboarding UX

