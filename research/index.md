---
title: Research Notes
description: Evidence packs and deeper dives used to ground solution reviews in reproducible on-chain analysis.
---

# Research Notes

This folder collects deeper dives and working notes used to ground the solution reviews in evidence.

<CardGroup cols={2}>
  <Card title="Livepeer vs peers (comparison)" href="/research/livepeer-vs-peers">
    Side-by-side comparison of Livepeer vs peer protocols (exchange routing, post-exit roles, exit friction, and Livepeer-only signals).
  </Card>
  <Card title="Livepeer vs peers (infographics, static)" href="/research/livepeer-vs-peers-infographics">
    Markdown-only “one-pager” infographics for GitHub/Mintlify (no React/MDX required).
  </Card>
  <Card title="Outflows + retention" href="/research/livepeer-delegator-outflows-research">
    Delegation exits, dormancy proxies, retention curves, and post-withdraw destination classification.
  </Card>
  <Card title="Reflexivity + yield extraction" href="/research/reflexivity-and-yield-extraction">
    LPT inflation rewards, reward withdrawals, and how delta-neutral staking can create structural sell pressure.
  </Card>
  <Card title="L1 follow-up for bridge-outs" href="/research/l1-bridge-recipient-followup">
    Tracks where the Arbitrum bridge-out recipients route LPT on Ethereum L1 (contracts vs EOAs vs known DEX routers).
  </Card>
  <Card title="L1 second hop (exchange routing)" href="/research/l1-bridge-recipient-second-hop">
    Follows the biggest L1 EOA destinations one hop further; surfaces labeled exchange endpoints (best-effort).
  </Card>
  <Card title="Exchange routing metrics" href="/research/exchange-routing-metrics">
    Standardized, lower-bound “% routed to exchanges” metrics across protocols (best-effort).
  </Card>
  <Card title="Extraction timing traces (L2→L1→exchange)" href="/research/extraction-timing-traces">
    Links `WithdrawStake` → L2 bridge-out → L1 escrow receipt → tight-window exchange routing (best-effort; 1 intermediate hop).
  </Card>
  <Card title="Buy pressure proxies (exchange outflows → bonders)" href="/research/buy-pressure-proxies">
    Buy-side proxy: labeled CEX outflows on L1 and whether recipients bridge + bond on Arbitrum (best-effort).
  </Card>
  <Card title="Stake rotation (TransferBond)" href="/research/livepeer-transferbond-rotation">
    Quantifies stake rotation / wallet rotation via `TransferBond` on Livepeer’s Arbitrum BondingManager (best-effort).
  </Card>
  <Card title="Rewards claimed vs stake withdrawn (time series)" href="/research/rewards-withdraw-timeseries">
    Monthly/yearly totals of LPT rewards claimed vs stake withdrawn via `WithdrawStake`.
  </Card>
  <Card title="Extraction fingerprints (on-chain proxies)" href="/research/extraction-fingerprints">
    Top-50 “cashout-heavy” wallets: rewards claimed vs withdrawn, post-withdraw routing, and whether they remain bonded.
  </Card>
  <Card title="DePIN benchmark: Filecoin vs Livepeer" href="/research/filecoin-lock-burn-metrics">
    Filecoin’s lock/burn primitives (on-chain) contrasted with Livepeer’s extraction proxies.
  </Card>
  <Card title="DePIN: reward vesting vs liquid rewards" href="/research/depin-reward-vesting-vs-liquid">
    What “time-locked linear rewards” look like in practice, and what tends to happen with/without them.
  </Card>
  <Card title="DePIN: liquidity primitives snapshot" href="/research/depin-liquidity-primitives-snapshot">
    On-chain snapshot of unbond/thaw delays and Filecoin vesting/lock primitives (used to back comparative claims).
  </Card>
  <Card title="Pocket: liquidity primitives" href="/research/pocket-liquidity-primitives">
    Pocket Shannon (poktroll) unbonding delays + mint allocation parameters (on-chain).
  </Card>
  <Card title="Theta: liquidity primitives" href="/research/theta-liquidity-primitives">
    Theta staking withdrawal/unstaking delays (Guardian stake ~48h; TFUEL stake ~60h) with chain context.
  </Card>
  <Card title="The Graph: withdrawals → exchange routing" href="/research/thegraph-delegation-withdrawal-routing">
    Delegation withdrawal events and whether withdrawing delegators route GRT to labeled exchanges within a tight window (best-effort).
  </Card>
  <Card title="Curve: veCRV withdraws → exchange routing" href="/research/curve-vecrv-exit-routing">
    veCRV withdraw events and whether recipients route CRV to labeled exchanges within a tight window (best-effort).
  </Card>
  <Card title="Frax: veFXS withdraws → exchange routing" href="/research/frax-vefxs-exit-routing">
    veFXS withdraw events and whether recipients route FXS to labeled exchanges within a tight window (best-effort).
  </Card>
  <Card title="Aave: stkAAVE redeem → exchange routing" href="/research/aave-stkaave-redeem-exit-routing">
    stkAAVE redeem events and whether recipients route AAVE to labeled exchanges within a tight window (best-effort).
  </Card>
  <Card title="Label sources" href="/research/address-label-sources">
    Where `data/labels.json` comes from and how to interpret “exchange routing” (lower bound).
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
- `research/depin-reward-vesting-vs-liquid.md`: how DePIN protocols handle reward liquidity (linear vesting vs liquid rewards).
- `research/depin-liquidity-primitives-snapshot.md`: on-chain snapshot of unbond/thaw delays and Filecoin vesting/lock primitives.
- `research/exchange-routing-metrics.md`: standardized, lower-bound exchange routing shares across protocols.
- `research/pocket-liquidity-primitives.md`: Pocket Shannon (poktroll) unbonding + mint allocation snapshot.
- `research/theta-liquidity-primitives.md`: Theta staking withdrawal delay excerpts (Guardian stake + TFUEL staking).
- `research/thegraph-delegation-withdrawal-routing.md`: Graph delegation withdrawals and tight-window routing to labeled exchanges (best-effort).
- `research/curve-vecrv-exit-routing.md`: Curve veCRV withdraw events and tight-window routing to labeled exchanges (best-effort).
- `research/frax-vefxs-exit-routing.md`: Frax veFXS withdraw events and tight-window routing to labeled exchanges (best-effort).
- `research/aave-stkaave-redeem-exit-routing.md`: Aave stkAAVE redeem events and tight-window routing to labeled exchanges (best-effort).
- `research/address-label-sources.md`: where exchange/router labels come from + how to interpret “exchange routing” results.

These were imported from the main workspace repo and should be edited/maintained here going forward.
