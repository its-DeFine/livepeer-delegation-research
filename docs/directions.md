---
title: General Directions
description: Proposed high-level directions to grow 1k–10k and 10k+ delegators while staying sybil-aware.
---

# General Directions (What to Do Next)

This section is intentionally “directional”: it’s meant to help stakeholders align on what kinds of interventions are likely to move the important brackets (`1k–10k`, `10k+`) and how to measure progress.

## Direction 1 — Increase LPT utility (so larger participants can enter/exit sanely)

Why: the data implies that security-relevant growth is bracket growth, and big actors need deep liquidity + usable rails.

What it could include:
- A conservative **liquid staking** path (`stLPT / wstLPT`), with integrations (borrowing, LP, vaults).
- Targeted **DEX liquidity** improvements with explicit KPIs and stop conditions (see IDOL/Arrakis dossier).

How to measure:
- Growth in `1k–10k` and `10k+` wallet counts and bonded LPT
- Delegate/orchestrator concentration (top-10 share, Nakamoto 33/50)

## Direction 2 — Make incentives retention-gated (not “pay per address”)

Why: paying “small balances per address” is sybilable; retention gating is harder to game and aligns with long-term stake.

What it could include:
- Treasury bonuses that vest over 90–180 days and are forfeited on early unbond/withdraw.
- “Re-delegate and stay” campaigns (time-boxed) targeting the `1k–10k` bracket.

How to measure:
- 30/90/180d retention of new entrants in `1k–10k` and `10k+`
- Net bonded stake change (not just churn)

## Direction 3 — Treat “small delegators” as a UX/onboarding problem, not a security lever

Why: small wallets are important for community participation, but they don’t move bonded stake unless you also solve UX and liquidity.

What it could include:
- Gas sponsorship + “one-click delegation” funnels (Lisar-like), but with explicit stake/retention KPIs.
- Programs that nudge users to graduate from “single-digit LPT” toward meaningful stake bands over time.

How to measure:
- Funnel metrics: funded → bonded → still bonded at 90d
- Graduation: share of cohort that crosses `100`, `1k`, `10k` thresholds

## Direction 4 — Increase independent high-stake delegates (competition + decentralization)

Why: decentralization is primarily a function of stake distribution across **delegates**, not just delegator accounts.

What it could include:
- Programs that help new/independent orchestrators reach meaningful stake (without concentrating to a single incumbent).
- Transparent “delegate quality” dashboards so larger delegators can allocate rationally.

How to measure:
- # of delegates ≥ `100k` and ≥ `1m` bonded stake
- Nakamoto coefficients over time (33% / 50%)

## Direction 5 — Reduce inflation extractability (so yield doesn’t become structural sell pressure)

Why: if large actors can run delta-neutral staking, inflation rewards can get routinely withdrawn and routed off-chain, creating reflexive price pressure.

What it could include:
- Protocol-level: separate principal vs rewards and make the **reward component** time-gated (vesting) and/or penalized on early exit (avoid flat “principal exit taxes”).
- Program-level (if protocol change is too heavy): bonuses in an escrow contract with vest/forfeit; this helps program incentives but does **not** fix base-inflation extractability by itself.

How to measure:
- Reward-only exits over time (requires principal-vs-reward separation in staking accounting)
- Bridge-out → exchange routing changes (see `/research/l1-bridge-recipient-second-hop`)
- Retention curves for `1k–10k` and `10k+` cohorts

## Where the evidence lives

<CardGroup cols={2}>
  <Card title="Executive statement" href="/docs/statement">
    The bracket thesis and why it matters.
  </Card>
  <Card title="Reflexivity + yield extraction" href="/research/reflexivity-and-yield-extraction">
    The delta-neutral thesis and mitigation primitives (escrow/vesting, reward-only penalties, and measurement).
  </Card>
  <Card title="Analytics jump table" href="/docs/analytics">
    Links to the board, time series, outflow research, and bridge-out decode.
  </Card>
</CardGroup>
