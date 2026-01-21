---
title: Start Here
description: A single, evidence-based place to understand Livepeer delegation trends on Arbitrum and evaluate proposed fixes.
---

# Livepeer Delegation Research

This is a working research repo: we prioritize **verifiable on-chain evidence** and a consistent rubric for judging solutions.

## Recommended reading order (stakeholder flow)

<CardGroup cols={2}>
  <Card title="1) Executive statement" href="/docs/statement">
    The current thesis: security-relevant growth is bracket growth (1k–10k, 10k+), driven by token utility.
  </Card>
  <Card title="2) Analytics" href="/docs/analytics">
    The key dashboards and evidence links (board, time series, outflows, bridge-outs).
  </Card>
  <Card title="3) Solution dossiers (3)" href="/solutions/ydol">
    Lisar (onboarding), IDOL/Arrakis (liquidity), Tenderize (liquid staking).
  </Card>
  <Card title="4) General directions" href="/docs/directions">
    Proposed next-step directions that are sybil-aware and measurable.
  </Card>
  <Card title="Meeting dashboard" href="/meeting">
    One-page, slide-friendly view of the latest metrics + key takeaways.
  </Card>
  <Card title="Scoreboard + rubric" href="/docs/scoreboard">
    Cross-solution comparison + scoring framework.
  </Card>
</CardGroup>

## Evidence Packs

<CardGroup cols={2}>
  <Card title="Outflows + retention research" href="/research/livepeer-delegator-outflows-research">
    Who exits, when they exit, and what happens after withdraw (including “cashout” bounds).
  </Card>
  <Card title="Cashout routing (bridge-outs → exchanges)" href="/research/l1-bridge-recipient-second-hop">
    Follows Arbitrum bridge-outs to L1 recipients and one hop further to labeled exchange endpoints (best-effort).
  </Card>
  <Card title="Incentives + tokenomics notes" href="/research/livepeer-delegator-incentives">
    Design space for small-delegator growth (and what is sybilable vs sybil-neutral).
  </Card>
  <Card title="Rewards vs withdrawals (time series)" href="/research/rewards-withdraw-timeseries">
    Monthly/yearly LPT rewards claimed vs `WithdrawStake` (sell-pressure proxy; includes principal).
  </Card>
  <Card title="Reflexivity + yield extraction (mitigations)" href="/research/reflexivity-and-yield-extraction">
    Delta-neutral extraction thesis + mitigation primitives (escrow/vesting, reward-only exit locks/penalties).
  </Card>
  <Card title="Solutions: Lisar" href="/solutions/lisar">
    Treasury program outcomes + KPI alignment vs the stated goals.
  </Card>
  <Card title="Solutions: IDOL / Arrakis" href="/solutions/ydol">
    DEX liquidity-focused proposal analysis (mechanism, risks, and measurement).
  </Card>
  <Card title="Solutions: Tenderize (tLPT)" href="/solutions/tenderize">
    Historical Livepeer liquid staking: adoption evidence, mechanics, and failure modes.
  </Card>
  <Card title="Solutions: Delegator tiers (stake + contribution)" href="/solutions/delegator-tiers">
    A tier ladder that targets small/mid delegators using verifiable usage and contributions (sybil-costly).
  </Card>
  <Card title="Cross-protocol experiments" href="/research/cross-protocol-tokenomics-experiments">
    What worked (and what backfired) in crypto incentives, with takeaways for Livepeer.
  </Card>
</CardGroup>
