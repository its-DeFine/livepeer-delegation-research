# Livepeer Delegation Research

This repo is a “one place” to frame the **Livepeer delegation problem** and then **evaluate proposed solutions** (tokenomics changes, products, treasury-funded programs, etc.) using **reproducible evidence**.

## How to use this repo

- Single overview (read this first): `docs/overview.md`
- Problem framing + metrics: `docs/problem.md`
- Evaluation rubric + scoring: `docs/rubric.md`
- Solution dossiers: `solutions/`
- Cross-solution comparison: `docs/scoreboard.md`
- Deep dives / background notes: `research/`

## Clone

`git clone https://github.com/its-DeFine/livepeer-delegation-research.git`

## Docs (Mintlify)

This repo includes a `docs.json` so it can be browsed as a Mintlify docs site.

- Run locally: `npx mintlify dev --no-open`
- Open: `http://localhost:3000/docs` (or `http://localhost:3000/` → redirects)

## Hosted docs (Vercel)

This repo also includes a small Docusaurus site so it can be deployed to Vercel.

- Local preview: `npm install` then `npm run start` (Docusaurus dev server)
- Deploys automatically via Vercel Git integration on pushes to `main`

## License

MIT — see `LICENSE`.

## Principles

- Evidence first: prefer on-chain / verifiable metrics over narratives.
- Separate “shipped product” from “measurable adoption”: both matter, but don’t conflate them.
- Be explicit about sybil assumptions: if a proposal needs identity/KYC, say it.
