# Contributing (Avoiding Conflicts)

## Ground rules

- Keep shared edits minimal (prefer small diffs) in:
  - `docs/scoreboard.md`
  - `docs/rubric.md`
- Put new work in its own place:
  - Fill in a new folder under `solutions/<name>/`, or
  - Create a separate private repo for the solution and add it as a submodule under `solutions/<name>/`.

## Adding a new solution dossier (folder)

1) Copy `solutions/_template.md` into `solutions/<name>/README.md`.
2) Add links to evidence (on-chain artifacts, dashboards, forum posts).
3) Add a row to `docs/scoreboard.md`.

## Adding a new solution dossier (submodule)

1) Create the private repo for the solution (scripts + pinned artifacts).
2) In this repo:
   - `git submodule add <repo-url> solutions/<name>`
3) Add a row to `docs/scoreboard.md` pointing at `solutions/<name>/`.

