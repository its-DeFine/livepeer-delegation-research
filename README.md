# Livepeer Delegation Research (Private)

This repo is the “one place” to frame the **Livepeer delegation problem** and then **evaluate proposed solutions** (tokenomics changes, products, treasury-funded programs, etc.) using **reproducible evidence**.

## How to use this repo

- Problem framing + metrics: `docs/problem.md`
- Evaluation rubric + scoring: `docs/rubric.md`
- Solution dossiers (submodules or folders): `solutions/`
- Cross-solution comparison: `docs/scoreboard.md`
- Deep dives / background notes: `research/`

## Clone (includes submodules)

- Clone with submodules:
  - `git clone --recurse-submodules https://github.com/its-DeFine/livepeer-delegation-research.git`
- Or after cloning:
  - `git submodule update --init --recursive`

## Principles

- Evidence first: prefer on-chain / verifiable metrics over narratives.
- Separate “shipped product” from “measurable adoption”: both matter, but don’t conflate them.
- Be explicit about sybil assumptions: if a proposal needs identity/KYC, say it.
