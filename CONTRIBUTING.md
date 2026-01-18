# Contributing (Avoiding Conflicts)

## Ground rules

- Keep shared edits minimal (prefer small diffs) in:
  - `docs/overview.md`
  - `docs/scoreboard.md`
  - `docs/rubric.md`
- Put new work in its own place:
  - Fill in a new folder under `solutions/<name>/`.

## Adding a new solution dossier (folder)

1) Copy `solutions/_template.md` into `solutions/<name>/README.md`.
2) Add links to evidence (on-chain artifacts, dashboards, forum posts).
3) Add a row to `docs/scoreboard.md`.

## If you need separate repos (rare)

Prefer vendoring the content into `solutions/<name>/` so browsing stays zero-friction.
If you want to preserve history while still vendoring, use `git subtree` (optional).

## Docs preview (Mintlify)

- `npx mintlify dev`
