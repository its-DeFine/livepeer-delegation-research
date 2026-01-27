---
title: Exchange Label Sources
description: Document how we source, filter, and caveat Ethereum exchange labels for routing analyses.
---

# Exchange label sources (Ethereum)

This guidance covers how we document upstream label datasets, curate exchange addresses, and communicate "lower bound" caveats in exchange routing analyses.

## Recommended upstream datasets

- Etherscan label pages and any public label dumps or APIs they publish. Use the "Exchange" category labels as the primary source for L1.
- Chain-specific explorers when routing spans other chains (for example, Arbiscan, Optimism, Base). Keep chain labels separate.
- Exchange transparency or proof-of-reserves disclosures (official exchange posts or dashboards).
- Public, versioned GitHub lists that include source links and a clear license. Treat these as supplemental and lower confidence unless independently verified.

## Filtering and curation criteria

- Require explicit exchange naming (for example, "Binance 14", "Coinbase 1") and avoid ambiguous service tags.
- Prefer labels with a primary source (explorer label or exchange disclosure). If using a community list, require at least one independent confirmation.
- Keep categories separate: exchange, bridge, dex_router, token, custodian, mixer. Do not fold non-exchange services into exchange routing.
- Track chain context (L1 vs L2). The same address on different chains is unrelated and must not be merged.
- Record provenance and confidence per address:
  - source name and URL
  - retrieval date
  - label text as shown upstream
  - confidence (high, medium, low)
  - notes about why it is included or excluded
- Periodically re-validate: exchange wallets rotate, labels can be stale, and deposit addresses can change.

## Lower-bound disclaimers for exchange routing analyses

Always include a "lower bound" disclaimer when presenting routing results:

- The label set is intentionally small and incomplete. Unlabeled exchange wallets and unlabeled deposit addresses are not counted.
- Explorer labels can be stale or incorrect. False positives and false negatives are possible.
- Multi-hop routing is heuristic and windowed; it can miss splits, delays, or intermediate hops.
- Transfers to exchange wallets are not proof of sale. They only indicate a plausible exchange or custody destination.
- Off-chain trades, internal exchange ledger movements, and OTC activity are invisible on-chain.

## Suggested fields for label datasets

- address
- category (exchange, bridge, dex_router, token, custodian, mixer)
- exchange (normalized name)
- label (verbatim upstream label)
- source (explorer, exchange disclosure, community list)
- source_url
- retrieved_at (YYYY-MM-DD)
- confidence (high, medium, low)
- notes
