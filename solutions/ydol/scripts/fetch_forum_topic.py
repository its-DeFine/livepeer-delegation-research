from __future__ import annotations

import argparse
from pathlib import Path

from bs4 import BeautifulSoup

from utils import DATA_DIR, discourse_topic_json_url, ensure_dir, write_json, write_text


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    # Discourse cooked HTML includes a lot of whitespace; preserve paragraphs with blank lines.
    raw_lines = [ln.rstrip() for ln in soup.get_text("\n", strip=False).splitlines()]
    out: list[str] = []
    blank = 0
    for ln in raw_lines:
        if ln.strip() == "":
            blank += 1
            if blank <= 2:
                out.append("")
        else:
            blank = 0
            out.append(ln.strip())
    return "\n".join(out).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a Discourse topic JSON and extract posts to markdown.")
    parser.add_argument(
        "--topic-url",
        default="https://forum.livepeer.org/t/pre-proposal-idol-improving-dex-onchain-liquidity/3151",
        help="Any URL within the topic is fine; the script will resolve it to the topic .json endpoint.",
    )
    parser.add_argument("--refresh", action="store_true", help="Re-download even if cached.")
    args = parser.parse_args()

    json_url = discourse_topic_json_url(args.topic_url)
    topic_id = json_url.split("/")[-1].replace(".json", "")

    out_json = DATA_DIR / f"forum-topic-{topic_id}.json"
    ensure_dir(out_json.parent)

    if out_json.exists() and not args.refresh:
        data = out_json.read_text(encoding="utf-8")
        import json

        data = json.loads(data)
    else:
        import requests

        resp = requests.get(json_url, timeout=30, headers={"User-Agent": "proposal-review/1.0"})
        resp.raise_for_status()
        data = resp.json()
        write_json(out_json, data)

    posts_dir = DATA_DIR / f"forum-posts-{topic_id}"
    ensure_dir(posts_dir)

    index_lines = [f"# Forum snapshot: {data.get('title','(untitled)')}", "", f"Source: {args.topic_url}", ""]
    posts = data.get("post_stream", {}).get("posts", [])
    for post in sorted(posts, key=lambda p: p.get("post_number", 0)):
        num = post.get("post_number")
        username = post.get("username", "unknown")
        created_at = post.get("created_at", "")
        cooked = post.get("cooked", "")

        body = html_to_text(cooked)
        md = f"# Post {num} — @{username}\n\nCreated: {created_at}\n\n{body}"
        path = posts_dir / f"post-{num:02d}-{username}.md"
        write_text(path, md)
        index_lines.append(f"- `post-{num:02d}-{username}.md`")

    write_text(posts_dir / "index.md", "\n".join(index_lines) + "\n")
    print(f"Wrote {len(posts)} posts to `{posts_dir}` and cached JSON to `{out_json}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
