# Cached data (pinned snapshots)

Scripts in `scripts/` cache downloads here to make runs reproducible and reduce unnecessary network calls.

Typical contents:
- `forum-topic-*.json` and extracted post markdown
- downloaded audit PDFs + extracted text
- CoinGecko price snapshots used during runs
