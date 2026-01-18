# Livepeer Delegation Research (Private)

This repo is the “one place” to frame the **Livepeer delegation problem** and then **evaluate proposed solutions** (tokenomics changes, products, treasury-funded programs, etc.) using **reproducible evidence**.

## How to use this repo

- Single overview (read this first): `docs/overview.md`
- Problem framing + metrics: `docs/problem.md`
- Evaluation rubric + scoring: `docs/rubric.md`
- Solution dossiers: `solutions/`
- Cross-solution comparison: `docs/scoreboard.md`
- Deep dives / background notes: `research/`

## Clone

This repo includes git submodules (e.g. `solutions/lisar/`). Clone with submodules:

`git clone --recurse-submodules https://github.com/its-DeFine/livepeer-delegation-research.git`

If you already cloned without them:

`git submodule update --init --recursive`

## Docs (Mintlify)

This repo includes a `docs.json` so it can be browsed as a Mintlify docs site.

- Run locally: `npx mintlify dev --no-open`
- Open: `http://localhost:3000/docs` (or `http://localhost:3000/` → redirects)

## Hosted docs (Vercel)

This repo also includes a small Docusaurus site so it can be deployed to Vercel.

- Local preview: `npm install` then `npm run start` (Docusaurus dev server)
- GitHub Actions deploy: `.github/workflows/deploy-vercel.yml` (requires GitHub secrets `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`)

## Principles

- Evidence first: prefer on-chain / verifiable metrics over narratives.
- Separate “shipped product” from “measurable adoption”: both matter, but don’t conflate them.
- Be explicit about sybil assumptions: if a proposal needs identity/KYC, say it.
