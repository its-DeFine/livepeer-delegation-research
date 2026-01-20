---
title: Analytics
description: Key dashboards and evidence for Livepeer delegation on Arbitrum (brackets, flows, concentration, and exits).
---

# Analytics (Key Metrics)

This page is the “metrics jump table” for stakeholders.

## Read in this order

<CardGroup cols={2}>
  <Card title="Delegation board (brackets + inflow/outflow + gain/bleed)" href="/research/delegation-board">
    The single best starting point: bracket sizes, net change window, inflow/outflow proxies, and top delegate gain/bleed.
  </Card>
  <Card title="Bracket time series (monthly, event replay)" href="/research/delegator-band-timeseries">
    How the bracket counts + bonded LPT evolved since 2022 (and concentration trends).
  </Card>
  <Card title="Outflows by size band (who exits?)" href="/research/delegator-outflows-by-size-band">
    Withdraw/unbond behavior grouped by wallet size (count vs LPT).
  </Card>
  <Card title="Stake distribution snapshot" href="/research/delegator-stake-distribution">
    A current distribution view (useful for pie charts and “how many wallets are tiny” questions).
  </Card>
  <Card title="Bridge-out decode (Arbitrum → L1 recipients)" href="/research/arbitrum-bridge-out-decode">
    Shows that major “whale exits” often bridge to L1 (and mostly to self), which is not the same as selling.
  </Card>
  <Card title="L1 follow-up (post-bridge destinations)" href="/research/l1-bridge-recipient-followup">
    After bridge-outs land on Ethereum L1, this tracks where the L1 recipients send LPT next (DEX vs contracts vs EOAs).
  </Card>
  <Card title="L1 second hop (exchange routing)" href="/research/l1-bridge-recipient-second-hop">
    Follows the biggest L1 EOA destinations one hop further; surfaces labeled exchange endpoints (best-effort, label-set based).
  </Card>
  <Card title="Rewards claimed vs stake withdrawn (time series)" href="/research/rewards-withdraw-timeseries">
    Monthly/yearly totals of LPT rewards claimed and LPT withdrawn via `WithdrawStake` (a rough upper bound for liquidity exits).
  </Card>
  <Card title="Reflexivity + yield extraction (delta-neutral thesis)" href="/research/reflexivity-and-yield-extraction">
    Evidence-backed look at inflation rewards, reward withdrawals, and why delta-neutral staking can create structural sell pressure.
  </Card>
  <Card title="Deep dive: outflows + retention evidence pack" href="/research/livepeer-delegator-outflows-research">
    The longer-form research notes, methodology, and artifacts behind churn/cashout claims.
  </Card>
</CardGroup>

## Solution analytics

<CardGroup cols={2}>
  <Card title="Lisar (delegation onboarding)" href="/solutions/lisar">
    Outcomes vs KPI and what it actually moved: count vs stake.
  </Card>
  <Card title="IDOL / Arrakis (DEX liquidity)" href="/solutions/ydol">
    Slippage + liquidity analysis and the risk/measurement surface.
  </Card>
  <Card title="Tenderize (tLPT liquid staking)" href="/solutions/tenderize">
    Evidence of many small stake participants, and why it doesn’t increase protocol delegator count directly.
  </Card>
</CardGroup>
