---
title: "Address label sources (exchange + routers)"
description: "Where `data/labels.json` comes from, what it does/doesn’t cover, and how to extend it safely for exchange-routing evidence packs."
sidebar_label: "Label sources"
---

# Address label sources (exchange + routers)

Several evidence packs in this repo classify “likely exchange routing” by checking whether a transfer lands in a small curated set of **labeled exchange hot wallets** in `data/labels.json`.

This page documents how those labels are sourced and the limitations you should assume when interpreting results.

## What `data/labels.json` is

- A hand-curated mapping from EVM address → `{category, name, ...}`.
- Categories include (at minimum): `exchange`, `dex_router`, `bridge`, `token`, `livepeer_contract`, `burn`.
- Used by reports like:
  - `/research/l1-bridge-recipient-second-hop` (Livepeer L1 exchange routing)
  - `/research/extraction-timing-traces` (Livepeer L2→L1→exchange tight-window traces)
  - `/research/thegraph-delegation-withdrawal-routing` (Graph withdrawal → exchange routing, best-effort)

## Where the labels come from (public sources)

We prefer sources that replicate **Etherscan “labels”** into machine-readable address lists:

- `brianleect/etherscan-labels` (GitHub): periodic dumps of Etherscan-labeled addresses.
- `yevadrian/etherscan-labels` (GitHub): similar Etherscan label export.
- `dawsbot/eth-labels` (GitHub): additional labeled datasets (often includes Etherscan-derived tags).

When adding addresses, we keep the set **small and conservative**:
- Prefer exchange **hot wallets** / well-known custody endpoints.
- Avoid “Token”, “Deployer”, or unrelated label namespaces that create false positives.
- Avoid very large label sets when reports rely on `eth_getLogs` with topic OR filters (some providers reject huge topic arrays).

## Limitations (how to interpret results)

All exchange-routing results should be treated as a **lower bound**:

- **CEX deposit addresses are not fully labeled.** Many deposits go to per-user deposit addrs that are unlabeled.
- **Routing can go through unlabeled EOAs/contracts.** A 1–3 hop scan catches only simple paths.
- **Cross-chain exits complicate classification.** For Livepeer, bridging out of Arbitrum to L1 is a common intermediate step.
- **Labels can be stale.** Exchange wallet clusters change over time; a label dump is not ground truth.

If a report says “X% routed to exchanges”, read it as:
> “At least X% routed into this small labeled exchange set within the scan window.”

## How to extend safely

1) Add only addresses with strong public labeling (Etherscan label or widely cited hot wallet).
2) Record `category=exchange` and a stable `exchange` key (e.g., `binance`, `coinbase`, `kraken`).
3) Prefer adding a few high-signal hot wallets over thousands of deposit addresses.
4) Re-run the evidence pack(s) that depend on the labels to confirm no performance regressions.

