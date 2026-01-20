---
title: Research Notes
description: Evidence packs and deeper dives used to ground solution reviews in reproducible on-chain analysis.
---

# Research Notes

This folder collects deeper dives and working notes used to ground the solution reviews in evidence.

<CardGroup cols={2}>
  <Card title="Outflows + retention" href="/research/livepeer-delegator-outflows-research">
    Delegation exits, dormancy proxies, retention curves, and post-withdraw destination classification.
  </Card>
  <Card title="Reflexivity + yield extraction" href="/research/reflexivity-and-yield-extraction">
    LPT inflation rewards, reward withdrawals, and how delta-neutral staking can create structural sell pressure.
  </Card>
  <Card title="Incentives + tokenomics" href="/research/livepeer-delegator-incentives">
    Design patterns to grow small delegators without enabling easy sybil farming.
  </Card>
  <Card title="Outflows by size band" href="/research/delegator-outflows-by-size-band">
    Who exits (by count vs LPT) and whether each size band is growing via new delegators per year.
  </Card>
  <Card title="Cross-protocol experiments" href="/research/cross-protocol-tokenomics-experiments">
    What worked (and what backfired) in crypto incentive design, with takeaways for Livepeer.
  </Card>
</CardGroup>

- `research/livepeer-delegator-incentives.md`: tokenomics/program design ideas + constraints.
- `research/livepeer-delegator-outflows-research.md`: on-chain outflow + sybil-cashout hypothesis research.
- `research/delegator-outflows-by-size-band.md`: outflows segmented by delegator size + new delegators per year by size.
- `research/delegate-525419ff-top-unbonders.md`: delegate profile — top unbonders + claimed vs `WithdrawStake` cashout.
- `research/eth-l1-wallet-86abf78a-origin.md`: L1 origin trace — bond deposits, withdraws, and LPT transfer counterparties.
- `research/cross-protocol-tokenomics-experiments.md`: precedent patterns (worked vs failed) and what to copy/avoid.

These were imported from the main workspace repo and should be edited/maintained here going forward.
